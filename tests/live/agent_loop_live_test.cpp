// Live end-to-end tests for the M4 AgentLoop against a real Ollama server
// (opt-in: -DAQUILA_LIVE_TESTS=ON). Excluded from CI, same policy as the M2 live
// tests (ollama_live_test.cpp). Their CI-safe deterministic counterparts are the
// ReplayBackend property tests (Property 1-5, 21) in tests/unit.
//
// TEST 1 (live.agent_loop.code_smoke_file, Req 7.2/7.3/8.4): runs the
//   code_smoke_file recipe 3 times against stock Ollama, asserting the Python
//   rubric each time -- a file matching **/harness_smoke.py exists and contains
//   HARNESS_OK -- and recording the per-run turn count, outcome, and acceptance.
// TEST 2 (live.agent_loop.forced_failure, Req 7.4/8.4): the SAME recipe (the gate
//   still requires HARNESS_OK) but a system prompt that instructs the agent to
//   OMIT the marker, so the must_succeed gate fails on every complete_recipe and
//   the loop can only end at the turn limit with a non-success terminal.
#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/agent/runtime_tier.hpp"
#include "aquila/inference/ollama_backend.hpp"
#include "aquila/modules/registry.hpp"

#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <regex>
#include <string>
#include <system_error>

using namespace aquila;

namespace {

namespace fs = std::filesystem;

std::string live_model() {
    const char* m = std::getenv("AQUILA_LIVE_MODEL");
    return (m && *m) ? m : "aquila:latest";
}

OllamaHttpBackend live_backend() {
    auto c = OllamaConfig::from_env();
    c.model = live_model();
    // The GPU tier offloads every layer (gpu_layers 999) and a 4070 is present;
    // the backend's profile is informational here, the LoopConfig tier drives the
    // real knobs. Keep the config profile aligned with the tier we use below.
    c.profile = ComputeProfile::gpu_high_vram;
    return OllamaHttpBackend(c);
}

// The same ~10-line guard ollama_live_test.cpp uses: probe /api/version and
// REQUIRE a plain release (\d+\.\d+\.\d+), rejecting the turboquant build whose
// version reads "pr15505-turboquant".
void require_stock_server(const OllamaHttpBackend& b) {
    const auto version = b.probe(5.0);
    REQUIRE(version.has_value());
    std::printf("server %s version %s, model %s\n", b.config().base_url.c_str(), version->c_str(),
                b.config().model.c_str());
    REQUIRE(std::regex_match(*version, std::regex(R"(\d+\.\d+\.\d+)")));
}

// A fresh directory under the system temp dir, removed on destruction. Local to
// this file (tests/unit/temp_dir.hpp is not on the live target's include path).
class LiveTempDir {
public:
    LiveTempDir() {
        static std::atomic<unsigned> counter{0};
        const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
        path_ = fs::temp_directory_path() /
                ("aquila-live-" + std::to_string(stamp) + "-" + std::to_string(counter++));
        std::error_code ec;
        fs::create_directories(path_, ec);
    }
    ~LiveTempDir() {
        std::error_code ec;
        fs::remove_all(path_, ec);
    }
    LiveTempDir(const LiveTempDir&) = delete;
    LiveTempDir& operator=(const LiveTempDir&) = delete;

