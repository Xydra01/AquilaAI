#include "aquila/core.hpp"

#include <catch2/catch_test_macros.hpp>

using namespace aquila::deps_probe;

TEST_CASE("version matches the CMake project version") {
    CHECK(aquila::version() == "0.0.1");
}

TEST_CASE("nlohmann/json parses an object") {
    CHECK(json_int(R"({"num_ctx": 6144})", "num_ctx") == 6144);
}

TEST_CASE("nlohmann/json rejects malformed input") {
    CHECK_THROWS(json_int(R"({"num_ctx": )", "num_ctx"));
}

TEST_CASE("inja renders recipe-style placeholders") {
    CHECK(inja_render("Fix {{ file }} in {{ module }}",
                      R"({"file": "main.cpp", "module": "workspace"})") ==
          "Fix main.cpp in workspace");
}

TEST_CASE("fmt formats with alignment") {
    CHECK(fmt_tokens(2048) == "  2048 tokens");
}

TEST_CASE("spdlog writes through an ostream sink") {
    const auto line = spdlog_line("hello");
    CHECK(line.find("[info] hello") == 0);
}

TEST_CASE("cpp-httplib links and knows status reasons") {
    CHECK(http_reason(404) == "Not Found");
    CHECK(http_server_constructs());
}
