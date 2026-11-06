// aquila/agent/recipes.hpp
#pragma once

#include "aquila/json.hpp"
#include "aquila/types/recipe.hpp"

#include <string_view>
#include <vector>

namespace aquila {

namespace detail {

// src/core/agent/recipes/code_smoke_file.recipe.json, verbatim.
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

// src/core/agent/recipes/fn_research_full.recipe.json, verbatim.
inline constexpr std::string_view kFnResearchFullRecipeJson = R"AQ({
  "recipe_id": "fn_research_full",
  "goal_template": "Conduct comprehensive research on: {{user_instructions}}",
  "load_modules": [
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region",
        "outline"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "verified_facts",
          "next_immediate_action"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "trigger_context_condense"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Search local documentation and corpus for relevant material",
    "Store key verified findings into long-term knowledge memory",
    "Summarize final synthesis into report file",
    "Call complete_recipe"
  ]
}
)AQ";

// src/core/agent/recipes/fn_research_dynamic.recipe.json, verbatim.
inline constexpr std::string_view kFnResearchDynamicRecipeJson = R"AQ({
  "recipe_id": "fn_research_dynamic",
  "goal_template": "Perform dynamic hypothesis-driven research: {{user_instructions}}",
  "load_modules": [
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "ExecutionModule",
      "initial_state": {
        "test_cmd": "pytest"
      },
      "expose_actions": [
        "exec_sandboxed_cmd",
        "run_test_suite"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region",
        "outline"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "current_hypothesis",
          "verified_facts"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "trigger_context_condense"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Formulate and test experimental hypotheses",
    "Capture experimental outputs and verify facts",
    "Complete research investigation"
  ]
}
)AQ";

// src/core/agent/recipes/fn_research_offline.recipe.json, verbatim.
inline constexpr std::string_view kFnResearchOfflineRecipeJson = R"AQ({
  "recipe_id": "fn_research_offline",
  "goal_template": "Conduct offline corpus research without external tools: {{user_instructions}}",
  "load_modules": [
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "read_region",
        "outline"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "verified_facts"
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
    "Examine local docs and files",
    "Record verified facts",
    "Conclude findings"
  ]
}
)AQ";

// src/core/agent/recipes/fn_research_chat_light.recipe.json, verbatim.
inline constexpr std::string_view kFnResearchChatLightRecipeJson = R"AQ({
  "recipe_id": "fn_research_chat_light",
  "goal_template": "Provide responsive conversational research assistance: {{user_instructions}}",
  "load_modules": [
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "get_all_facts"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective"
        ]
      },
      "expose_actions": [
        "complete_recipe"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Answer user query with verified citations",
    "Complete recipe"
  ]
}
)AQ";

// src/core/agent/recipes/fn_writing_full.recipe.json, verbatim.
inline constexpr std::string_view kFnWritingFullRecipeJson = R"AQ({
  "recipe_id": "fn_writing_full",
  "goal_template": "Author a structured multi-section document: {{user_instructions}}",
  "load_modules": [
    {
      "module": "DocumentModule",
      "initial_state": {},
      "expose_actions": [
        "init_document",
        "write_section",
        "read_outline",
        "revise_selection",
        "compile_document",
        "get_draft_state"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact",
        "get_all_facts"
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
        "complete_recipe",
        "trigger_context_condense"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Initialize document canvas with target outline",
    "Draft each section adhering to word count guidelines",
    "Revise and refine sections",
    "Compile final draft and complete"
  ]
}
)AQ";

// src/core/agent/recipes/fn_writing_dynamic.recipe.json, verbatim.
inline constexpr std::string_view kFnWritingDynamicRecipeJson = R"AQ({
  "recipe_id": "fn_writing_dynamic",
  "goal_template": "Iteratively research, draft and refine a technical paper: {{user_instructions}}",
  "load_modules": [
    {
      "module": "DocumentModule",
      "initial_state": {},
      "expose_actions": [
        "init_document",
        "write_section",
        "read_outline",
        "revise_selection",
        "compile_document",
        "get_draft_state"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "current_hypothesis",
          "next_immediate_action"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "trigger_context_condense"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Setup outline and gather background facts",
    "Write core technical sections",
    "Compile and verify document"
  ]
}
)AQ";

// src/core/agent/recipes/fn_writing_sources.recipe.json, verbatim.
inline constexpr std::string_view kFnWritingSourcesRecipeJson = R"AQ({
  "recipe_id": "fn_writing_sources",
  "goal_template": "Compose sourced article synthesizing local reference documents: {{user_instructions}}",
  "load_modules": [
    {
      "module": "DocumentModule",
      "initial_state": {},
      "expose_actions": [
        "init_document",
        "write_section",
        "compile_document"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "verified_facts"
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
    "Search reference documents for quotes and sources",
    "Write sourced sections",
    "Compile finished document"
  ]
}
)AQ";

