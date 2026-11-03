#include "aquila/canvas/diff.hpp"

#include "git_oracle.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cstdio>
#include <random>
#include <vector>

using namespace aquila;

namespace {

struct Pair {
    std::string name;
    std::string old_text;
    std::string new_text;
};

const std::vector<Pair>& edge_cases() {
    static const std::vector<Pair> cases = {
        {"change middle", "a\nb\nc\nd\ne\nf\ng\nh\n", "a\nb\nc\nD\ne\nf\ng\nh\n"},
        {"insert top", "x\ny\n", "new\nx\ny\n"},
        {"append", "x\ny\n", "x\ny\nz\n"},
        {"delete all", "x\ny\n", ""},
        {"from empty", "", "x\n"},
        {"two far hunks", "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n13\n14\n15\n16\n17\n18\n19\n20\n",
         "1\nTWO\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n13\n14\n15\n16\n17\n18\nNINETEEN\n20\n"},
        {"drop final newline", "x\ny\n", "x\ny"},
        {"add final newline", "x\ny", "x\ny\n"},
        {"no final newline both, change last", "x\ny", "x\nz"},
        {"no final newline, append", "x", "x\ny\n"},
        {"crlf content", "a\r\nb\r\nc\r\n", "a\r\nB\r\nc\r\n"},
        {"unicode", "naïve\n✓ ok\n", "naïve\n✓ fine\n"},
        {"blank lines", "\n\n\n", "\n\nx\n\n"},
    };
    return cases;
}

std::string random_text(std::mt19937& rng) {
    std::uniform_int_distribution<int> lines(0, 12);
    std::uniform_int_distribution<int> word(0, 4);
    const char* words[] = {"alpha", "beta", "gamma", "", "delta"};
    std::string t;
    const int n = lines(rng);
    for (int i = 0; i < n; ++i) {
        t += words[word(rng)];
        t += '\n';
    }
    if (!t.empty() && word(rng) == 0) t.pop_back();  // sometimes no final newline
    return t;
}

}  // namespace

TEST_CASE("diff: equal texts give an empty diff") {
    CHECK(diff::unified("a\n", "a\n", "a/x", "b/x").empty());
}

TEST_CASE("diff: known output for a one-line change") {
    CHECK(diff::unified("a\nb\nc\n", "a\nB\nc\n", "a/f.txt", "b/f.txt") ==
          "--- a/f.txt\n+++ b/f.txt\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n");
}

TEST_CASE("diff: apply(unified(a, b)) == b for edge cases and 2000 random pairs") {
    std::size_t checked = 0;
    for (const auto& c : edge_cases()) {
        INFO(c.name);
        std::string err;
        const auto patch = diff::unified(c.old_text, c.new_text, "a/f", "b/f");
        const auto applied = diff::apply(c.old_text, patch, err);
        INFO(patch << err);
        REQUIRE(applied.has_value());
        CHECK(*applied == c.new_text);
        ++checked;
    }
    std::mt19937 rng(20261103);
    for (int i = 0; i < 2000; ++i) {
        const auto a = random_text(rng);
        const auto b = random_text(rng);
        const auto patch = diff::unified(a, b, "a/f", "b/f");
        if (a == b) {
            CHECK(patch.empty());
            continue;
        }
        std::string err;
        const auto applied = diff::apply(a, patch, err);
        INFO("a=[" << a << "] b=[" << b << "]\n" << patch << err);
        REQUIRE(applied.has_value());
        CHECK(*applied == b);
        ++checked;
    }
    std::printf("diff round-trip: %zu pairs\n", checked);
}

TEST_CASE("diff: git apply (outside oracle) reproduces the new bytes") {
    std::size_t checked = 0;
    for (const auto& c : edge_cases()) {
        INFO(c.name);
        const bool create = c.old_text.empty();
        const auto patch = diff::unified(c.old_text, c.new_text, create ? "/dev/null" : "a/f.txt", "b/f.txt");
        if (c.new_text.empty()) continue;  // git treats an emptied file as needing deletion headers
        const auto result = test::git_apply("f.txt", c.old_text, patch, create);
        INFO(patch);
        REQUIRE(result.has_value());
        CHECK(*result == c.new_text);
        ++checked;
    }
    std::printf("git apply oracle: %zu diffs applied byte-identically\n", checked);
}

TEST_CASE("diff: apply rejects mismatched context and malformed patches") {
    std::string err;
    CHECK_FALSE(diff::apply("a\nb\n", "@@ -1,2 +1,2 @@\n a\n-x\n+y\n", err).has_value());
    CHECK(err.find("removed line mismatch at line 2") != std::string::npos);
    CHECK_FALSE(diff::apply("a\n", "no hunks here\n", err).has_value());
    CHECK(err == "patch has no hunks");
    CHECK_FALSE(diff::apply("a\n", "@@ -5,1 +5,1 @@\n-a\n+b\n", err).has_value());
}
