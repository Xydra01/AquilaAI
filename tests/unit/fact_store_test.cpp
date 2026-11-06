#include "aquila/storage/fact_store.hpp"

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <string>

using namespace aquila::storage;

TEST_CASE("FactStore in-memory basic operations and formatting") {
    auto store = FactStore::open_memory();

    // 1. Facts
    CHECK(store.get_all_facts() == "No permanent facts stored yet.");

    std::string msg = store.store_fact("Security", "Never expose private keys in logs");
    CHECK(msg.find("Security") != std::string::npos);

    store.store_fact("Coding", "Prefer C++20 RAII over raw pointers");

    std::string all_facts = store.get_all_facts();
    CHECK(all_facts.find("=== PERMANENT SYSTEM FACTS & LORE ===") != std::string::npos);
    CHECK(all_facts.find("- [CODING]: Prefer C++20 RAII over raw pointers") != std::string::npos);
    CHECK(all_facts.find("- [SECURITY]: Never expose private keys in logs") != std::string::npos);

    auto query_res = store.query_facts("security");
    REQUIRE(query_res.size() == 1);
    CHECK(query_res[0].topic == "security");
    CHECK(query_res[0].fact == "Never expose private keys in logs");

    // 2. Scratchpad notes
    CHECK(store.get_scratchpad_notes("task-1") == "No research notes found for this task.");

    store.save_scratchpad_note("task-1", "Initial investigation started");
    store.save_scratchpad_note("task-1", "Root cause identified in parser");

    std::string notes = store.get_scratchpad_notes("task-1");
    CHECK(notes.find("=== SCRATCHPAD NOTES FOR task-1 ===") != std::string::npos);
    CHECK(notes.find("--- Note 1 ---\nInitial investigation started") != std::string::npos);
    CHECK(notes.find("--- Note 2 ---\nRoot cause identified in parser") != std::string::npos);

    // 3. Workspace summaries
    CHECK(store.get_workspace_summary("inst-1", "task-1").empty());
    store.save_workspace_summary("inst-1", "task-1", "Completed initial setup of module");
    CHECK(store.get_workspace_summary("inst-1", "task-1") == "Completed initial setup of module");

    // Upsert replaces existing summary
    store.save_workspace_summary("inst-1", "task-1", "Completed initial setup and added tests");
    CHECK(store.get_workspace_summary("inst-1", "task-1") == "Completed initial setup and added tests");
}

TEST_CASE("FactStore reads existing Python reference fact_graph.db without error") {
    const std::filesystem::path real_db_path = "F:/Users/myfri/agent-projects/Agent-Memory/fact_graph.db";
    if (!std::filesystem::exists(real_db_path)) {
        SUCCEED("Skipping real database test: file not found at " + real_db_path.string());
        return;
    }

    // Open read-only to guarantee the reference data is preserved untouched
    auto db = SqliteDb::open(real_db_path, SQLITE_OPEN_READONLY);
    REQUIRE(db.is_open());

    FactStore store(std::move(db));

    // Verify row counts match what Python produced
    auto stmt_scratch = store.db().prepare("SELECT count(*) FROM scratchpad;");
    REQUIRE(stmt_scratch.step() == true);
    const int scratch_count = stmt_scratch.column_int(0);
    CHECK(scratch_count > 0);

    auto stmt_summaries = store.db().prepare("SELECT count(*) FROM workspace_summaries;");
    REQUIRE(stmt_summaries.step() == true);
    const int summary_count = stmt_summaries.column_int(0);
    CHECK(summary_count > 0);

    // Verify get_all_facts does not crash and formats existing facts
    std::string facts = store.get_all_facts();
    CHECK(!facts.empty());
}