// src/core/agent/recipes/fn_learn_syllabus.recipe.json, verbatim.
inline constexpr std::string_view kFnLearnSyllabusRecipeJson = R"AQ({
  "recipe_id": "fn_learn_syllabus",
  "goal_template": "Develop an accredited course syllabus and archive learning modules: {{user_instructions}}",
  "load_modules": [
    {
      "module": "LearnModule",
      "initial_state": {},
      "expose_actions": [
        "write_syllabus",
        "finalize_course",
        "generate_assessment",
        "record_result",
        "search_archive",
        "get_course_info"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region"
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
    "Formulate hierarchical syllabus with >=8 units and >=5 sub-units",
    "Validate and write syllabus structure",
    "Finalize course and verify archive readiness"
  ]
}
)AQ";

// src/core/agent/recipes/fn_learn_syllabus_web.recipe.json, verbatim.
inline constexpr std::string_view kFnLearnSyllabusWebRecipeJson = R"AQ({
  "recipe_id": "fn_learn_syllabus_web",
  "goal_template": "Research contemporary topics and build an interactive course: {{user_instructions}}",
  "load_modules": [
    {
      "module": "LearnModule",
      "initial_state": {},
      "expose_actions": [
        "write_syllabus",
        "finalize_course",
        "generate_assessment",
        "record_result",
        "search_archive",
        "get_course_info"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
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
        "create_file",
        "read_region"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "verified_facts",
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
    "Gather knowledge and citations",
    "Construct syllabus tree conforming to curriculum rules",
    "Finalize course"
  ]
}
)AQ";

// src/core/agent/recipes/fn_persona_build.recipe.json, verbatim.
inline constexpr std::string_view kFnPersonaBuildRecipeJson = R"AQ({
  "recipe_id": "fn_persona_build",
  "goal_template": "Construct and initialize an immersive character persona: {{user_instructions}}",
  "load_modules": [
    {
      "module": "PersonaModule",
      "initial_state": {},
      "expose_actions": [
        "load_persona",
        "write_initialization",
        "finalize_persona",
        "update_preferences",
        "chat_as_persona"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region"
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
    "Craft rich initialization profile (>=800 characters)",
    "Write initialization and configure preferences",
    "Finalize persona profile"
  ]
}
)AQ";

// src/core/agent/recipes/fn_persona_lore.recipe.json, verbatim.
inline constexpr std::string_view kFnPersonaLoreRecipeJson = R"AQ({
  "recipe_id": "fn_persona_lore",
  "goal_template": "Expand world lore and interactive dialogue for persona: {{user_instructions}}",
  "load_modules": [
    {
      "module": "PersonaModule",
      "initial_state": {},
      "expose_actions": [
        "load_persona",
        "chat_as_persona",
        "update_preferences"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective"
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
    "Load persona and inspect lore",
    "Roleplay dialogue and update lore knowledge",
    "Complete recipe"
  ]
}
)AQ";

// src/core/agent/recipes/fn_dev_implement.recipe.json, verbatim.
inline constexpr std::string_view kFnDevImplementRecipeJson = R"AQ({
  "recipe_id": "fn_dev_implement",
  "goal_template": "Implement software feature according to specifications and pass tests: {{user_instructions}}",
  "load_modules": [
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region",
        "surgical_edit",
        "outline"
      ]
    },
    {
      "module": "ExecutionModule",
      "initial_state": {
        "test_cmd": "pytest"
      },
      "expose_actions": [
        "exec_sandboxed_cmd",
        "run_test_suite"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "current_hypothesis",
          "next_immediate_action"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "trigger_context_condense"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Analyze requirements and codebase",
    "Implement necessary code changes",
    "Run test suite to verify implementation",
    "Complete task"
  ]
}
)AQ";

// src/core/agent/recipes/fn_dev_documentation.recipe.json, verbatim.
inline constexpr std::string_view kFnDevDocumentationRecipeJson = R"AQ({
  "recipe_id": "fn_dev_documentation",
  "goal_template": "Review codebase and generate comprehensive API/architecture documentation: {{user_instructions}}",
  "load_modules": [
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region",
        "outline"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "verified_facts"
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
    "Scan source files and header definitions",
    "Document architecture, modules, and APIs",
    "Complete documentation task"
  ]
}
)AQ";

