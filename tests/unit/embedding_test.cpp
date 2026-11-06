#include "aquila/knowledge/embedding.hpp"

#include <catch2/catch_test_macros.hpp>
#include <nlohmann/json.hpp>
#include <rapidcheck/catch.h>

#include <cmath>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

using namespace aquila::knowledge;

TEST_CASE("HashingEmbedder matches Python reference oracle fixtures") {
    const std::filesystem::path fixture_path = std::string(AQUILA_FIXTURE_DIR) + "/embedding_oracle.json";
    REQUIRE(std::filesystem::exists(fixture_path));

    std::ifstream file(fixture_path);
    REQUIRE(file.is_open());
    auto j = nlohmann::json::parse(file);
    REQUIRE(j.is_array());

    HashingEmbedder embedder(384);

    for (const auto& item : j) {
        std::string input = item["input"];
        auto py_tokens = item["tokens"].get<std::vector<std::string>>();
        auto py_vec = item["vector"].get<std::vector<float>>();

        // 1. Verify token extraction parity
        auto cpp_tokens = embedder.extract_tokens(input);
        CHECK(cpp_tokens == py_tokens);

        // 2. Verify embedding vector parity
        auto cpp_vec = embedder.embed(input);
        REQUIRE(cpp_vec.size() == 384);

        if (py_tokens.empty()) {
            // Both must be all zeros
            for (float val : cpp_vec) {
                CHECK(val == 0.0f);
            }
        } else {
            // Compute cosine similarity (dot product of unit vectors)
            double dot = 0.0;
            for (std::size_t i = 0; i < 384; ++i) {
                dot += static_cast<double>(cpp_vec[i]) * static_cast<double>(py_vec[i]);
            }
            CHECK(dot >= 0.999999);
        }
    }
}

// Feature: m6-knowledge-module, Property 4: Embedder Output Invariants
// For any string, dimension is 384, no NaNs/Infs, norm is 1.0 (or 0 for empty tokens), and deterministic.
TEST_CASE("Property 4: HashingEmbedder output invariants", "[rapidcheck]") {
    rc::prop("Embedder output is normalized and finite", [](const std::string& input) {
        HashingEmbedder embedder(384);
        RC_ASSERT(embedder.dimension() == 384);

        auto vec1 = embedder.embed(input);
        auto vec2 = embedder.embed(input);

        RC_ASSERT(vec1.size() == 384);
        RC_ASSERT(vec1 == vec2);  // Determinism

        double sum_sq = 0.0;
        for (float v : vec1) {
            RC_ASSERT(!std::isnan(v));
            RC_ASSERT(!std::isinf(v));
            sum_sq += static_cast<double>(v) * static_cast<double>(v);
        }

        auto tokens = embedder.extract_tokens(input);
        if (tokens.empty()) {
            RC_ASSERT(sum_sq == 0.0);
        } else {
            double norm = std::sqrt(sum_sq);
            RC_ASSERT(std::abs(norm - 1.0) < 1e-4);
        }
    });
}

