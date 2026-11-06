// aquila/agent/recipes.hpp
#pragma once

#include "aquila/json.hpp"
#include "aquila/types/recipe.hpp"

#include <string_view>

namespace aquila {

// Built-in recipe cartridges (R12). Each accessor parses a canonical JSON literal
// embedded below and returns the value type — there is NO run-time file I/O, so
// the recipes are available even without the resource tree on disk. The embedded
// literal is kept byte-identical to the authoritative on-disk copy under
// src/core/agent/recipes/ so the cartridge parity test (task 10.2) can assert the
// two agree.

namespace detail {

// src/core/agent/recipes/code_smoke_file.recipe.json, verbatim.
// Canonical form (R2): 2-space indent, UTF-8 not escaped, keys in field order,
// trailing newline. The raw-string delimiter "AQ" keeps the embedded `"`/`\`
// bytes literal and matches the file byte-for-byte.
inline constexpr std::string_view kCodeSmokeFileRecipeJson = R"AQ({
  "recipe_id": "code_smoke_file",
  "goal_template": "Create a Python smoke file named harness_smoke.py somewhere in the workspace whose contents include the marker HARNESS_OK, then complete the recipe. Objective: {{user_instructions}}",
  "load_modules": [
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "surgical_edit"
      ]
    },
    {
      "module": "ExecutionModule",
      "initial_state": {
        "test_cmd": "python -c 'import pathlib,sys; m=[p for p in pathlib.Path(\".\").rglob(\"harness_smoke.py\") if \"HARNESS_OK\" in p.read_text(encoding=\"utf-8\",errors=\"ignore\")]; sys.exit(0 if m else 1)'"
      },
      "expose_actions": []
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "next_immediate_action"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Record the active objective and the next immediate action before completing",
    "Create harness_smoke.py containing the HARNESS_OK marker via create_file",
    "Call complete_recipe so the deterministic exit gate verifies the smoke file"
  ],
  "post_llm_validation_hook": {
    "module": "ExecutionModule",
    "action": "run_test_suite",
    "must_succeed": true,
    "on_failure_instruction": "No file matching **/harness_smoke.py containing the marker HARNESS_OK was found. Use WorkspaceModule.create_file to write harness_smoke.py with HARNESS_OK in its contents, then complete the recipe again."
  }
}
)AQ";

// src/core/agent/recipes/knowledge_smoke.recipe.json, verbatim.
inline constexpr std::string_view kKnowledgeSmokeRecipeJson = R"AQ({
  "recipe_id": "knowledge_smoke",
  "goal_template": "Retrieve documentation, store verified facts into permanent memory, and complete the objective: {{user_instructions}}",
  "load_modules": [
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "get_all_facts",
        "search_local_docs",
        "store_fact"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "next_immediate_action"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Search local documents for knowledge",
    "Record verified facts using KnowledgeModule.store_fact",
    "Complete recipe"
  ],
  "post_llm_validation_hook": {
    "module": "KnowledgeModule",
    "action": "get_all_facts",
    "must_succeed": true,
    "on_failure_instruction": "Knowledge store validation failed."
  }
}
)AQ";

}  // namespace detail

// The "code_smoke_file" exit-gate smoke recipe (R12, Req 7.1/7.2/7.5): load the
// Workspace, Execution and Orchestrator modules, let the LLM create a file and
// checkpoint/complete, and gate completion on a deterministic ExecutionModule
// check that a file matching **/harness_smoke.py containing HARNESS_OK exists.
//
// The validation hook targets ExecutionModule.run_test_suite, which the loop
// invokes with empty args; run_test_suite runs the configured test_cmd (a
// no-shell `python -c` check) that exits non-zero unless the marker file is
// present, so the gate is driven entirely by the module's initial_state. The
// hook action is intentionally NOT in ExecutionModule's expose_actions — a
// HookCall may invoke an action the LLM cannot (Req 5.5).
[[nodiscard]] inline RecipeCartridge code_smoke_file_recipe() {
    return parse<RecipeCartridge>(detail::kCodeSmokeFileRecipeJson);
}

// The "knowledge_smoke" recipe cartridge exercising KnowledgeModule, WorkspaceModule,
// and OrchestratorModule.
[[nodiscard]] inline RecipeCartridge knowledge_smoke_recipe() {
    return parse<RecipeCartridge>(detail::kKnowledgeSmokeRecipeJson);
}

}  // namespace aquila
