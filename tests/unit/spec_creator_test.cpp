// tests/unit/spec_creator_test.cpp
#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/agent/spec_creator.hpp"
#include "aquila/inference/backend.hpp"
#include "aquila/json.hpp"
#include "aquila/modules/registry.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <fstream>
#include <string>

using namespace aquila;
using aquila::test::TempDir;

namespace {

class SpecMockBackend final : public IInferenceBackend {
public:
    void append(const Message& msg) override {
        messages_.push_back(msg);
    }
    std::size_t mark_checkpoint() const override { return messages_.size(); }
    void rollback_to(std::size_t cp) override { messages_.resize(cp); }
    GenerationResult generate(const GenerationParams&,
                              const TokenCallback& on_token) override {
        GenerationResult res;
        res.ok = true;
        res.content = R"(# Task Specification: Advanced Exoplanet Biosignature Survey

## 1. Objective & Scope
Conduct systematic investigation of exoplanet atmospheric spectra from 2024-2026 observations.

## 2. Technical Context & Strategy
Focus on LHS 1140 b, TRAPPIST-1 e, and K2-18 b using SearXNG web search.

## 3. Key Deliverables & Validation Criteria
Final report in research_report.md with Executive Summary, Key Findings, Detailed Analysis, and References.

## 4. Execution Milestones & Task Ledger
Detailed milestones for execution:
```json:milestones
[
  {"id": "step_1", "description": "Search for JWST atmospheric spectroscopy data on LHS 1140 b and TRAPPIST-1 e"},
  {"id": "step_2", "description": "Extract molecular absorption bands (H2O, CH4, CO2) and record physical parameters"},
  {"id": "step_3", "description": "Store verified parameters into KnowledgeModule using store_fact"}
]
```

## 5. Constraints & Exit Gate Checklist
Strict adherence to exit gate rules.
)";
        res.completion_tokens = 240;
        if (on_token) {
            on_token(res.content, "");
        }
        return res;
    }
    ComputeProfile active_profile() const noexcept override {
        return ComputeProfile::cpu_low_spec_edge;
    }
    bool supports_kv_reuse() const noexcept override { return false; }
    std::size_t message_count() const noexcept { return messages_.size(); }

private:
    std::vector<Message> messages_;
};

}  // namespace

TEST_CASE("spec_creator: domain grounding context inspection", "[spec_creator]") {
    TempDir tmp;
    const auto ws = tmp.path();

    SECTION("dev recipe identifies existing repo and build files") {
        std::filesystem::create_directories(ws / ".git");
        {
            std::ofstream out(ws / "CMakeLists.txt");
            out << "cmake_minimum_required(VERSION 3.20)\nproject(TestProject)\n";
        }
        {
            std::ofstream out(ws / "README.md");
            out << "# Test Project\nThis is a sample project for testing.\n";
        }
        std::filesystem::create_directories(ws / "src");
        {
            std::ofstream out(ws / "src" / "main.cpp");
            out << "int main() { return 0; }\n";
        }

        const auto dev_recipe = fn_dev_implement_recipe();
        auto ctx = SpecCreator::inspect_grounding_context(dev_recipe, ws);

        CHECK(ctx.domain == "dev");
        CHECK(ctx.is_existing_repo == true);
        CHECK(ctx.build_system_or_corpus_info.find("CMake") != std::string::npos);
        CHECK(ctx.build_system_or_corpus_info.find("README Overview") != std::string::npos);
        CHECK(ctx.project_structure_summary.find("src/") != std::string::npos);
    }

    SECTION("research recipe identifies research domain and documents") {
        std::filesystem::create_directories(ws / "docs");
        {
            std::ofstream out(ws / "docs" / "background.md");
            out << "# Background Notes\nPrior exoplanet research.\n";
        }

        const auto res_recipe = fn_research_full_recipe();
        auto ctx = SpecCreator::inspect_grounding_context(res_recipe, ws);

        CHECK(ctx.domain == "research");
        CHECK(ctx.project_structure_summary.find("docs/background.md") != std::string::npos);
    }
}

