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

        // 5. Storing fact then verifying passes (offline / default mode)!
        km_temp.execute_action("store_fact", Json{
            {"topic", "attention"},
            {"fact", "FlashAttention-3 leverages TMA and asynchronous warp specialization."}
        });
        res = km_temp.execute_action("verify_research_deliverable", Json::object());
        CHECK(res.success);
        CHECK(res.llm_facing_output.find("verified successfully") != std::string::npos);

        // 6. Online mode (require_urls=true) rejects placeholder-only citations without real http(s):// URLs
        res = km_temp.execute_action("verify_research_deliverable", Json{
            {"require_urls", true},
            {"grounded_urls", Json::array({"https://github.com/org/repo", "https://arxiv.org/abs/2403.05286"})}
        });
        CHECK_FALSE(res.success);
        CHECK(res.error_code == "ungrounded_citations");

        // 7. Online mode rejects hallucinated URLs that don't match any session grounded_url
        std::string hallucinated_report = cited_report +
            "\n\n## References\n- [1] https://madeup.example.invalid/a\n- [2] https://madeup.example.invalid/b\n";
        tmp.write("research_report.md", hallucinated_report);
        res = km_temp.execute_action("verify_research_deliverable", Json{
            {"require_urls", true},
            {"grounded_urls", Json::array({"https://github.com/org/repo", "https://arxiv.org/abs/2403.05286"})}
        });
        CHECK_FALSE(res.success);
        CHECK(res.error_code == "ungrounded_citations");

        // 8. Online mode passes with >= 2 distinct real URLs and >= 1 matching session URL (Option A)
        std::string grounded_report = cited_report +
            "\n\n## References\n- [1] https://arxiv.org/abs/2403.05286\n- [2] https://github.com/org/repo\n";
        tmp.write("research_report.md", grounded_report);
        res = km_temp.execute_action("verify_research_deliverable", Json{
            {"require_urls", true},
            {"grounded_urls", Json::array({"https://github.com/org/repo", "https://arxiv.org/abs/2403.05286"})}
        });
        CHECK(res.success);

        // 9. Single-source online run (e.g. localhost fixture) requires >= 1 matching URL
        std::string single_url_report = cited_report + "\n\n## References\n- [1] http://127.0.0.1:9999/explore\n";
        tmp.write("research_report.md", single_url_report);
        res = km_temp.execute_action("verify_research_deliverable", Json{
            {"require_urls", true},
            {"grounded_urls", Json::array({"http://127.0.0.1:9999/explore"})}
        });
        CHECK(res.success);

        // 10. Unexpanded TODO/TBD placeholders fail verification
        tmp.write("research_report.md", grounded_report + "\nTODO: expand section 4.\n");
        res = km_temp.execute_action("verify_research_deliverable", Json::object());
        CHECK_FALSE(res.success);
        CHECK(res.error_code == "placeholder_content");
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

        // Host visit budget separates web_search auto-scrape from explicit fetch_and_clean_url
        km->search_engine().set_mock_handler([](std::string_view) -> std::optional<std::vector<SearchResult>> {
            return std::vector<SearchResult>{
                SearchResult{"R1", "http://local.docs/overview", "s1", "mock", 1.0},
                SearchResult{"R2", "http://local.docs/overview", "s2", "mock", 0.9},
                SearchResult{"R3", "http://local.docs/overview", "s3", "mock", 0.8}
            };
        });
        CHECK(km->execute_action("web_search", Json{{"query", "overview"}, {"auto_scrape", true}}).success);
        // 4 more explicit fetches on local.docs succeed (total 5 explicit visits), 6th hits host_visit_cap fail
        for (int i = 0; i < 4; ++i) {
            CHECK(km->execute_action("fetch_and_clean_url", Json{{"url", "http://local.docs/overview"}}).success);
        }
        auto cap_res = km->execute_action("fetch_and_clean_url", Json{{"url", "http://local.docs/overview"}});
        CHECK_FALSE(cap_res.success);
        CHECK(cap_res.error_code == "host_visit_cap");
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

        // Null optional boolean must return invalid_args instead of throwing json::type_error
        auto null_bypass = km->execute_action("fetch_and_clean_url", Json{
            {"url", "http://local.docs/overview"},
            {"bypass_cache", nullptr}
        });
        CHECK(!null_bypass.success);
        CHECK(null_bypass.error_code == "invalid_args");
    }

    SECTION("search_local_docs lazily indexes workspace markdown files and ignores Agent-Tasks") {
        test::TempDir tmp;
        tmp.write("docs/overview.md", "# Aquila Notes\n\nGatedDeltaNet hybrid attention supports snapshots.\n");
        tmp.write("Agent-Tasks/fn_research_full_ledger.md", "# ACTIVE TASK LEDGER\n\nGatedDeltaNet ledger noise entry.\n");
        ModuleContext ws_ctx{.workspace_root = tmp.path(), .max_output_chars = 2000};
        KnowledgeModule km_ws(ws_ctx);

        auto res = km_ws.execute_action("search_local_docs", Json{{"query", "GatedDeltaNet snapshots"}, {"max_results", 5}});
        CHECK(res.success);
        CHECK(res.llm_facing_output.find("GatedDeltaNet") != std::string::npos);
        CHECK(res.llm_facing_output.find("Agent-Tasks") == std::string::npos);
    }
}

TEST_CASE("All builtin module action schemas are well-formed JSON Schema objects", "[registry][schema]") {
    ModuleContext ctx{.workspace_root = "", .max_output_chars = 2000};
    auto registry = ModuleRegistry::builtin();
    for (const auto& mod_id : registry.ids()) {
        auto mod = registry.create(mod_id, ctx);
        REQUIRE(mod != nullptr);
        for (const auto& act : mod->get_actions()) {
            INFO("module=" << mod_id << " action=" << act.action_name);
            REQUIRE(act.parameters_json_schema.is_object());
            CHECK(act.parameters_json_schema.value("type", std::string{}) == "object");
            if (act.parameters_json_schema.contains("properties")) {
                const auto& props = act.parameters_json_schema["properties"];
                REQUIRE(props.is_object());
                for (const auto& [k, prop_schema] : props.items()) {
                    INFO("property=" << k << " dump=" << prop_schema.dump());
                    CHECK(prop_schema.is_object());
                    if (prop_schema.is_object()) {
                        CHECK(prop_schema.contains("type"));
                    }
                }
            }
        }
    }
}

TEST_CASE("KnowledgeModule rejects binary PDF URLs with HTML guidance before burning host quota",
          "[knowledge_module]") {
    ModuleContext ctx{.workspace_root = "", .max_output_chars = 4000};
    KnowledgeModule km(ctx);

    const auto pdf_res = km.execute_action("fetch_and_clean_url", Json{
        {"url", "https://arxiv.org/pdf/2105.03310"}
    });
    CHECK_FALSE(pdf_res.success);
    CHECK(pdf_res.error_code == "fetch_error");
    CHECK(pdf_res.llm_facing_output.find("https://arxiv.org/abs/2105.03310") != std::string::npos);

    km.search_engine().set_mock_handler([](std::string_view) -> std::optional<std::vector<SearchResult>> {
        return std::vector<SearchResult>{
            SearchResult{"Paper PDF", "https://arxiv.org/pdf/2105.03310.pdf", "snippet", "mock", 10.0}
        };
    });
    const auto ws_res = km.execute_action("web_search", Json{
        {"query", "paper"},
        {"auto_scrape", true}
    });
    CHECK(ws_res.success);
    CHECK(ws_res.llm_facing_output.find("Skipped auto-scrape for binary PDF") != std::string::npos);
}

