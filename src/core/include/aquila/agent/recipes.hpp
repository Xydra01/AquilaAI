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
        "web_search",
        "fetch_and_clean_url",
        "search_local_docs",
        "store_fact",
        "get_all_facts",
        "verify_research_deliverable"
      ]
    },
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "."
      },
      "expose_actions": [
        "create_file",
        "write_file",
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
    "Search web or local documentation for relevant material using KnowledgeModule web_search",
    "Store key verified findings into long-term knowledge memory using KnowledgeModule store_fact",
    "Write comprehensive final research report to research_report.md (with markdown headers and citations like [1]) using WorkspaceModule create_file",
    "Call OrchestratorModule complete_recipe to finish"
  ],
  "post_llm_validation_hook": {
    "module": "KnowledgeModule",
    "action": "verify_research_deliverable",
    "must_succeed": true,
    "on_failure_instruction": "Research deliverable verification failed. Ensure you have recorded verified facts with KnowledgeModule.store_fact and written a comprehensive markdown report (at least 350 characters, with markdown headers and citations like [1] or [Author, Year]) to research_report.md before completing."
  }
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
        "web_search",
        "fetch_and_clean_url",
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
        "ensure_venv",
        "pip_install",
        "run_python",
        "pip_list",
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
    "Search local documentation or investigate question using KnowledgeModule search_local_docs",
    "Store verified findings into knowledge memory using KnowledgeModule store_fact",
    "Call OrchestratorModule complete_recipe to finish"
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
    "Examine local docs and files using KnowledgeModule search_local_docs or WorkspaceModule outline",
    "Record verified facts using KnowledgeModule store_fact",
    "Call OrchestratorModule complete_recipe to finish"
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
        "web_search",
        "fetch_and_clean_url",
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
    "Answer user query with verified citations",
    "Call OrchestratorModule complete_recipe to finish"
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
        "get_draft_state",
        "verify_manuscript_quality"
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
    "Draft each section with substantive, detailed paragraphs (minimum 250 words total across at least 2 sections)",
    "Revise and refine sections",
    "Compile final draft and complete"
  ],
  "post_llm_validation_hook": {
    "module": "DocumentModule",
    "action": "verify_manuscript_quality",
    "must_succeed": true,
    "on_failure_instruction": "Manuscript verification failed. Ensure your draft contains at least 2 distinct sections, has at least 250 words total, has no placeholder tokens (such as TODO, Lorem ipsum, or TBD), and has substantive prose before completing."
  }
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
        "compile_document",
        "verify_manuscript_quality"
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
    "Initialize document canvas with target title via DocumentModule.init_document",
    "Search reference documents or record key background facts via KnowledgeModule",
    "Draft multiple sourced sections with detailed paragraphs (minimum 250 words total across at least 2 sections) via DocumentModule.write_section",
    "Compile finished document via DocumentModule.compile_document",
    "Call OrchestratorModule complete_recipe"
  ],
  "post_llm_validation_hook": {
    "module": "DocumentModule",
    "action": "verify_manuscript_quality",
    "must_succeed": true,
    "on_failure_instruction": "Manuscript verification failed. Ensure your draft contains at least 2 distinct sections, has at least 250 words total, has no placeholder tokens, and has substantive prose before completing."
  }
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
        "create_or_load_course",
        "create_course",
        "write_syllabus",
        "finalize_course",
        "generate_assessment",
        "record_result",
        "add_archive_source",
        "ingest_archive_file",
        "ingest_archive_url",
        "list_archive_sources",
        "search_archive",
        "get_course_info",
        "verify_course_quality"
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
    "Finalize course and verify archive readiness",
    "Call OrchestratorModule complete_recipe"
  ],
  "post_llm_validation_hook": {
    "module": "LearnModule",
    "action": "verify_course_quality",
    "must_succeed": true,
    "on_failure_instruction": "Course verification failed. Ensure you have written a hierarchical syllabus with at least 8 units, at least 5 sub-units with parent_id, distinct non-placeholder titles, and called LearnModule.finalize_course before completing."
  }
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
        "create_or_load_course",
        "create_course",
        "write_syllabus",
        "finalize_course",
        "generate_assessment",
        "record_result",
        "add_archive_source",
        "ingest_archive_file",
        "ingest_archive_url",
        "list_archive_sources",
        "search_archive",
        "get_course_info"
      ]
    },
    {
      "module": "KnowledgeModule",
      "initial_state": {},
      "expose_actions": [
        "web_search",
        "fetch_and_clean_url",
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
        "chat_as_persona",
        "verify_persona_quality"
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
    "Load or initialize persona record via PersonaModule.load_persona",
    "Write rich initialization profile (>=800 characters) with structured headings via PersonaModule.write_initialization",
    "Finalize persona profile with in-character greeting and tagline via PersonaModule.finalize_persona",
    "Call OrchestratorModule complete_recipe"
  ],
  "post_llm_validation_hook": {
    "module": "PersonaModule",
    "action": "verify_persona_quality",
    "must_succeed": true,
    "on_failure_instruction": "Persona verification failed. Ensure you have written initialization.md with at least 800 characters of rich lore, structured markdown headings, no generic assistant leakage, and called PersonaModule.finalize_persona with an in-character greeting before completing."
  }
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
    "Load persona using PersonaModule load_persona or inspect world lore",
    "Record lore facts into knowledge memory using KnowledgeModule store_fact",
    "Call OrchestratorModule complete_recipe to finish"
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
        "ensure_venv",
        "pip_install",
        "run_python",
        "pip_list",
        "exec_sandboxed_cmd",
        "run_test_suite",
        "verify_implementation"
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
    "Analyze requirements and codebase",
    "Ensure workspace virtualenv and install required dependencies",
    "Implement necessary code changes",
    "Run script or test suite to verify implementation",
    "Complete task"
  ],
  "post_llm_validation_hook": {
    "module": "ExecutionModule",
    "action": "verify_implementation",
    "must_succeed": true,
    "on_failure_instruction": "Implementation verification failed. Ensure the script exists, has non-empty executable code (no pass/TODO stubs), passes python syntax checks, and executes cleanly in .venv without errors. Fix the code and complete the recipe again."
  }
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
    "Scan source files and header definitions using WorkspaceModule outline",
    "Document architecture, modules, and APIs into ARCHITECTURE.md using WorkspaceModule create_file",
    "Call OrchestratorModule complete_recipe"
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
        "ensure_venv",
        "pip_install",
        "run_python",
        "pip_list",
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
    "Ensure workspace virtualenv and test framework is ready",
    "Create test file with pytest test cases (remember to import the module under test)",
    "Implement code in target file to satisfy tests using WorkspaceModule create_file",
    "Run ExecutionModule run_test_suite to verify all tests pass",
    "Call OrchestratorModule complete_recipe"
  ]
}
)AQ";

