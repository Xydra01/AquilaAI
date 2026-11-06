#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/json.hpp"
#include "aquila/modules/registry.hpp"

#include "replay_backend.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <fstream>
#include <ios>
#include <sstream>
#include <string>
#include <vector>

using namespace aquila;
using aquila::test::ReplayBackend;
using aquila::test::TempDir;

namespace {

std::string read_recipe_file(const std::string& name) {
    const std::string path = std::string(AQUILA_RECIPE_DIR) + "/" + name;
    std::ifstream in(path, std::ios::binary);
    REQUIRE(in.is_open());
    std::ostringstream buf;
    buf << in.rdbuf();
    return buf.str();
}

std::string action_reply(const std::string& thought, const std::string& mod,
                         const std::string& act, const Json& args) {
    Json call = Json::object();
    call["thought"] = thought;
    call["module"] = mod;
    call["action"] = act;
    call["args"] = args;
    return call.dump();
}

GenerationResult ok_reply(const std::string& content) {
    GenerationResult r;
    r.ok = true;
    r.content = content;
    r.prompt_tokens = 10;
    r.completion_tokens = 10;
    return r;
}

LoopConfig make_config(std::uint32_t max_turns) {
    LoopConfig config;
    config.system_prompt = "You are a helpful knowledge assistant.";
    config.task_id = "task-knowledge-recipe";
    config.mode = "test";
    config.instance_id = "inst-recipe-1";
    config.tier = RuntimeTierConfig::default_config();
    config.tier.limits.max_turns = max_turns;
    return config;
}

}  // namespace

TEST_CASE("knowledge_smoke cartridge loads, validates, and matches its JSON",
          "[recipe][knowledge]") {
    const RecipeCartridge recipe = knowledge_smoke_recipe();
    const std::string on_disk = read_recipe_file("knowledge_smoke.recipe.json");

    SECTION("JSON parity in both directions") {
        CHECK(to_canonical_string(recipe) == on_disk);
        CHECK(parse<RecipeCartridge>(on_disk) == recipe);
    }

    SECTION("validate_recipe accepts the cartridge against built-in modules") {
        TempDir tmp;
        const ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = tmp.path();
        CHECK_NOTHROW(registry.validate_recipe(recipe, ctx));
    }
}

TEST_CASE("AgentLoop executes knowledge_smoke recipe end-to-end",
          "[agent_loop][recipe][knowledge]") {
    TempDir tmp;
    tmp.write("docs/arch.md", "# Architecture\nAquila uses SQLite and Blake2b for deterministic knowledge retrieval.");

    const RecipeCartridge recipe = knowledge_smoke_recipe();
    const LoopConfig config = make_config(8);

    // Scripted turns for the agent:
    // Turn 0: Search local docs
    // Turn 1: Store retrieved fact
    // Turn 2: Checkpoint required notes
    // Turn 3: Complete recipe
    std::vector<GenerationResult> scripted;
    scripted.push_back(ok_reply(action_reply(
        "Search local documentation", "KnowledgeModule", "search_local_docs",
        Json::object({{"query", "Architecture"}, {"max_results", 3}}))));

    scripted.push_back(ok_reply(action_reply(
        "Store the architectural fact", "KnowledgeModule", "store_fact",
        Json::object({{"topic", "arch"}, {"fact", "Aquila uses SQLite and Blake2b"}}))));

    scripted.push_back(ok_reply(action_reply(
        "Checkpoint notes for requirements", "OrchestratorModule", "checkpoint_notes",
        Json::object({{"active_objective", "Index architecture"},
                      {"next_immediate_action", "Complete recipe"}}))));

    scripted.push_back(ok_reply(action_reply(
        "Complete recipe and trigger validation gate", "OrchestratorModule", "complete_recipe",
        Json::object({{"output", "All facts stored successfully."}}))));

    ReplayBackend backend(std::move(scripted));
    const ModuleRegistry registry = ModuleRegistry::builtin();
    ModuleContext ctx;
    ctx.workspace_root = tmp.path();

    AgentLoop loop(backend, registry, ctx);
    const TerminalResult result = loop.run(recipe, "Retrieve docs and store facts", config);

    CHECK(result.outcome == LoopOutcome::success);
    CHECK(result.success == true);
    CHECK(result.transcript.size() == 4);
    CHECK(result.run_record.step_index == 4);

    // Turn 0 inspected docs
    REQUIRE(result.transcript[0].interaction.has_value());
    CHECK(result.transcript[0].interaction->module == "KnowledgeModule");
    CHECK(result.transcript[0].interaction->action == "search_local_docs");
    CHECK(result.transcript[0].interaction->result.success == true);

    // Turn 1 stored fact
    REQUIRE(result.transcript[1].interaction.has_value());
    CHECK(result.transcript[1].interaction->module == "KnowledgeModule");
    CHECK(result.transcript[1].interaction->action == "store_fact");
    CHECK(result.transcript[1].interaction->result.success == true);

    // Turn 2 check-pointed scratchpad
    REQUIRE(result.transcript[2].interaction.has_value());
    CHECK(result.transcript[2].interaction->module == "OrchestratorModule");
    CHECK(result.transcript[2].interaction->action == "checkpoint_notes");
    CHECK(result.transcript[2].interaction->result.success == true);

    // Turn 3 completed and passed exit gate
    REQUIRE(result.transcript[3].interaction.has_value());
    CHECK(result.transcript[3].interaction->module == "OrchestratorModule");
    CHECK(result.transcript[3].interaction->action == "complete_recipe");
    CHECK(result.transcript[3].interaction->result.success == true);

    // Exit gate succeeded and returned completion output from complete_recipe
    CHECK(result.completion_output == "All facts stored successfully.");
}

