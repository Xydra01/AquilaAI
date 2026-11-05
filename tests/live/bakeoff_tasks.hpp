#pragma once

// Bake-off task suite (M5 task 11.3, Req 9.2) -- multi-turn tool-use scenarios that
// FORCE long context: each plants a fact in an EARLY turn, then interposes several
// tool-result turns (a detour), then requires the FINAL action to use the planted
// value. A strategy that condenses carelessly will "forget" the planted fact and
// fail the oracle -- which is exactly the compaction-fidelity signal the bake-off
// measures (the failure mode the NVIDIA "you don't need long context" paper warns
// about for open models).
//
// A task is a prefix (system + how to answer) + an ordered list of turns + an
// oracle over the FINAL ActionCall. The harness feeds the turns to a ContextStrategy
// and asks for one action at the end; the oracle decides pass/fail deterministically.

#include "aquila/json.hpp"
#include "aquila/types/action.hpp"
#include "aquila/types/message.hpp"

#include <functional>
#include <string>
#include <vector>

namespace aquila::bakeoff {

// Returns true when the final action satisfies the task (the planted fact survived).
using Oracle = std::function<bool(const ActionCall&)>;

struct Task {
    std::string name;
    std::vector<Message> prefix;   // pinned: system prompt + answer contract
    std::vector<Message> turns;    // ordered user/tool turns; a fact is planted early
    std::string final_prompt;      // the last user turn that asks for the action
    Oracle oracle;                 // checks the final ActionCall used the planted fact
};

// A compact system prefix shared by the suite: the model must answer with exactly
// one JSON action {thought, module, action, args}; the GBNF grammar enforces shape,
// the oracle checks the SEMANTICS (did it carry the remembered value).
inline std::vector<Message> common_prefix() {
    return {
        Message{Role::system,
                "You are Aquila, a careful coding agent. Respond with exactly one "
                "JSON action object: {\"thought\", \"module\", \"action\", \"args\"}. "
                "Always use values the user established earlier in the conversation; "
                "never invent identifiers, paths, or names."},
    };
}

// `n_detour` filler tool-result turns that push the planted fact out of the recent
// window without adding information the final action needs -- the "long context"
// pressure. Kept textually bulky so the token threshold is reached.
inline std::vector<Message> detour_turns(std::size_t n_detour) {
    std::vector<Message> t;
    for (std::size_t i = 0; i < n_detour; ++i) {
        t.push_back(Message{Role::tool,
                            "tool_result[" + std::to_string(i) + "]: scanned module "
                            "sources; no actionable findings. Checked imports, ran the "
                            "linter, inspected the build graph, and confirmed the "
                            "workspace is clean. Continuing the investigation."});
    }
    return t;
}

// The suite: 6 tasks, each plants a different KIND of fact (filename, id, numeric
// constraint, path, flag name, ordered pair) so a strategy cannot special-case one.
inline std::vector<Task> suite(std::size_t n_detour = 8) {
    std::vector<Task> tasks;

    // 1) planted FILENAME must be the create target.
    {
        Task t;
        t.name = "remember_filename";
        t.prefix = common_prefix();
        t.turns.push_back(Message{Role::user,
            "Remember this exact target filename for later: harness_report_7f3a.md"});
        for (auto& m : detour_turns(n_detour)) t.turns.push_back(m);
        t.final_prompt = "Now create that file. Emit the create_file action with the "
                         "args.path set to the filename I gave you earlier.";
        t.oracle = [](const ActionCall& a) {
            return a.args.contains("path") && a.args["path"].is_string() &&
                   a.args["path"].get<std::string>().find("harness_report_7f3a.md") !=
                       std::string::npos;
        };
        tasks.push_back(std::move(t));
    }

    // 2) planted ISSUE ID must be echoed in args.id.
    {
        Task t;
        t.name = "remember_issue_id";
        t.prefix = common_prefix();
        t.turns.push_back(Message{Role::user,
            "Track issue AQ-20481 across this session; it is the only issue that matters."});
        for (auto& m : detour_turns(n_detour)) t.turns.push_back(m);
        t.final_prompt = "Close the issue. Emit the close_issue action with args.id set "
                         "to the issue identifier from earlier.";
        t.oracle = [](const ActionCall& a) {
            return a.args.contains("id") && a.args["id"].is_string() &&
                   a.args["id"].get<std::string>().find("AQ-20481") != std::string::npos;
        };
        tasks.push_back(std::move(t));
    }

    // 3) planted NUMERIC constraint must be respected in args.max_retries.
    {
        Task t;
        t.name = "remember_numeric_constraint";
        t.prefix = common_prefix();
        t.turns.push_back(Message{Role::user,
            "Hard rule for this task: max_retries must be exactly 3. Do not change it."});
        for (auto& m : detour_turns(n_detour)) t.turns.push_back(m);
        t.final_prompt = "Configure the runner. Emit the set_config action with "
                         "args.max_retries set to the value from the hard rule.";
        t.oracle = [](const ActionCall& a) {
            if (!a.args.contains("max_retries")) return false;
            const Json& v = a.args["max_retries"];
            if (v.is_number_integer()) return v.get<long long>() == 3;
            if (v.is_string()) return v.get<std::string>() == "3";
            return false;
        };
        tasks.push_back(std::move(t));
    }

    // 4) planted PATH must be the read target.
    {
        Task t;
        t.name = "remember_path";
        t.prefix = common_prefix();
        t.turns.push_back(Message{Role::user,
            "The config we care about lives at src/core/agent/tier_defaults.yaml."});
        for (auto& m : detour_turns(n_detour)) t.turns.push_back(m);
        t.final_prompt = "Read that config. Emit the read_file action with args.path "
                         "set to the path I mentioned.";
        t.oracle = [](const ActionCall& a) {
            return a.args.contains("path") && a.args["path"].is_string() &&
                   a.args["path"].get<std::string>().find(
                       "src/core/agent/tier_defaults.yaml") != std::string::npos;
        };
        tasks.push_back(std::move(t));
    }

    // 5) planted FLAG NAME must appear in args.flag.
    {
        Task t;
        t.name = "remember_flag";
        t.prefix = common_prefix();
        t.turns.push_back(Message{Role::user,
            "The feature flag to toggle is called kv_rollback_experimental."});
        for (auto& m : detour_turns(n_detour)) t.turns.push_back(m);
        t.final_prompt = "Disable it. Emit the toggle_flag action with args.flag set "
                         "to the flag name and args.enabled false.";
        t.oracle = [](const ActionCall& a) {
            return a.args.contains("flag") && a.args["flag"].is_string() &&
                   a.args["flag"].get<std::string>().find("kv_rollback_experimental") !=
                       std::string::npos;
        };
        tasks.push_back(std::move(t));
    }

    // 6) planted ORDERED PAIR (branch, base) must both survive and keep order.
    {
        Task t;
        t.name = "remember_branch_pair";
        t.prefix = common_prefix();
        t.turns.push_back(Message{Role::user,
            "We are merging branch feature/bakeoff-metrics INTO base main. Keep that "
            "direction straight: head is feature/bakeoff-metrics, base is main."});
        for (auto& m : detour_turns(n_detour)) t.turns.push_back(m);
        t.final_prompt = "Open the pull request. Emit the open_pr action with "
                         "args.head and args.base set from earlier.";
        t.oracle = [](const ActionCall& a) {
            if (!a.args.contains("head") || !a.args.contains("base")) return false;
            if (!a.args["head"].is_string() || !a.args["base"].is_string()) return false;
            return a.args["head"].get<std::string>().find("feature/bakeoff-metrics") !=
                       std::string::npos &&
                   a.args["base"].get<std::string>() == "main";
        };
        tasks.push_back(std::move(t));
    }

    return tasks;
}

}  // namespace aquila::bakeoff