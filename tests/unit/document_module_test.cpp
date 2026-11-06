#include "aquila/document/document_module.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>
#include <fstream>

using namespace aquila;
using namespace aquila::document;

TEST_CASE("document: header normalization and redundant heading stripping", "[document]") {
    CHECK(normalize_section_header("## 1. Executive Summary ##") == "Executive Summary");
    CHECK(normalize_section_header("  3) Methodology  ") == "Methodology");
    CHECK(normalize_section_header("### Plain Header") == "Plain Header");
    CHECK(normalize_section_header("") == "Untitled Section");
    CHECK(normalize_section_header("###") == "Untitled Section");

    // Redundant header stripping
    CHECK(strip_redundant_leading_heading("# Executive Summary\nActual body content", "Executive Summary") == "Actual body content");
    CHECK(strip_redundant_leading_heading("## 1. Executive Summary\nLine 1\nLine 2", "1. Executive Summary") == "Line 1\nLine 2");
    CHECK(strip_redundant_leading_heading("Just normal text\nSecond line", "Overview") == "Just normal text\nSecond line");
    CHECK(strip_redundant_leading_heading("", "Overview") == "");
}

TEST_CASE("document: full document module workflow", "[document]") {
    test::TempDir tmp;
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();

    DocumentModule doc(ctx);
    CHECK_FALSE(doc.has_active_draft());

    // 1. Calling write_section before init fails with no_active_document
    auto res = doc.execute_action("write_section", Json::object({
        {"section_header", "Intro"},
        {"content", "Some content"}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "no_active_document");

    // 2. Initialize document
    res = doc.execute_action("init_document", Json::object({
        {"title", "Aquila Rebuild Architecture"},
        {"synopsis", "Technical blueprint for C++20 re-architecture."}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("Aquila Rebuild Architecture") != std::string::npos);
    CHECK(doc.has_active_draft());
    CHECK(std::filesystem::exists(doc.active_draft_file()));

    // 3. Write section 1
    res = doc.execute_action("write_section", Json::object({
        {"section_header", "1. Core Design"},
        {"content", "Strict single-threaded deterministic state engine."}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("Core Design") != std::string::npos);
    CHECK(res.llm_facing_output.find("added") != std::string::npos);

    // 4. Write section 2
    res = doc.execute_action("write_section", Json::object({
        {"section_header", "2. Memory Architecture"},
        {"content", "SQLite amalgamation backed fact graph and vector indices."}
    }));
    REQUIRE(res.success);
    CHECK(doc.draft().sections.size() == 2);

    // 5. Overwrite section 1
    res = doc.execute_action("write_section", Json::object({
        {"section_header", "1. Core Design"},
        {"content", "## Core Design\nStrict single-threaded deterministic engine with zero leaks."}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("OVERWRITTEN") != std::string::npos);
    CHECK(doc.draft().sections.size() == 2);
    // Verified redundant heading was stripped
    CHECK(doc.draft().sections[0].content == "Strict single-threaded deterministic engine with zero leaks.");

    // 6. Read outline
    res = doc.execute_action("read_outline", Json::object());
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("OUTLINE FOR: Aquila Rebuild Architecture") != std::string::npos);
    CHECK(res.llm_facing_output.find("1. Core Design") != std::string::npos);
    CHECK(res.llm_facing_output.find("2. Memory Architecture") != std::string::npos);

    // 7. Revise selection
    res = doc.execute_action("revise_selection", Json::object({
        {"section_header", "Core Design"},
        {"new_content", "Polished core engine description."}
    }));
    REQUIRE(res.success);
    CHECK(doc.draft().sections[0].content == "Polished core engine description.");

    // 8. Snapshot round-trip
    const auto snapshot = doc.export_state_snapshot();
    CHECK(snapshot["active"] == true);
    CHECK(snapshot["title"] == "Aquila Rebuild Architecture");
    CHECK(snapshot["section_count"] == 2);

    DocumentModule doc2(ctx);
    doc2.restore_state_snapshot(snapshot);
    CHECK(doc2.has_active_draft());
    CHECK(doc2.draft().title == "Aquila Rebuild Architecture");
    CHECK(doc2.draft().sections.size() == 2);

    // 9. Compile document
    res = doc.execute_action("compile_document", Json::object({
        {"file_name", "architecture_report.md"}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("SUCCESS") != std::string::npos);

    // Verify active draft is cleared
    CHECK_FALSE(doc.has_active_draft());
    CHECK_FALSE(std::filesystem::exists(doc.active_draft_file()));

    // Verify compiled markdown file on disk
    const auto compiled_file = doc.drafts_dir() / "architecture_report.md";
    REQUIRE(std::filesystem::exists(compiled_file));
    std::ifstream in(compiled_file);
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    CHECK(content.find("# Aquila Rebuild Architecture") != std::string::npos);
    CHECK(content.find("## Core Design") != std::string::npos);
    CHECK(content.find("Polished core engine description.") != std::string::npos);
    CHECK(content.find("## Memory Architecture") != std::string::npos);
}

