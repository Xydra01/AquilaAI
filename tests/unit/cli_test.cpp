// tests/unit/cli_test.cpp
#include "cli_app.hpp"

#include "aquila/core.hpp"
#include "aquila/inference/backend.hpp"

#include <catch2/catch_test_macros.hpp>

#include <sstream>
#include <string>

namespace {

class CliMockBackend final : public aquila::IInferenceBackend {
public:
    void append(const aquila::Message& msg) override {
        messages_.push_back(msg);
    }
    std::size_t mark_checkpoint() const override { return messages_.size(); }
    void rollback_to(std::size_t cp) override { messages_.resize(cp); }
    aquila::GenerationResult generate(const aquila::GenerationParams&,
                                      const aquila::TokenCallback& on_token) override {
        aquila::GenerationResult res;
        res.ok = true;
        // Output complete_recipe action
        res.content = R"({"thought":"done","module":"OrchestratorModule","action":"complete_recipe","args":{"output":"all done"}})";
        if (on_token) {
            on_token(res.content, "");
        }
        return res;
    }
    aquila::ComputeProfile active_profile() const noexcept override {
        return aquila::ComputeProfile::cpu_low_spec_edge;
    }
    bool supports_kv_reuse() const noexcept override { return false; }

private:
    std::vector<aquila::Message> messages_;
};

}  // namespace

TEST_CASE("cli: parse_args and dispatch flags", "[cli]") {
    SECTION("empty args defaults to help") {
        const char* argv[] = {"aquila_cli"};
        auto opts = aquila::cli::parse_args(1, argv);
        CHECK(opts.help);
        CHECK(opts.command == "help");
    }

    SECTION("--version flag") {
        const char* argv[] = {"aquila_cli", "--version"};
        auto opts = aquila::cli::parse_args(2, argv);
        CHECK(opts.version);
        CHECK(opts.command == "version");

        std::ostringstream out;
        std::ostringstream err;
        std::istringstream in;
        int rc = aquila::cli::dispatch(opts, in, out, err);
        CHECK(rc == 0);
        CHECK(out.str().find("aquila 0.0.1") != std::string::npos);
    }

    SECTION("--help flag") {
        const char* argv[] = {"aquila_cli", "--help"};
        auto opts = aquila::cli::parse_args(2, argv);
        CHECK(opts.help);

        std::ostringstream out;
        std::ostringstream err;
        std::istringstream in;
        int rc = aquila::cli::dispatch(opts, in, out, err);
        CHECK(rc == 0);
        CHECK(out.str().find("Usage: aquila_cli") != std::string::npos);
    }

    SECTION("list-recipes command") {
        const char* argv[] = {"aquila_cli", "list-recipes"};
        auto opts = aquila::cli::parse_args(2, argv);
        CHECK(opts.command == "list-recipes");

        std::ostringstream out;
        std::ostringstream err;
        std::istringstream in;
        int rc = aquila::cli::dispatch(opts, in, out, err);
        CHECK(rc == 0);
        CHECK(out.str().find("Builtin Recipe Cartridges (17):") != std::string::npos);
        CHECK(out.str().find("fn_dev_implement") != std::string::npos);
        CHECK(out.str().find("fn_writing_full") != std::string::npos);
        CHECK(out.str().find("fn_persona_build") != std::string::npos);
        CHECK(out.str().find("fn_learn_syllabus") != std::string::npos);
    }

    SECTION("list-modules command") {
        const char* argv[] = {"aquila_cli", "list-modules"};
        auto opts = aquila::cli::parse_args(2, argv);
        CHECK(opts.command == "list-modules");

        std::ostringstream out;
        std::ostringstream err;
        std::istringstream in;
        int rc = aquila::cli::dispatch(opts, in, out, err);
        CHECK(rc == 0);
        CHECK(out.str().find("[WorkspaceModule]") != std::string::npos);
        CHECK(out.str().find("[ExecutionModule]") != std::string::npos);
        CHECK(out.str().find("[OrchestratorModule]") != std::string::npos);
        CHECK(out.str().find("[KnowledgeModule]") != std::string::npos);
        CHECK(out.str().find("[DocumentModule]") != std::string::npos);
        CHECK(out.str().find("[PersonaModule]") != std::string::npos);
        CHECK(out.str().find("[LearnModule]") != std::string::npos);
    }

    SECTION("run command parsing") {
        const char* argv[] = {
            "aquila_cli", "run",
            "--recipe", "fn_dev_implement",
            "--task", "Fix the bug",
            "--tier", "gpu",
            "--verbose"
        };
        auto opts = aquila::cli::parse_args(9, argv);
        CHECK(opts.command == "run");
        CHECK(opts.recipe_id == "fn_dev_implement");
        CHECK(opts.task_prompt == "Fix the bug");
        CHECK(opts.tier_name == "gpu");
        CHECK(opts.verbose);
    }

    SECTION("run command with missing recipe returns error") {
        aquila::cli::CliOptions opts;
        opts.command = "run";
        opts.recipe_id = "non_existent_recipe_xyz";

        std::ostringstream out;
        std::ostringstream err;
        std::istringstream in;
        int rc = aquila::cli::dispatch(opts, in, out, err);
        CHECK(rc == 2);
        CHECK(err.str().find("Could not find or parse recipe") != std::string::npos);
    }

    SECTION("eval command validates all recipes") {
        aquila::cli::CliOptions opts;
        opts.command = "eval";

        std::ostringstream out;
        std::ostringstream err;
        std::istringstream in;
        int rc = aquila::cli::dispatch(opts, in, out, err);
        CHECK(rc == 0);
        CHECK(out.str().find("Evaluation Summary: 17 valid, 0 invalid") != std::string::npos);
    }

    SECTION("run command execution with mock backend") {
        aquila::cli::CliOptions opts;
        opts.command = "run";
        opts.recipe_id = "fn_research_offline";
        opts.task_prompt = "Research quantum mechanics";

        CliMockBackend mock;
        std::ostringstream out;
        std::ostringstream err;
        std::istringstream in;
        int rc = aquila::cli::dispatch(opts, in, out, err, &mock);
        CHECK(rc == 0);
        CHECK(out.str().find("Recipe execution SUCCEEDED") != std::string::npos);
    }
}
