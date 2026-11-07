#include "aquila/knowledge/web_search.hpp"
#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/modules/registry.hpp"

#include <catch2/catch_test_macros.hpp>

using namespace aquila;
using namespace aquila::knowledge;

TEST_CASE("WebSearchEngine: provider resolution and options", "[web_search]") {
    CHECK(search_provider_from_string("duckduckgo") == SearchProvider::duckduckgo);
    CHECK(search_provider_from_string("searxng") == SearchProvider::searxng);
    CHECK(search_provider_from_string("wikipedia") == SearchProvider::wikipedia);
    CHECK(search_provider_from_string("auto") == SearchProvider::auto_detect);

    CHECK(to_string(SearchProvider::duckduckgo) == "duckduckgo");
    CHECK(to_string(SearchProvider::searxng) == "searxng");
    CHECK(to_string(SearchProvider::wikipedia) == "wikipedia");
}

TEST_CASE("WebSearchEngine: mock search handler and ranking", "[web_search]") {
    WebSearchEngine engine;
    engine.set_mock_handler([](std::string_view query) -> std::optional<std::vector<SearchResult>> {
        if (query == "modern c++") {
            return std::vector<SearchResult>{
                {
                    .title = "Random Blog Post",
                    .url = "https://randomblog.xyz/post",
                    .snippet = "Some thoughts on c++",
                    .engine = "duckduckgo",
                    .score = 5.0
                },
                {
                    .title = "C++ Reference",
                    .url = "https://en.cppreference.com/cpp",
                    .snippet = "Official reference for Modern C++",
                    .engine = "duckduckgo",
                    .score = 65.0
                }
            };
        }
        return std::nullopt;
    });

    auto results = engine.search("modern c++");
    REQUIRE(results.size() == 2);
    // Highest score must be sorted first
    CHECK(results[0].title == "C++ Reference");
    CHECK(results[1].title == "Random Blog Post");
}

TEST_CASE("KnowledgeModule: web_search action execution", "[knowledge_module]") {
    ModuleContext ctx{.workspace_root = "", .max_output_chars = 4000};
    KnowledgeModule km(ctx);

    km.search_engine().set_mock_handler([](std::string_view query) -> std::optional<std::vector<SearchResult>> {
        if (query == "test topic") {
            return std::vector<SearchResult>{
                {
                    .title = "Authoritative Guide",
                    .url = "https://en.cppreference.com/w/cpp",
                    .snippet = "Comprehensive C++ reference documentation",
                    .engine = "duckduckgo",
                    .score = 80.0
                }
            };
        }
        return std::nullopt;
    });

    // Mock page fetcher for the auto-scrape phase
    km.fetcher().set_mock_handler([](std::string_view url) -> std::optional<FetchResponse> {
        if (url == "https://en.cppreference.com/w/cpp") {
            return FetchResponse{
                .status_code = 200,
                .content_type = "text/html",
                .body = "<html><title>C++ Reference</title><body><h1>Standard C++</h1><p>Welcome to modern C++ reference documentation.</p></body></html>",
                .final_url = "https://en.cppreference.com/w/cpp"
            };
        }
        return std::nullopt;
    });

    auto res = km.execute_action("web_search", Json{
        {"query", "test topic"},
        {"max_results", 3},
        {"auto_scrape", true}
    });

    CHECK(res.success);
    CHECK(res.llm_facing_output.find("Web Search Results for 'test topic'") != std::string::npos);
    CHECK(res.llm_facing_output.find("Authoritative Guide") != std::string::npos);
    CHECK(res.llm_facing_output.find("https://en.cppreference.com/w/cpp") != std::string::npos);
}

