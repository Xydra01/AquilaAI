#include "aquila/exec/diagnostics.hpp"
#include "aquila/json.hpp"

#include "fixtures.hpp"

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cstdio>

using namespace aquila;
namespace fs = std::filesystem;

namespace {

fs::path logs() {
    return test::fixture_dir() / "logs";
}

}  // namespace

TEST_CASE("diagnostics: real tool logs match their hand-written expectations") {
    std::size_t checked = 0;
    std::vector<fs::path> files;
    for (const auto& e : fs::directory_iterator(logs())) {
        const auto name = e.path().filename().string();
        if (name.size() > 14 && name.substr(name.size() - 14) == ".expected.json") files.push_back(e.path());
    }
    std::sort(files.begin(), files.end());
    for (const auto& file : files) {
        const auto exp = Json::parse(test::read_bytes(file));
        const auto log = test::read_bytes(logs() / exp["log"].get<std::string>());
        INFO(exp["log"].get<std::string>());
        const auto d = exec::diagnose(log);

        CHECK(d.errors == exp["errors"].get<std::size_t>());
        CHECK(d.warnings == exp["warnings"].get<std::size_t>());
        if (exp.contains("failed_targets")) CHECK(d.failed_targets == exp["failed_targets"].get<std::vector<std::string>>());
        if (exp.contains("tests")) {
            REQUIRE(d.tests.found);
            CHECK(d.tests.passed == exp["tests"]["passed"].get<std::size_t>());
            CHECK(d.tests.failed == exp["tests"]["failed"].get<std::size_t>());
            CHECK(d.tests.errors == exp["tests"]["errors"].get<std::size_t>());
            CHECK(d.tests.skipped == exp["tests"]["skipped"].get<std::size_t>());
            CHECK(d.tests.xfailed == exp["tests"]["xfailed"].get<std::size_t>());
        }
        const auto& blocks = exp["blocks"];
        REQUIRE(d.blocks.size() == blocks.size());
        for (std::size_t i = 0; i < blocks.size(); ++i) {
            INFO("block " << i);
            const auto& b = blocks[i];
            CHECK(d.blocks[i].file == b["file"].get<std::string>());
            CHECK(d.blocks[i].line == b["line"].get<std::size_t>());
            CHECK(d.blocks[i].col == b["col"].get<std::size_t>());
            CHECK(d.blocks[i].severity == b["severity"].get<std::string>());
            CHECK(d.blocks[i].code == b["code"].get<std::string>());
            CHECK(d.blocks[i].message == b["message"].get<std::string>());
            CHECK(d.blocks[i].count == b["count"].get<std::size_t>());
        }
        const auto text = exec::render(d);
        std::printf("diagnose %-28s %6zu bytes -> %5zu bytes, %zu block(s)\n", exp["log"].get<std::string>().c_str(),
                    log.size(), text.size(), d.blocks.size());
        ++checked;
    }
    CHECK(checked == 12);
}

TEST_CASE("diagnostics: pytest counts equal Python's run_tests parsing of the same output") {
    const auto counts = Json::parse(test::read_bytes(test::fixture_dir() / "python" / "workspace" / "pytest_counts.json"));
    std::size_t checked = 0;
    for (const auto& c : counts) {
        INFO(c["case"].get<std::string>());
        const auto d = exec::diagnose(test::read_bytes(logs() / c["log"].get<std::string>()));
        CHECK(d.tests.passed == c["python_passed"].get<std::size_t>());
        CHECK(d.tests.failed == c["python_failed"].get<std::size_t>());
        ++checked;
    }
    std::printf("pytest counts: %zu runs match Python's regexes\n", checked);
    CHECK(checked == 5);
}

TEST_CASE("diagnostics: render output for the template-spam log") {
    const auto d = exec::diagnose(test::read_bytes(logs() / "clang_template_spam.txt"));
    const auto text = exec::render(d);
    CHECK(text.rfind("8 error(s), 0 warning(s), 1 unique\n"
                     "1. template_spam.cpp:2:52 error: no member named 'missing' in 'A'  (x8, same error)\n", 0) == 0);
}

TEST_CASE("diagnostics: a 5000-line log is reduced to at most 5 blocks within the cap") {
    std::string log;
    for (int i = 0; i < 5000; ++i) {
        switch (i % 5) {
            case 0: log += "src/a.cpp:" + std::to_string(10 + i % 40) + ":5: error: use of undeclared identifier 'x" + std::to_string(i) + "'\n"; break;
            case 1: log += "    10 |     return x;\n"; break;
            case 2: log += "src/b.cpp(" + std::to_string(i % 7 + 1) + "): warning C4244: conversion from 'double' to 'int', possible loss of data\n"; break;
            case 3: log += "[" + std::to_string(i) + "/5000] Building CXX object x.obj\n"; break;
            default: log += "random progress noise line " + std::to_string(i) + "\n"; break;
        }
    }
    const auto d = exec::diagnose(log);
    CHECK(d.errors == 1000);
    CHECK(d.warnings == 1000);
    // Error lines sit at i % 5 == 0, so 10 + i % 40 takes 8 values; warnings cover all 7 of i % 7.
    CHECK(d.blocks.size() == 15);
    CHECK(d.blocks.front().severity == "error");
    CHECK(d.blocks.front().count == 125);  // 1000 errors over 8 lines
    const auto text = exec::render(d, 5, 1500);
    CHECK(text.find("5. ") != std::string::npos);
    CHECK(text.find("6. ") == std::string::npos);
    CHECK(text.size() <= 1500 + 20);
    CHECK(text.find("+10 more unique diagnostic(s) not shown") != std::string::npos);
    std::printf("diagnose synthetic: %zu bytes, 5000 lines -> %zu bytes\n", log.size(), text.size());
}