// src/core/agent/recipes/fn_dev_dynamic.recipe.json, verbatim.
inline constexpr std::string_view kFnDevDynamicRecipeJson = R"AQ({
  "recipe_id": "fn_dev_dynamic",
  "goal_template": "Implement, debug, and verify execution: {{user_instructions}}",
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
        "ensure_venv",
        "pip_install",
        "run_python",
        "pip_list",
        "exec_sandboxed_cmd",
        "run_test_suite",
        "verify_implementation"
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
    "Write the script or implementation file using WorkspaceModule create_file (use pure Python standard library e.g. urllib or socket for cross-platform compatibility)",
    "Run and verify execution using ExecutionModule run_python",
    "Verify implementation quality via ExecutionModule verify_implementation",
    "Call OrchestratorModule complete_recipe"
  ],
  "post_llm_validation_hook": {
    "module": "ExecutionModule",
    "action": "verify_implementation",
    "must_succeed": true,
    "on_failure_instruction": "Implementation verification failed. Ensure you have written a complete, substantive script without stub bodies (no pass or TODO), and that it executes cleanly with exit code 0."
  }
}
)AQ";

} // namespace detail

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
      code_smoke_file_recipe(),       knowledge_smoke_recipe(),
      fn_research_full_recipe(),      fn_research_dynamic_recipe(),
      fn_research_offline_recipe(),   fn_research_chat_light_recipe(),
      fn_writing_full_recipe(),       fn_writing_dynamic_recipe(),
      fn_writing_sources_recipe(),    fn_learn_syllabus_recipe(),
      fn_learn_syllabus_web_recipe(), fn_persona_build_recipe(),
      fn_persona_lore_recipe(),       fn_dev_implement_recipe(),
      fn_dev_documentation_recipe(),  fn_dev_tdd_recipe(),
      fn_dev_dynamic_recipe(),
  };
}

} // namespace aquila
