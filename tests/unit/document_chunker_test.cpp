#include "aquila/knowledge/document_chunker.hpp"
#include "aquila/knowledge/embedding.hpp"
#include "aquila/storage/sqlite_db.hpp"

#include <catch2/catch_test_macros.hpp>
#include <rapidcheck.h>
#include <rapidcheck/catch.h>

#include <filesystem>
#include <fstream>
#include <string>

using namespace aquila::knowledge;
using namespace aquila::storage;

TEST_CASE("DocumentChunker header hierarchy and breadcrumb generation", "[document_chunker]") {
    DocumentChunker chunker(50); // small word limit to test splitting

    const std::string doc = R"(# Aquila Framework
An advanced C++20 local agent framework.

## Architecture
Modular decoupled architecture.

### Storage Engine
In-process SQLite database with RAII wrappers.
Threadsafe and WAL-enabled.

### Inference Engine
Dual-backend Ollama and LlamaCpp support.

## Recipes
JSON recipe cartridge definitions.
)";

    auto chunks = chunker.chunk_markdown(doc, "docs/architecture.md");
    REQUIRE(chunks.size() >= 4);

    CHECK(chunks[0].breadcrumbs == "Aquila Framework");
    CHECK(chunks[0].content.find("advanced C++20") != std::string::npos);

    CHECK(chunks[1].breadcrumbs == "Aquila Framework > Architecture");
    CHECK(chunks[1].content.find("Modular decoupled") != std::string::npos);

    CHECK(chunks[2].breadcrumbs == "Aquila Framework > Architecture > Storage Engine");
    CHECK(chunks[2].content.find("In-process SQLite") != std::string::npos);

    CHECK(chunks[3].breadcrumbs == "Aquila Framework > Architecture > Inference Engine");
    CHECK(chunks[3].content.find("Dual-backend") != std::string::npos);

    CHECK(chunks[4].breadcrumbs == "Aquila Framework > Recipes");
    CHECK(chunks[4].content.find("recipe cartridge") != std::string::npos);
}

TEST_CASE("LocalDocIndex hybrid retrieval with Dense + FTS5 RRF", "[document_chunker][hybrid]") {
    auto db = SqliteDb::open_memory();
    auto embedder = std::make_shared<HashingEmbedder>(384);
    LocalDocIndex index(db, embedder);

    const std::string md = R"(# Aquila Agent Rebuild
Ground up C++20 reconstruction.

## Storage Layer
SqliteDb provides C++20 RAII around sqlite3 handles.
Uses FTS5 for fast full-text lexical search and BM25 ranking.

## Networking Layer
WebFetcher wraps httplib with redirect limits and timeouts.
HtmlCleaner strips noisy tags like script and style.
)";

    index.index_document("docs/overview.md", md);
    CHECK(index.chunk_count() >= 3);

    SECTION("Hybrid search finds relevant section via Dense and FTS5") {
        auto matches = index.search_hybrid("sqlite raii bm25 fts5", 2);
        REQUIRE(!matches.empty());

        CHECK(matches[0].breadcrumbs == "Aquila Agent Rebuild > Storage Layer");
        CHECK(matches[0].rrf_score > 0.0f);
        CHECK(matches[0].dense_score > 0.0f);

        auto formatted = index.format_search_results(matches);
        CHECK(formatted.find("### Relevant Documentation") != std::string::npos);
        CHECK(formatted.find("Storage Layer") != std::string::npos);
    }

    SECTION("Removing document clears both doc_chunks and FTS5 index") {
        index.remove_document("docs/overview.md");
        CHECK(index.chunk_count() == 0);

        auto matches = index.search_hybrid("sqlite", 5);
        CHECK(matches.empty());
    }

    SECTION("Indexes and queries real repository README.md if present") {
        const std::filesystem::path readme_path = "F:/Users/myfri/Aquila-cpp/README.md";
        if (std::filesystem::exists(readme_path)) {
            std::ifstream file(readme_path);
            std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());

            index.index_document("README.md", content);
            CHECK(index.chunk_count() > 0);

            auto results = index.search_hybrid("Aquila agent framework", 3);
            CHECK(!results.empty());
        }
    }
}

// Feature: m6-knowledge-module, Property 9: Breadcrumb Invariant
TEST_CASE("Property 9: Breadcrumb Invariant", "[rapidcheck]") {
    rc::prop("Emitted chunks preserve parent-child breadcrumb ordering", []() {
        const std::string doc = R"(# Top
Top intro.
## Mid1
Mid1 intro.
### Deep1
Deep1 intro.
## Mid2
Mid2 intro.
)";
        DocumentChunker chunker(100);
        auto chunks = chunker.chunk_markdown(doc, "test.md");

        for (const auto& chunk : chunks) {
            if (chunk.breadcrumbs.find("Deep1") != std::string::npos) {
                RC_ASSERT(chunk.breadcrumbs == "Top > Mid1 > Deep1");
            }
            if (chunk.breadcrumbs.find("Mid2") != std::string::npos) {
                RC_ASSERT(chunk.breadcrumbs == "Top > Mid2");
            }
        }
    });
}

