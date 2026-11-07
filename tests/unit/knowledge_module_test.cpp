#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/modules/registry.hpp"

#include <catch2/catch_test_macros.hpp>

using namespace aquila;
using namespace aquila::knowledge;

TEST_CASE("KnowledgeModule registration and action dispatch", "[knowledge_module]") {
    ModuleContext ctx{.workspace_root = "", .max_output_chars = 2000};
    auto registry = ModuleRegistry::builtin();

    REQUIRE(registry.contains("KnowledgeModule"));
    auto mod_ptr = registry.create("KnowledgeModule", ctx);
    REQUIRE(mod_ptr != nullptr);
    CHECK(mod_ptr->module_id() == "KnowledgeModule");

    auto* km = dynamic_cast<KnowledgeModule*>(mod_ptr.get());
    REQUIRE(km != nullptr);

    auto actions = km->get_actions();
    CHECK(actions.size() == 6);

    SECTION("store_fact and get_all_facts lifecycle") {
        auto res1 = km->execute_action("store_fact", Json{
            {"topic", "rebuild"},
            {"fact", "Aquila was rewritten in C++20 with zero raw owning pointers."}
        });
        CHECK(res1.success);
        CHECK(res1.llm_facing_output.find("Fact securely stored under topic 'rebuild'") != std::string::npos);

        auto res2 = km->execute_action("get_all_facts", Json::object());
        CHECK(res2.success);
        CHECK(res2.llm_facing_output.find("- [REBUILD]: Aquila was rewritten in C++20") != std::string::npos);
    }

    SECTION("fetch_and_clean_url via mock fetcher and error handling") {
        km->fetcher().set_mock_handler([](std::string_view url) -> std::optional<FetchResponse> {
            if (url == "http://local.docs/overview") {
                return FetchResponse{
                    .status_code = 200,
                    .content_type = "text/html",
                    .body = "<html><title>Docs</title><body><h1>Overview</h1><p>Doc body</p></body></html>",
                    .final_url = "http://local.docs/overview"
                };
            }
            return std::nullopt;
        });

        auto res = km->execute_action("fetch_and_clean_url", Json{
            {"url", "http://local.docs/overview"}
        });
        CHECK(res.success);
        CHECK(res.llm_facing_output.find("Title: Docs") != std::string::npos);
        CHECK(res.llm_facing_output.find("Doc body") != std::string::npos);

        // Fetching uncached/unmocked invalid url returns typed failed ActionResult without throwing
        auto fail_res = km->execute_action("fetch_and_clean_url", Json{
            {"url", "http://invalid.local.domain.doesnotexist.fail/test"}
        });
        CHECK(!fail_res.success);
        CHECK(fail_res.error_code == "fetch_error");
    }

    SECTION("search_local_docs returns formatted documentation") {
        km->doc_index().index_document("docs/test.md", "# Guide\n\n## SQLite\nSQLite RAII handles.");
        auto res = km->execute_action("search_local_docs", Json{
            {"query", "SQLite handles"},
            {"max_results", 1}
        });
        CHECK(res.success);
        CHECK(res.llm_facing_output.find("SQLite RAII handles") != std::string::npos);
    }

    SECTION("recall_experiences recalls seeded episodic vectors") {
        km->vectors().upsert("episodic_experiences", "exp1", "Fixed collision bug in GalagaShooter sprites",
                             Json{{"task", "galaga_fix"}, {"date", "2026-05-01"}});

        auto res = km->execute_action("recall_experiences", Json{
            {"query", "GalagaShooter collision sprites"}
        });
        CHECK(res.success);
        CHECK(res.llm_facing_output.find("Fixed collision bug") != std::string::npos);
        CHECK(res.llm_facing_output.find("galaga_fix") != std::string::npos);
    }

    SECTION("State snapshot export and restoration") {
        km->execute_action("store_fact", Json{
            {"topic", "persistence"},
            {"fact", "Snapshots restore long-term facts faithfully."}
        });

        auto snapshot = km->export_state_snapshot();
        CHECK(snapshot.contains("facts"));
        CHECK(snapshot["facts"].size() == 1);

        // Create fresh second module
        KnowledgeModule km2(ctx);
        CHECK(km2.execute_action("get_all_facts", Json::object()).llm_facing_output == "No permanent facts stored yet.");

        km2.restore_state_snapshot(snapshot);
        auto restored = km2.execute_action("get_all_facts", Json::object());
        CHECK(restored.llm_facing_output.find("Snapshots restore long-term facts faithfully.") != std::string::npos);
    }

    SECTION("Bad LLM input validation") {
        auto bad_act = km->execute_action("non_existent_action", Json::object());
        CHECK(!bad_act.success);
        CHECK(bad_act.error_code == "unknown_action");

        // Missing required property 'fact'
        auto bad_args = km->execute_action("store_fact", Json{{"topic", "test"}});
        CHECK(!bad_args.success);
        CHECK(bad_args.error_code == "invalid_args");
    }
}