    [[nodiscard]] const fs::path& path() const noexcept { return path_; }

private:
    fs::path path_;
};

// The Python rubric (capability_harness.py code_smoke_file): a file whose name is
// harness_smoke.py exists anywhere under `root` and its contents contain the exact
// marker HARNESS_OK. Mirrors the recipe's run_test_suite gate check, re-run
// independently so acceptance is judged by the test, not by the gate alone.
bool harness_smoke_accepted(const fs::path& root) {
    std::error_code ec;
    for (fs::recursive_directory_iterator it(root, fs::directory_options::skip_permission_denied, ec),
         end;
         !ec && it != end; it.increment(ec)) {
        if (!it->is_regular_file(ec)) continue;
        if (it->path().filename() != "harness_smoke.py") continue;
        std::ifstream in(it->path(), std::ios::binary);
        const std::string contents((std::istreambuf_iterator<char>(in)),
                                   std::istreambuf_iterator<char>());
        if (contents.find("HARNESS_OK") != std::string::npos) return true;
    }
    return false;
}

const char* outcome_name(LoopOutcome o) {
    switch (o) {
    case LoopOutcome::success: return "success";
    case LoopOutcome::turn_limit: return "turn_limit";
    case LoopOutcome::aborted: return "aborted";
    }
    return "?";
}

// A concise, realistic coding-agent system prompt. It names the ONLY exposed
// actions, states the one-action-per-turn JSON contract, the required scratchpad
// fields, and the exact goal (create harness_smoke.py containing HARNESS_OK,
// checkpoint, then complete_recipe).
constexpr const char* kSmokeSystemPrompt =
    "You are a coding agent driving a tool loop. Each turn you emit EXACTLY ONE "
    "JSON object and nothing else: {\"thought\": string, \"module\": string, "
    "\"action\": string, \"args\": object}. You may use ONLY these actions:\n"
    "- WorkspaceModule.create_file {\"file\": string, \"content\": string}: create a new file.\n"
    "- WorkspaceModule.surgical_edit {\"file\": string, \"search_block\": string, \"replace_block\": string}: edit a file.\n"
    "- OrchestratorModule.checkpoint_notes {\"active_objective\": string, \"next_immediate_action\": string}: "
    "record your notes (both fields are required and must be non-empty).\n"
    "- OrchestratorModule.complete_recipe {}: finish the recipe; a deterministic gate then verifies your work.\n"
    "\n"
    "TASK: Create a file named harness_smoke.py (at the workspace root is fine) whose contents include "
    "the exact marker HARNESS_OK. A minimal valid body is:\n"
    "# HARNESS_OK\\nprint(\"ok\")\n"
    "\n"
    "PLAN (follow in order):\n"
    "1. Call OrchestratorModule.checkpoint_notes with active_objective and next_immediate_action.\n"
    "2. Call WorkspaceModule.create_file for harness_smoke.py with contents that contain HARNESS_OK.\n"
    "3. Call OrchestratorModule.complete_recipe to finish.\n"
    "Do not wrap the JSON in markdown fences. Emit one action per turn.";

// The forced-failure analogue of "the written file omits HARNESS_OK" (Req 7.4).
// Same recipe, same gate (still requires HARNESS_OK), but the agent is told to
// create harness_smoke.py WITHOUT the marker, so the must_succeed gate fails on
// every complete_recipe attempt and the loop can only end at the turn limit.
constexpr const char* kForcedFailureSystemPrompt =
    "You are a coding agent driving a tool loop. Each turn you emit EXACTLY ONE "
    "JSON object and nothing else: {\"thought\": string, \"module\": string, "
    "\"action\": string, \"args\": object}. You may use ONLY these actions:\n"
    "- WorkspaceModule.create_file {\"file\": string, \"content\": string}: create a new file.\n"
    "- WorkspaceModule.surgical_edit {\"file\": string, \"search_block\": string, \"replace_block\": string}: edit a file.\n"
    "- OrchestratorModule.checkpoint_notes {\"active_objective\": string, \"next_immediate_action\": string}: "
    "record your notes (both fields are required and must be non-empty).\n"
    "- OrchestratorModule.complete_recipe {}: finish the recipe.\n"
    "\n"
    "TASK: Create a file named harness_smoke.py (at the workspace root is fine) whose contents are EXACTLY:\n"
    "print(\"hello\")\n"
    "Do NOT include the token HARNESS_OK anywhere in the file. The file must contain only print(\"hello\").\n"
    "\n"
    "PLAN (follow in order):\n"
    "1. Call OrchestratorModule.checkpoint_notes with active_objective and next_immediate_action.\n"
    "2. Call WorkspaceModule.create_file for harness_smoke.py with contents print(\"hello\") and NOTHING else.\n"
    "3. Call OrchestratorModule.complete_recipe to finish.\n"
    "Do not wrap the JSON in markdown fences. Emit one action per turn.";

}  // namespace

TEST_CASE("live: code_smoke_file passes the Python rubric 3/3", "[agent_loop_live]") {
    auto backend = live_backend();
    require_stock_server(backend);

    const RuntimeTierConfig tier = RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram);
    const RecipeCartridge recipe = code_smoke_file_recipe();
    const ModuleRegistry registry = ModuleRegistry::builtin();

    int passes = 0;
    for (int run = 0; run < 3; ++run) {
        LiveTempDir workspace;

        ModuleContext ctx;
        ctx.workspace_root = workspace.path();
        ctx.max_output_chars = tier.limits.tool_output_chars;

        LoopConfig config;
        config.tier = tier;
        config.system_prompt = kSmokeSystemPrompt;
        config.task_id = "code_smoke_file";
        config.mode = "code";
        config.instance_id = "live-run-" + std::to_string(run);

        AgentLoop loop(backend, registry, ctx);
        const TerminalResult result =
            loop.run(recipe, "Create harness_smoke.py containing HARNESS_OK.", config);

        const bool accepted = harness_smoke_accepted(workspace.path());
        std::printf("[run %d] turns=%zu outcome=%s success=%d accepted=%d\n", run,
                    result.transcript.size(), outcome_name(result.outcome),
                    static_cast<int>(result.success), static_cast<int>(accepted));

        INFO("run " << run << " outcome=" << outcome_name(result.outcome)
                    << " turns=" << result.transcript.size());
        CHECK(accepted);
        if (accepted) ++passes;
    }

    std::printf("code_smoke_file acceptance: %d/3\n", passes);
    CHECK(passes == 3);
}

TEST_CASE("live: forced-failure reaches the turn limit with a non-success terminal",
          "[agent_loop_live]") {
    auto backend = live_backend();
    require_stock_server(backend);

    const RuntimeTierConfig tier = RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram);
    const RecipeCartridge recipe = code_smoke_file_recipe();
    const ModuleRegistry registry = ModuleRegistry::builtin();

    LiveTempDir workspace;
    ModuleContext ctx;
    ctx.workspace_root = workspace.path();
    ctx.max_output_chars = tier.limits.tool_output_chars;

    LoopConfig config;
    config.tier = tier;
    config.system_prompt = kForcedFailureSystemPrompt;
    config.task_id = "code_smoke_file";
    config.mode = "code";
    config.instance_id = "live-forced-failure";

    AgentLoop loop(backend, registry, ctx);
    const TerminalResult result = loop.run(
        recipe, "Create harness_smoke.py containing only print(\"hello\") (no HARNESS_OK).", config);

    std::printf("[forced-failure] turns=%zu outcome=%s success=%d\n", result.transcript.size(),
                outcome_name(result.outcome), static_cast<int>(result.success));

    INFO("outcome=" << outcome_name(result.outcome) << " turns=" << result.transcript.size());
    CHECK_FALSE(result.success);
    CHECK(result.outcome == LoopOutcome::turn_limit);
}
