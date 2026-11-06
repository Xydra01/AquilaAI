#include "aquila/knowledge/html_cleaner.hpp"
#include "aquila/knowledge/web_fetcher.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck.h>
#include <rapidcheck/catch.h>

#include <string>

using namespace aquila::knowledge;

TEST_CASE("HtmlCleaner basic text extraction and entity decoding", "[html_cleaner]") {
    SECTION("Extracts title and cleans markup") {
        const std::string html = R"(
            <!DOCTYPE html>
            <html>
            <head>
                <title>Aquila Framework &amp; Docs</title>
                <style>body { font-size: 14px; }</style>
                <script>console.log("noisy tracking script");</script>
            </head>
            <body>
                <header><nav><a href="/">Home</a></nav></header>
                <h1>Welcome to Aquila</h1>
                <p>Aquila is a C++20 agent framework &quot;built for speed&quot;.</p>
                <!-- This is an internal comment -->
                <div>Features include:</div>
                <ul>
                    <li>Deterministic Blake2b Embeddings</li>
                    <li>Zero-I/O Page Cache</li>
                </ul>
                <footer>&copy; 2026 Aquila Project</footer>
            </body>
            </html>
        )";

        auto cleaned = HtmlCleaner::clean(html);
        CHECK(cleaned.title == "Aquila Framework & Docs");
        CHECK(cleaned.text.find("Welcome to Aquila") != std::string::npos);
        CHECK(cleaned.text.find("Aquila is a C++20 agent framework \"built for speed\".") != std::string::npos);
        CHECK(cleaned.text.find("Deterministic Blake2b Embeddings") != std::string::npos);

        // Stripped sections
        CHECK(cleaned.text.find("noisy tracking script") == std::string::npos);
        CHECK(cleaned.text.find("font-size") == std::string::npos);
        CHECK(cleaned.text.find("Home") == std::string::npos);
        CHECK(cleaned.text.find("internal comment") == std::string::npos);
        CHECK(cleaned.text.find("Aquila Project") == std::string::npos);
    }

    SECTION("Decodes HTML entities properly") {
        CHECK(HtmlCleaner::decode_entities("&lt;div&gt;&amp;&quot;&#39;&nbsp;&copy;") == "<div>&\"' (c)");
        CHECK(HtmlCleaner::decode_entities("&#65;&#66;&#67;") == "ABC");
        CHECK(HtmlCleaner::decode_entities("&#x41;&#x42;&#x43;") == "ABC");
    }

    SECTION("Handles malformed and unclosed tags without crashing") {
        auto cleaned = HtmlCleaner::clean("<p>Unclosed paragraph <script>alert('run')");
        CHECK(!cleaned.text.empty());
        CHECK(cleaned.text.find("alert") == std::string::npos);
    }
}

TEST_CASE("WebFetcher mock handler and safety policies", "[web_fetcher]") {
    FetchOptions options{
        .timeout_seconds = 5,
        .max_body_bytes = 1000,
        .max_redirects = 2,
        .user_agent = "Aquila-Test/1.0"
    };
    WebFetcher fetcher(options);

    SECTION("Successful mock fetch") {
        fetcher.set_mock_handler([](std::string_view url) -> std::optional<FetchResponse> {
            if (url == "http://example.com/page") {
                return FetchResponse{
                    .status_code = 200,
                    .content_type = "text/html; charset=utf-8",
                    .body = "<html><title>Example</title><body>Content</body></html>",
                    .final_url = "http://example.com/page"
                };
            }
            return std::nullopt;
        });

        auto res = fetcher.fetch("http://example.com/page");
        CHECK(res.status_code == 200);
        CHECK(res.body.find("Content") != std::string::npos);
    }

    SECTION("Rejects non-2xx status code") {
        fetcher.set_mock_handler([](std::string_view) -> std::optional<FetchResponse> {
            return FetchResponse{
                .status_code = 404,
                .content_type = "text/html",
                .body = "Not Found",
                .final_url = "http://example.com/missing"
            };
        });

        CHECK_THROWS_AS(fetcher.fetch("http://example.com/missing"), FetchError);
    }

    SECTION("Rejects non-text MIME type") {
        fetcher.set_mock_handler([](std::string_view) -> std::optional<FetchResponse> {
            return FetchResponse{
                .status_code = 200,
                .content_type = "application/octet-stream",
                .body = "binary data",
                .final_url = "http://example.com/file.bin"
            };
        });

        CHECK_THROWS_AS(fetcher.fetch("http://example.com/file.bin"), FetchError);
    }

    SECTION("Rejects body exceeding max_body_bytes") {
        fetcher.set_mock_handler([](std::string_view) -> std::optional<FetchResponse> {
            return FetchResponse{
                .status_code = 200,
                .content_type = "text/plain",
                .body = std::string(2000, 'x'),
                .final_url = "http://example.com/large"
            };
        });

        CHECK_THROWS_AS(fetcher.fetch("http://example.com/large"), FetchError);
    }
}

// Feature: m6-knowledge-module, Property 6: HTML Cleaning Safety
TEST_CASE("Property 6: HTML cleaning safety and termination", "[rapidcheck]") {
    rc::prop("HtmlCleaner terminates safely for arbitrary inputs", [](const std::string& input) {
        auto cleaned = HtmlCleaner::clean(input);
        // Cleaner should not throw and should output valid UTF-8/ASCII strings
        RC_ASSERT(cleaned.text.size() <= input.size() * 2 + 100);
        RC_ASSERT(cleaned.title.size() <= input.size() * 2 + 100);
    });
}

