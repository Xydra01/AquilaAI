#include "aquila/knowledge/page_cache.hpp"
#include "aquila/knowledge/sha256.hpp"
#include "aquila/storage/sqlite_db.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck.h>
#include <rapidcheck/catch.h>

#include <atomic>
#include <string>

using namespace aquila::knowledge;
using namespace aquila::storage;

TEST_CASE("Sha256 known test vectors", "[sha256]") {
    CHECK(Sha256::hash_hex("") ==
          "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    CHECK(Sha256::hash_hex("abc") ==
          "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}

TEST_CASE("PageCache URL canonicalization rules", "[page_cache]") {
    SECTION("Strips default ports") {
        CHECK(PageCache::canonicalize_url("http://example.com:80/path") ==
              "http://example.com/path");
        CHECK(PageCache::canonicalize_url("https://example.com:443/path") ==
              "https://example.com/path");
        CHECK(PageCache::canonicalize_url("http://example.com:8080/path") ==
              "http://example.com:8080/path");
    }

    SECTION("Strips fragments") {
        CHECK(PageCache::canonicalize_url("http://example.com/path#section-1") ==
              "http://example.com/path");
    }

    SECTION("Lowercases scheme and host while preserving path case") {
        CHECK(PageCache::canonicalize_url("HTTP://MySite.COM/UserGuides/M6") ==
              "http://mysite.com/UserGuides/M6");
    }

    SECTION("Sorts query parameters deterministically") {
        CHECK(PageCache::canonicalize_url("http://example.com/search?z=3&a=1&m=2") ==
              "http://example.com/search?a=1&m=2&z=3");
    }
}

TEST_CASE("PageCache hit/miss mechanics and zero-I/O guarantees", "[page_cache]") {
    auto db = SqliteDb::open_memory();
    auto fetcher = std::make_shared<WebFetcher>();

    std::atomic<int> fetch_count{0};
    fetcher->set_mock_handler([&](std::string_view) -> std::optional<FetchResponse> {
        ++fetch_count;
        return FetchResponse{
            .status_code = 200,
            .content_type = "text/html",
            .body = "<html><title>Cached Doc</title><body>Fresh Content</body></html>",
            .final_url = "http://example.com/doc"
        };
    });

    PageCache cache(db, fetcher);
    CHECK(cache.size() == 0);
    CHECK(!cache.has_cached("http://example.com/doc"));

    // 1. Initial fetch (cache miss)
    auto page1 = cache.fetch_and_clean("http://example.com/doc");
    CHECK(!page1.from_cache);
    CHECK(page1.title == "Cached Doc");
    CHECK(page1.clean_text == "Fresh Content");
    CHECK(fetch_count == 1);
    CHECK(cache.size() == 1);
    CHECK(cache.has_cached("http://example.com/doc"));

    // 2. Second fetch of identical canonical URL (cache hit - 0 network I/O)
    auto page2 = cache.fetch_and_clean("HTTP://EXAMPLE.COM:80/doc#ref");
    CHECK(page2.from_cache);
    CHECK(page2.title == "Cached Doc");
    CHECK(page2.clean_text == page1.clean_text);
    CHECK(fetch_count == 1); // Mock was NOT called! 0 I/O!

    // 3. Third fetch with bypass_cache=true (forces refresh)
    auto page3 = cache.fetch_and_clean("http://example.com/doc", true);
    CHECK(!page3.from_cache);
    CHECK(fetch_count == 2); // Mock WAS called!
}

// Feature: m6-knowledge-module, Property 7: Cache Hit Invariance
TEST_CASE("Property 7: Cache Hit Invariance", "[rapidcheck]") {
    rc::prop("Second fetch of canonical URL performs 0 requests and returns identical text", []() {
        auto db = SqliteDb::open_memory();
        auto fetcher = std::make_shared<WebFetcher>();

        int network_calls = 0;
        fetcher->set_mock_handler([&](std::string_view) -> std::optional<FetchResponse> {
            ++network_calls;
            return FetchResponse{
                .status_code = 200,
                .content_type = "text/html",
                .body = "<h1>Title</h1><p>Body text payload</p>",
                .final_url = "http://example.org/prop7"
            };
        });

        PageCache cache(db, fetcher);
        const std::string url = "http://example.org/prop7";

        auto first = cache.fetch_and_clean(url, false);
        RC_ASSERT(!first.from_cache);
        RC_ASSERT(network_calls == 1);

        auto second = cache.fetch_and_clean(url, false);
        RC_ASSERT(second.from_cache);
        RC_ASSERT(network_calls == 1); // 0 additional network calls
        RC_ASSERT(second.clean_text == first.clean_text);
        RC_ASSERT(second.title == first.title);
    });
}

// Feature: m6-knowledge-module, Property 8: Canonical URL Equivalence
TEST_CASE("Property 8: Canonical URL Equivalence", "[rapidcheck]") {
    rc::prop("Equivalent URLs differing only in port, fragment, or query order produce identical hashes", []() {
        const std::string u1 = "http://example.com:80/path?b=2&a=1#section";
        const std::string u2 = "HTTP://EXAMPLE.COM/path?a=1&b=2";

        const auto can1 = PageCache::canonicalize_url(u1);
        const auto can2 = PageCache::canonicalize_url(u2);

        RC_ASSERT(can1 == can2);
        RC_ASSERT(PageCache::compute_url_hash(can1) == PageCache::compute_url_hash(can2));
    });
}

