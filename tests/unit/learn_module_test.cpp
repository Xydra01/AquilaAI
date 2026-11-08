#include "aquila/learn/learn_module.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>
#include <fstream>

using namespace aquila;
using namespace aquila::learn;

TEST_CASE("learn: syllabus structure validation hierarchy", "[learn]") {
    // 1. Less than 8 nodes rejected
    std::vector<SyllabusNode> shallow = {
        SyllabusNode{"root", "Intro", std::nullopt, 0, 0, 0, std::nullopt},
        SyllabusNode{"u1", "Unit 1", "root", 1, 0, 0, std::nullopt},
        SyllabusNode{"u2", "Unit 2", "root", 2, 0, 0, std::nullopt}
    };
    auto [v1, r1] = validate_syllabus_structure(shallow);
    CHECK_FALSE(v1);
    CHECK(r1.find("Need at least 8 learning units") != std::string::npos);

    // 2. 8 nodes but less than 5 children rejected
    std::vector<SyllabusNode> flat;
    for (int i = 0; i < 8; ++i) {
        flat.push_back(SyllabusNode{"root" + std::to_string(i), "Title " + std::to_string(i), std::nullopt, i, 0, 0, std::nullopt});
    }
    auto [v2, r2] = validate_syllabus_structure(flat);
    CHECK_FALSE(v2);
    CHECK(r2.find("Need at least 5 sub-units with parent_id") != std::string::npos);

    // 3. Hierarchical tree with 1 root, 2 modules, 6 lessons passes
    std::vector<SyllabusNode> tree;
    tree.push_back(SyllabusNode{"root", "C++ Systems Programming", std::nullopt, 0, 0, 0, std::nullopt});
    tree.push_back(SyllabusNode{"m1", "Module 1: Concurrency", "root", 1, 0, 0, std::nullopt});
    tree.push_back(SyllabusNode{"m2", "Module 2: Memory", "root", 2, 0, 0, std::nullopt});
    for (int i = 1; i <= 3; ++i) {
        tree.push_back(SyllabusNode{"m1_l" + std::to_string(i), "Lesson " + std::to_string(i), "m1", i, 0, 0, std::nullopt});
        tree.push_back(SyllabusNode{"m2_l" + std::to_string(i), "Lesson " + std::to_string(i), "m2", i, 0, 0, std::nullopt});
    }
    auto [v3, r3] = validate_syllabus_structure(tree);
    CHECK(v3);
    CHECK(r3.empty());
}

