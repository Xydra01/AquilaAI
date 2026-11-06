#include "aquila/knowledge/embedding.hpp"
#include "aquila/knowledge/vector_index.hpp"
#include "aquila/storage/sqlite_db.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>
#include <rapidcheck.h>
#include <rapidcheck/catch.h>

#include <cmath>
#include <filesystem>
#include <string>

using namespace aquila::knowledge;
using namespace aquila::storage;

TEST_CASE("VectorIndex in-memory operations and similarity ranking", "[vector_index]") {
    auto db = SqliteDb::open_memory();
    auto embedder = std::make_shared<HashingEmbedder>(384);
    VectorIndex index(db, embedder);

    CHECK(index.count("test_coll") == 0);

    index.upsert("test_coll", "doc1", "The quick brown fox jumps over the lazy dog",
                 nlohmann::json{{"instance_id", "inst-1"}, {"tag", "animals"}});
    index.upsert("test_coll", "doc2", "A fast brown fox leaped across a sleepy canine",
                 nlohmann::json{{"instance_id", "inst-1"}, {"tag", "animals"}});
    index.upsert("test_coll", "doc3", "Quantum computing uses qubits and quantum superposition",
                 nlohmann::json{{"instance_id", "inst-2"}, {"tag", "physics"}});

    CHECK(index.count("test_coll") == 3);

    SECTION("Dense search ranks similar texts first") {
        auto matches = index.search_dense("test_coll", "brown fox canine", 3);
        REQUIRE(matches.size() == 3);

        // First two should be the fox sentences
        CHECK((matches[0].id == "doc1" || matches[0].id == "doc2"));
        CHECK((matches[1].id == "doc1" || matches[1].id == "doc2"));
        CHECK(matches[2].id == "doc3");

        // Monotonic scores
        CHECK(matches[0].score >= matches[1].score);
        CHECK(matches[1].score >= matches[2].score);
    }

    SECTION("Metadata filtering by instance_id") {
        auto filtered = index.search_dense("test_coll", "brown fox canine", 5, "inst-2");
        REQUIRE(filtered.size() == 1);
        CHECK(filtered[0].id == "doc3");
        CHECK(filtered[0].metadata["tag"] == "physics");
    }

    SECTION("top_k limits results") {
        auto limited = index.search_dense("test_coll", "fox", 1);
        REQUIRE(limited.size() == 1);
    }

    SECTION("Upsert overwrites existing document") {
        index.upsert("test_coll", "doc1", "Brand new content about spaceships",
                     nlohmann::json{{"instance_id", "inst-1"}, {"tag", "space"}});
        CHECK(index.count("test_coll") == 3);

        auto matches = index.search_dense("test_coll", "spaceships", 1);
        REQUIRE(matches.size() == 1);
        CHECK(matches[0].id == "doc1");
        CHECK(matches[0].metadata["tag"] == "space");
    }
}

TEST_CASE("VectorIndex ChromaDB importer", "[vector_index][chroma]") {
    const std::filesystem::path chroma_path = "F:/Users/myfri/agent-projects/vector_db/chroma.sqlite3";

    auto db = SqliteDb::open_memory();
    auto embedder = std::make_shared<HashingEmbedder>(384);
    VectorIndex index(db, embedder);

    SECTION("Non-existent Chroma path returns 0") {
        CHECK(index.import_chroma_db("F:/does/not/exist/chroma.sqlite3") == 0);
    }

    if (std::filesystem::exists(chroma_path)) {
        SECTION("Imports existing user Chroma database cleanly") {
            const auto imported_count = index.import_chroma_db(chroma_path);
            CHECK(imported_count > 0);

            // episodic_experiences should have been imported
            const auto exp_count = index.count("episodic_experiences");
            CHECK(exp_count > 0);

            // Dense search should return real results with non-zero similarity
            auto matches = index.search_dense("episodic_experiences", "GalagaShooter sprites collision", 3);
            CHECK(!matches.empty());
            for (const auto& match : matches) {
                CHECK(!match.id.empty());
                CHECK(!match.content.empty());
                CHECK(match.score > 0.0f);
            }
        }
    }
}

// Feature: m6-knowledge-module, Property 5: Exact Nearest Neighbor & Monotonicity
TEST_CASE("Property 5: VectorIndex Exact Nearest Neighbor and Monotonicity", "[rapidcheck]") {
    rc::prop("Query vector always scores ~1.0 against its own stored document with monotonic ordering", []() {
        auto gen_word = rc::gen::map(
            rc::gen::container<std::string>(rc::gen::inRange('a', 'z')),
            [](std::string s) { return s + "xyz"; }
        );

        const auto w1 = *gen_word;
        const auto w2 = *gen_word;
        const auto w3 = *gen_word;
        const std::string target_doc = w1 + " " + w2 + " " + w3;

        auto db = SqliteDb::open_memory();
        auto embedder = std::make_shared<HashingEmbedder>(384);
        VectorIndex index(db, embedder);

        // Insert target
        index.upsert("p5_coll", "target", target_doc, nlohmann::json::object());

        // Insert 3 distractor docs
        index.upsert("p5_coll", "d1", *gen_word + " something completely different", nlohmann::json::object());
        index.upsert("p5_coll", "d2", "entirely unrelated text about trees", nlohmann::json::object());
        index.upsert("p5_coll", "d3", "cryptography and blockchain protocols", nlohmann::json::object());

        // Search for the exact target doc
        auto results = index.search_dense("p5_coll", target_doc, 4);
        RC_ASSERT(!results.empty());

        // Top match must be target with score ~ 1.0 (unit vector dot product)
        RC_ASSERT(results[0].id == "target");
        RC_ASSERT(std::abs(results[0].score - 1.0f) < 1e-4f);

        // Monotonicity check: score[i] >= score[i+1]
        for (std::size_t i = 1; i < results.size(); ++i) {
            RC_ASSERT(results[i - 1].score >= results[i].score - 1e-6f);
        }
    });
}

