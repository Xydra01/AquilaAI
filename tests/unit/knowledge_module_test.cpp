#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/modules/registry.hpp"
#include "temp_dir.hpp"

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
    CHECK(actions.size() == 7);

    SECTION("verify_research_deliverable utility gate") {
        test::TempDir tmp;
        ModuleContext tmp_ctx{.workspace_root = tmp.path(), .max_output_chars = 2000};
        KnowledgeModule km_temp(tmp_ctx);

        // 1. Missing report fails
        auto res = km_temp.execute_action("verify_research_deliverable", Json::object());
        CHECK_FALSE(res.success);
        CHECK(res.error_code == "missing_report");

        // 2. Report too brief (< 350 chars) fails
        tmp.write("research_report.md", "# Findings\nShort text.\n");
        res = km_temp.execute_action("verify_research_deliverable", Json::object());
        CHECK_FALSE(res.success);
        CHECK(res.error_code == "shallow_report");

        // 3. Report lacking citations fails
        std::string long_no_cites = "# Executive Summary\n\nThis research project investigates modern transformer attention mechanisms.\n\n## Methodology\n\nWe survey flash attention, multi-head latent attention, and sparse kernels across modern GPU clusters without any formal reference markers.\n\n## Conclusion\n\nThe efficiency of tensor computations depends heavily on memory bandwidth rather than peak FLOPs.";
        while (long_no_cites.size() < 400) {
            long_no_cites += " Hardware accelerators dictate modern neural throughput.\n";
        }
        tmp.write("research_report.md", long_no_cites);
        res = km_temp.execute_action("verify_research_deliverable", Json::object());
        CHECK_FALSE(res.success);
        CHECK(res.error_code == "missing_citations");

        // 4. Report with citations but no facts stored in FactStore fails
        std::string cited_report = "# Executive Summary\n\nRecent advances in FlashAttention-3 [Dao et al., 2024] exploit asynchronous warp specialization [1].\n\n## Architecture Findings\n\nTMA (Tensor Memory Accelerator) enables overlap between GEMM computations and global memory loads [2].\n\n## Comparative Benchmarks\n\nHardware benchmarks demonstrate a 1.8x speedup over standard FP16 kernels on NVIDIA Hopper architectures [3].";
        while (cited_report.size() < 420) {
            cited_report += " Asynchronous memory staging minimizes register pressure.\n";
        }
        tmp.write("research_report.md", cited_report);
        res = km_temp.execute_action("verify_research_deliverable", Json::object());
        CHECK_FALSE(res.success);
        CHECK(res.error_code == "empty_factstore");

        // 5. Storing fact then verifying passes!
        km_temp.execute_action("store_fact", Json{
            {"topic", "attention"},
            {"fact", "FlashAttention-3 leverages TMA and asynchronous warp specialization."}
        });
        res = km_temp.execute_action("verify_research_deliverable", Json::object());
        CHECK(res.success);
        CHECK(res.llm_facing_output.find("verified successfully") != std::string::npos);
    }

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