TEST_CASE("spec_creator: title extraction and milestone parsing with exit gate enrichment", "[spec_creator]") {
    const auto recipe = fn_research_full_recipe();

    SECTION("extracts clean title from markdown") {
        const std::string md = "# Task Specification: Exoplanet Atmosphere Survey 2026\n\n## 1. Objective\n...";
        CHECK(SpecCreator::extract_title(md) == "Exoplanet Atmosphere Survey 2026");
    }

    SECTION("parses json:milestones block and enriches mandatory exit gates") {
        const std::string md = R"(# Task Specification: Sample
## 4. Execution Milestones
```json:milestones
[
  {"id": "step_1", "description": "Search NASA Exoplanet Archive"},
  {"id": "step_2", "description": "Extract transmission spectra"}
]
```
)";
        auto steps = SpecCreator::parse_milestones(md, recipe);
        REQUIRE(steps.size() >= 4);
        CHECK(steps[0].description == "Search NASA Exoplanet Archive");
        CHECK(steps[1].description == "Extract transmission spectra");

        // Enriched mandatory exit gates (Option B)
        bool has_ledger_step = false;
        bool has_complete_step = false;
        for (const auto& st : steps) {
            if (st.description.find("update_task_ledger") != std::string::npos) {
                has_ledger_step = true;
            }
            if (st.description.find("complete_recipe") != std::string::npos) {
                has_complete_step = true;
            }
        }
        CHECK(has_ledger_step);
        CHECK(has_complete_step);

        // Normalized IDs
        CHECK(steps[0].id == "step_1");
        CHECK(steps[1].id == "step_2");
        CHECK(steps.back().id == "step_" + std::to_string(steps.size()));
    }
}

TEST_CASE("spec_creator: workspace diagnostic archival", "[spec_creator]") {
    TempDir tmp;
    TaskSpec spec;
    spec.task_id = "fn_research_full";
    spec.timestamp = "20261120_120000";
    spec.title = "Exoplanet Biosignatures";
    spec.markdown_spec = "# Task Specification: Exoplanet Biosignatures\n\nFull details here.\n";

    auto saved = SpecCreator::save_spec_to_workspace(spec, tmp.path());
    CHECK(std::filesystem::exists(saved));
    CHECK(saved.filename().string() == "20261120_120000_fn_research_full_spec.md");

    // Also check latest_spec.md copy
    const auto latest = tmp.path() / "specs" / "latest_spec.md";
    CHECK(std::filesystem::exists(latest));

    std::ifstream in(latest);
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    CHECK(content.find("Exoplanet Biosignatures") != std::string::npos);
}

TEST_CASE("spec_creator: generate_spec with mock backend and rollback preservation", "[spec_creator]") {
    TempDir tmp;
    SpecMockBackend backend;

    SpecCreatorOptions opts;
    opts.user_prompt = "Analyze exoplanet atmospheres";
    opts.recipe = fn_research_full_recipe();
    opts.workspace_root = tmp.path();
    opts.include_workspace_grounding = true;

    TaskSpec spec = SpecCreator::generate_spec(backend, opts);

    CHECK(spec.title == "Advanced Exoplanet Biosignature Survey");
    CHECK(spec.domain == "research");
    CHECK(spec.objective == "Analyze exoplanet atmospheres");
    REQUIRE(spec.milestones.size() >= 5);
    CHECK(spec.milestones[0].description.find("Search for JWST") != std::string::npos);

    // Rollback check: backend messages must be completely rolled back to initial state (0 messages)
    CHECK(backend.message_count() == 0);

    // File check: spec must be archived in specs/
    CHECK(std::filesystem::exists(spec.saved_path));
}

TEST_CASE("spec_creator: TaskSpec JSON serialization round-trip", "[spec_creator]") {
    TaskSpec spec;
    spec.task_id = "fn_dev_implement";
    spec.timestamp = "20261120_123456";
    spec.title = "Refactor JSON parser";
    spec.objective = "Implement UTF-8 safety";
    spec.domain = "dev";
    spec.markdown_spec = "# Spec Content\nDetails...";
    spec.target_deliverables = {"src/json.cpp", "include/json.hpp"};
    spec.synthesis_tokens = 350;

    LedgerStep s1;
    s1.id = "step_1";
    s1.description = "Add truncate_utf8 function";
    s1.status = LedgerStepStatus::pending;
    spec.milestones.push_back(s1);

    Json j;
    to_json(j, spec);

    TaskSpec roundtrip;
    from_json(j, roundtrip, "/task_spec");

    CHECK(roundtrip.task_id == spec.task_id);
    CHECK(roundtrip.timestamp == spec.timestamp);
    CHECK(roundtrip.title == spec.title);
    CHECK(roundtrip.objective == spec.objective);
    CHECK(roundtrip.domain == spec.domain);
    CHECK(roundtrip.markdown_spec == spec.markdown_spec);
    CHECK(roundtrip.target_deliverables == spec.target_deliverables);
    CHECK(roundtrip.synthesis_tokens == spec.synthesis_tokens);
    REQUIRE(roundtrip.milestones.size() == 1);
    CHECK(roundtrip.milestones[0].id == "step_1");
    CHECK(roundtrip.milestones[0].description == "Add truncate_utf8 function");
}