// src/core/agent/recipes/fn_dev_tdd.recipe.json, verbatim.
inline constexpr std::string_view kFnDevTddRecipeJson = R"AQ({
  "recipe_id": "fn_dev_tdd",
  "goal_template": "Execute test-driven development cycle: write test first, verify failure, implement feature, verify passing: {{user_instructions}}",
  "load_modules": [
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region",
        "surgical_edit",
        "outline"
      ]
    },
    {
      "module": "ExecutionModule",
      "initial_state": {
        "test_cmd": "pytest"
      },
      "expose_actions": [
        "exec_sandboxed_cmd",
        "run_test_suite"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "current_hypothesis",
          "failed_approaches_do_not_repeat",
          "next_immediate_action"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "trigger_context_condense"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Create failing test reproducing target requirement",
    "Verify test fails on ExecutionModule",
    "Implement minimal code to pass test",
    "Verify test passes cleanly and complete"
  ]
}
)AQ";

// src/core/agent/recipes/fn_dev_dynamic.recipe.json, verbatim.
inline constexpr std::string_view kFnDevDynamicRecipeJson = R"AQ({
  "recipe_id": "fn_dev_dynamic",
  "goal_template": "Perform dynamic debugging, profiling, and iterative refactoring: {{user_instructions}}",
  "load_modules": [
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "read_region",
        "surgical_edit",
        "outline"
      ]
    },
    {
      "module": "ExecutionModule",
      "initial_state": {
        "test_cmd": "pytest"
      },
      "expose_actions": [
        "exec_sandboxed_cmd",
        "run_test_suite"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "search_local_docs",
        "store_fact",
        "get_all_facts"
      ]
    },
    {
      "module": "OrchestratorModule",
      "initial_state": {
        "required_fields": [
          "active_objective",
          "current_hypothesis",
          "verified_facts",
          "failed_approaches_do_not_repeat",
          "next_immediate_action"
        ]
      },
      "expose_actions": [
        "checkpoint_notes",
        "complete_recipe",
        "trigger_context_condense"
      ]
    }
  ],
  "pre_llm_hooks": [],
  "scratchpad_checklist": [
    "Reproduce issue and record hypotheses",
    "Run diagnostic commands and analyze output",
    "Apply surgical fixes and re-verify",
    "Complete recipe"
  ]
}
)AQ";

}  // namespace detail

[[nodiscard]] inline RecipeCartridge code_smoke_file_recipe() {
    return parse<RecipeCartridge>(detail::kCodeSmokeFileRecipeJson);
}

[[nodiscard]] inline RecipeCartridge knowledge_smoke_recipe() {
    return parse<RecipeCartridge>(detail::kKnowledgeSmokeRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_research_full_recipe() {
    return parse<RecipeCartridge>(detail::kFnResearchFullRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_research_dynamic_recipe() {
    return parse<RecipeCartridge>(detail::kFnResearchDynamicRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_research_offline_recipe() {
    return parse<RecipeCartridge>(detail::kFnResearchOfflineRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_research_chat_light_recipe() {
    return parse<RecipeCartridge>(detail::kFnResearchChatLightRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_writing_full_recipe() {
    return parse<RecipeCartridge>(detail::kFnWritingFullRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_writing_dynamic_recipe() {
    return parse<RecipeCartridge>(detail::kFnWritingDynamicRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_writing_sources_recipe() {
    return parse<RecipeCartridge>(detail::kFnWritingSourcesRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_learn_syllabus_recipe() {
    return parse<RecipeCartridge>(detail::kFnLearnSyllabusRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_learn_syllabus_web_recipe() {
    return parse<RecipeCartridge>(detail::kFnLearnSyllabusWebRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_persona_build_recipe() {
    return parse<RecipeCartridge>(detail::kFnPersonaBuildRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_persona_lore_recipe() {
    return parse<RecipeCartridge>(detail::kFnPersonaLoreRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_dev_implement_recipe() {
    return parse<RecipeCartridge>(detail::kFnDevImplementRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_dev_documentation_recipe() {
    return parse<RecipeCartridge>(detail::kFnDevDocumentationRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_dev_tdd_recipe() {
    return parse<RecipeCartridge>(detail::kFnDevTddRecipeJson);
}

[[nodiscard]] inline RecipeCartridge fn_dev_dynamic_recipe() {
    return parse<RecipeCartridge>(detail::kFnDevDynamicRecipeJson);
}

[[nodiscard]] inline std::vector<RecipeCartridge> all_builtin_recipes() {
    return {
        code_smoke_file_recipe(),
        knowledge_smoke_recipe(),
        fn_research_full_recipe(),
        fn_research_dynamic_recipe(),
        fn_research_offline_recipe(),
        fn_research_chat_light_recipe(),
        fn_writing_full_recipe(),
        fn_writing_dynamic_recipe(),
        fn_writing_sources_recipe(),
        fn_learn_syllabus_recipe(),
        fn_learn_syllabus_web_recipe(),
        fn_persona_build_recipe(),
        fn_persona_lore_recipe(),
        fn_dev_implement_recipe(),
        fn_dev_documentation_recipe(),
        fn_dev_tdd_recipe(),
        fn_dev_dynamic_recipe(),
    };
}

}  // namespace aquila