TEST_CASE("learn: full course and mastery workflow", "[learn]") {
    test::TempDir tmp;
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();

    LearnModule mod(ctx);
    CHECK_FALSE(mod.has_active_course());

    // 1. Calling write_syllabus before course creation fails
    auto res = mod.execute_action("write_syllabus", Json::object({{"content", "[]"}}));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "no_active_course");

    // 2. Create course
    res = mod.execute_action("create_or_load_course", Json::object({
        {"course_id", "cs101-cpp"},
        {"title", "Modern C++ Systems"},
        {"topic", "C++20 agent runtime development"},
        {"instance_id", "inst_alpha"}
    }));
    REQUIRE(res.success);
    CHECK(mod.has_active_course());
    CHECK(mod.course().title == "Modern C++ Systems");
    CHECK(std::filesystem::exists(mod.course_dir() / "course.json"));

    // 3. Write invalid syllabus (shallow)
    Json shallow_nodes = Json::array({
        Json::object({{"id", "root"}, {"title", "Root"}}),
        Json::object({{"id", "u1"}, {"title", "Unit 1"}, {"parent_id", "root"}})
    });
    res = mod.execute_action("write_syllabus", Json::object({
        {"content", shallow_nodes.dump()}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "quality_gate_failed");

    // 4. Write valid syllabus with markdown code fences (unwrapping test)
    Json tree_nodes = Json::array();
    tree_nodes.push_back(Json::object({{"id", "root"}, {"title", "C++ Programming"}}));
    tree_nodes.push_back(Json::object({{"id", "m1"}, {"title", "Module 1"}, {"parent_id", "root"}}));
    tree_nodes.push_back(Json::object({{"id", "m2"}, {"title", "Module 2"}, {"parent_id", "root"}}));
    for (int i = 1; i <= 6; ++i) {
        tree_nodes.push_back(Json::object({
            {"id", "lesson_" + std::to_string(i)},
            {"title", "Lesson " + std::to_string(i)},
            {"parent_id", (i <= 3 ? "m1" : "m2")},
            {"mastery_tier", 0}
        }));
    }
    const std::string fenced = "```json\n" + tree_nodes.dump(2) + "\n```";
    res = mod.execute_action("write_syllabus", Json::object({
        {"content", fenced}
    }));
    REQUIRE(res.success);
    CHECK(std::filesystem::exists(mod.syllabus_file()));
    CHECK(mod.syllabus().nodes.size() == 9);

    // 5. Finalize course
    res = mod.execute_action("finalize_course", Json::object());
    REQUIRE(res.success);
    CHECK(mod.course().build_complete);
    CHECK(mod.syllabus().status == "ready");

    // 6. Generate assessment
    res = mod.execute_action("generate_assessment", Json::object({
        {"node_id", "lesson_1"},
        {"questions", Json::array({"Explain RAII."})}
    }));
    REQUIRE(res.success);
    CHECK(std::filesystem::exists(mod.assessments_dir() / "lesson_1_assessment.json"));

    // 7. Record result and verify mastery advancement
    CHECK(mod.syllabus().nodes[3].id == "lesson_1");
    CHECK(mod.syllabus().nodes[3].mastery_tier == 0);
    res = mod.execute_action("record_result", Json::object({
        {"node_id", "lesson_1"},
        {"passed", true},
        {"score", 0.95}
    }));
    REQUIRE(res.success);
    CHECK(mod.syllabus().nodes[3].mastery_tier == 1);

    // 8. Snapshot round-trip
    const auto snapshot = mod.export_state_snapshot();
    CHECK(snapshot["has_active_course"] == true);
    CHECK(snapshot["course_id"] == "cs101-cpp");
    CHECK(snapshot["build_complete"] == true);
    CHECK(snapshot["node_count"] == 9);

    LearnModule mod2(ctx);
    mod2.restore_state_snapshot(snapshot);
    CHECK(mod2.has_active_course());
    CHECK(mod2.course().title == "Modern C++ Systems");
    CHECK(mod2.syllabus().status == "ready");
    CHECK(mod2.syllabus().nodes[3].mastery_tier == 1);
}

TEST_CASE("learn: notebooklm archive ingestion and grounded search", "[learn]") {
    test::TempDir tmp;
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();

    LearnModule mod(ctx);

    // 1. Create a course
    auto res = mod.execute_action("create_or_load_course", Json::object({
        {"course_id", "ai-systems-2026"},
        {"title", "Autonomous AI Systems Architecture"},
        {"topic", "Agent loops and deterministic state"}
    }));
    REQUIRE(res.success);

    // 2. Add text source directly
    res = mod.execute_action("add_archive_source", Json::object({
        {"name", "Architecture Design Doc"},
        {"content", "# Core Loop\n\nThe agent uses a deterministic exit gate protocol.\n\n## KV Cache Management\n\nKV rollback preserves token KV slots to prevent latency spikes."}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("Added source 'Architecture Design Doc'") != std::string::npos);

    // 3. Ingest a workspace file
    const auto file_path = tmp.path() / "syllabus_notes.txt";
    {
        std::ofstream out(file_path);
        out << "Module 1 covers memory models.\nModule 2 covers concurrent execution pipelines.";
    }
    res = mod.execute_action("ingest_archive_file", Json::object({
        {"file_path", "syllabus_notes.txt"},
        {"name", "Syllabus Notes"}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("Ingested file 'Syllabus Notes'") != std::string::npos);

    // 4. List archive sources
    res = mod.execute_action("list_archive_sources", Json::object());
    REQUIRE(res.success);
    Json list_json = Json::parse(res.llm_facing_output);
    CHECK(list_json["sources_count"] == 2);
    CHECK(list_json["total_tokens"] > 0);

    // 5. Grounded archive search
    res = mod.execute_action("search_archive", Json::object({
        {"query", "KV rollback cache"}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("Source: Architecture Design Doc") != std::string::npos);
    CHECK(res.llm_facing_output.find("KV rollback preserves token KV slots") != std::string::npos);

    // 6. Grounded search for non-matching query
    res = mod.execute_action("search_archive", Json::object({
        {"query", "astrophysics quantum tunneling"}
    }));
    REQUIRE(res.success);
    CHECK(res.llm_facing_output.find("0 matching passages found") != std::string::npos);
}

TEST_CASE("learn: verify_course_quality utility gates", "[learn]") {
    test::TempDir tmp;
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();

    LearnModule mod(ctx);

    // 1. Calling before creating course fails
    auto res = mod.execute_action("verify_course_quality", Json::object());
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "no_active_course");

    mod.execute_action("create_or_load_course", Json::object({
        {"course_id", "cs102"},
        {"title", "Data Structures"}
    }));

    // 2. Calling before finalize fails
    res = mod.execute_action("verify_course_quality", Json::object({
        {"require_finalized", true}
    }));
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "course_not_finalized");

    // 3. Write syllabus with duplicate titles
    std::string dup_syllabus = R"({
        "nodes": [
            {"id": "root", "title": "Root Topic", "order": 0},
            {"id": "u1", "title": "Arrays and Vectors", "parent_id": "root", "order": 1},
            {"id": "u2", "title": "Arrays and Vectors", "parent_id": "root", "order": 2},
            {"id": "u3", "title": "Hash Tables", "parent_id": "root", "order": 3},
            {"id": "u4", "title": "Binary Trees", "parent_id": "root", "order": 4},
            {"id": "u5", "title": "Graph Algorithms", "parent_id": "root", "order": 5},
            {"id": "u6", "title": "Dynamic Programming", "parent_id": "root", "order": 6},
            {"id": "u7", "title": "Disjoint Sets", "parent_id": "root", "order": 7}
        ]
    })";
    mod.execute_action("write_syllabus", Json::object({{"content", dup_syllabus}}));
    mod.execute_action("finalize_course", Json::object());

    res = mod.execute_action("verify_course_quality", Json::object());
    CHECK_FALSE(res.success);
    CHECK(res.error_code == "duplicate_unit_title");

    // 4. Write valid syllabus with distinct titles
    std::string valid_syllabus = R"({
        "nodes": [
            {"id": "root", "title": "Advanced Data Structures and Algorithms", "order": 0},
            {"id": "u1", "title": "Sequential Containers and Iterators", "parent_id": "root", "order": 1},
            {"id": "u2", "title": "Associative Maps and Hash Sets", "parent_id": "root", "order": 2},
            {"id": "u3", "title": "Self-Balancing Search Trees", "parent_id": "root", "order": 3},
            {"id": "u4", "title": "Priority Queues and Heaps", "parent_id": "root", "order": 4},
            {"id": "u5", "title": "Shortest Paths and MST Graphs", "parent_id": "root", "order": 5},
            {"id": "u6", "title": "Dynamic Programming Formulations", "parent_id": "root", "order": 6},
            {"id": "u7", "title": "Disjoint Set Union Find", "parent_id": "root", "order": 7}
        ]
    })";
    mod.execute_action("write_syllabus", Json::object({{"content", valid_syllabus}}));
    mod.execute_action("finalize_course", Json::object());

    res = mod.execute_action("verify_course_quality", Json::object());
    CHECK(res.success);
    CHECK(res.llm_facing_output.find("verified successfully") != std::string::npos);
}


