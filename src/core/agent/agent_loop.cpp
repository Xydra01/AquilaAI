#include "aquila/agent/agent_loop.hpp"

#include "aquila/json.hpp"
#include "aquila/logging/run_logger.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace aquila {

AgentLoop::AgentLoop(IInferenceBackend& backend, const ModuleRegistry& registry,
                     ModuleContext module_ctx)
    : backend_(backend), registry_(registry), module_ctx_(std::move(module_ctx)) {}

namespace {

std::string build_recipe_system_prompt(const RecipeCartridge& recipe,
                                       const std::vector<std::unique_ptr<IAgentModule>>& modules,
                                       const std::string& custom_prompt,
                                       const std::string& user_request) {
    std::string prompt = custom_prompt;
    if (prompt.empty()) {
#if defined(_WIN32)
        constexpr const char* kHostOsNote =
            "Host Environment: Windows (use cross-platform or Windows-compatible Python stdlib; "
            "do NOT import Unix-only modules like 'resource' or 'fcntl', nor read '/proc/*').\n";
#elif defined(__APPLE__)
        constexpr const char* kHostOsNote = "Host Environment: macOS.\n";
#else
        constexpr const char* kHostOsNote = "Host Environment: Linux.\n";
#endif
        prompt = std::string(
                     "You are Aquila, an autonomous software engineering and research agent.\n"
                     "You solve complex technical tasks systematically by selecting and executing module actions.\n") +
                 kHostOsNote;
    }
    prompt += "\nACTIVE RECIPE: " + recipe.recipe_id + "\n";
    std::string goal = recipe.goal_template;
    const std::string needle = "{{user_instructions}}";
    if (auto pos = goal.find(needle); pos != std::string::npos) {
        goal.replace(pos, needle.size(), user_request);
    } else if (!user_request.empty()) {
        goal += " (" + user_request + ")";
    }
    if (!goal.empty()) {
        prompt += "RECIPE OBJECTIVE: " + goal + "\n";
    }
    if (!recipe.scratchpad_checklist.empty()) {
        prompt += "\nRECIPE STEP CHECKLIST (Execute in order):\n";
        for (std::size_t i = 0; i < recipe.scratchpad_checklist.size(); ++i) {
            prompt += std::to_string(i + 1) + ". " + recipe.scratchpad_checklist[i] + "\n";
        }
    }
    prompt += "\nLOADED MODULES & EXPOSED ACTIONS (You must ONLY call actions from these modules):\n";
    for (const auto& lm : recipe.load_modules) {
        prompt += "- " + lm.module + ":\n";
        const IAgentModule* mod = nullptr;
        for (const auto& m : modules) {
            if (m && m->module_id() == lm.module) {
                mod = m.get();
                break;
            }
        }
        std::map<std::string, ActionSchema> schemas;
        if (mod != nullptr) {
            for (const auto& act : mod->get_actions()) {
                schemas[act.action_name] = act;
            }
        }
        for (const auto& act_name : lm.expose_actions) {
            prompt += "  * " + act_name;
            auto it = schemas.find(act_name);
            if (it != schemas.end()) {
                prompt += ": " + it->second.description;
                const auto& pschema = it->second.parameters_json_schema;
                if (!pschema.empty() && pschema.is_object() && pschema.contains("properties") && pschema["properties"].is_object()) {
                    prompt += " (Args: {";
                    bool first = true;
                    for (auto p = pschema["properties"].begin(); p != pschema["properties"].end(); ++p) {
                        if (!first) prompt += ", ";
                        std::string type_str = "any";
                        if (p.value().is_object() && p.value().contains("type")) {
                            if (p.value()["type"].is_string()) {
                                type_str = p.value()["type"].get<std::string>();
                            } else if (p.value()["type"].is_array() && !p.value()["type"].empty() && p.value()["type"][0].is_string()) {
                                type_str = p.value()["type"][0].get<std::string>();
                            }
                        }
                        prompt += p.key() + ": " + type_str;
                        first = false;
                    }
                    prompt += "})";
                }
            }
            prompt += "\n";
        }
    }
    prompt += "\nCRITICAL EXECUTION RULES:\n"
              "1. You must respond ONLY with a single JSON ActionCall object matching the required schema: {\"thought\": \"...\", \"module\": \"...\", \"action\": \"...\", \"args\": {...}}.\n"
              "2. The 'module' field MUST be one of the loaded modules listed above. Never invent or hallucinate unloaded modules.\n"
              "3. When writing code, scripts, or files (via WorkspaceModule or ExecutionModule), write complete, syntactically valid code (e.g. in Python, always call functions with parentheses like datetime.now(tz), provide valid arguments, and include needed imports). If an action returns an error or syntax failure, READ the error output, fix the code, and NEVER submit the identical failing code.\n"
              "4. Task Completion: Once your task ledger steps are completed and deliverables verified, call OrchestratorModule.complete_recipe with a concise summary of what was accomplished to finish the recipe. Do not stay stuck in repetitive loops or rerun completed steps.\n"
              "5. Non-Interactive & Server Application Rule: All generated code and scripts MUST be non-interactive and terminate cleanly. NEVER call input() or block on user stdin. For web servers and daemons (Flask, FastAPI, etc.): NEVER block unconditionally on app.run() or uvicorn.run() during testing. Always test routes using the framework's test client (e.g. app.test_client() in Flask or httpx/requests) so the script verifies endpoints and exits cleanly with exit code 0 when run directly, or guard server startup behind '--serve' CLI flag. Once verification succeeds, call OrchestratorModule.complete_recipe.\n"
              "6. Task Ledger & Milestone Tracking: Your active Task Ledger is anchored in your context every turn. Keep it updated as you progress by calling OrchestratorModule.update_task_ledger (e.g. completed_steps: [\"1\"], in_progress_step: \"2\") or during checkpoint_notes. OrchestratorModule.complete_recipe will deterministically reject if mandatory steps remain incomplete.\n";
    const bool has_browser = std::any_of(recipe.load_modules.begin(), recipe.load_modules.end(),
        [](const ModuleLoad& lm) { return lm.module == "BrowserModule"; });
    if (has_browser) {
        prompt += "7. Active Web Exploration (BrowserModule): Do NOT stop after glancing only at the top of one webpage. "
                  "Whenever a page reports remaining content below the fold or truncated text, call BrowserModule.browser_scroll (direction: \"down\", moderate steps <= 1600px) to read deeper sections, tables, benchmarks, and citations. "
                  "Use BrowserModule.browser_click with the listed CSS selectors to expand collapsed tabs/accordions ([collapsed] / [role=tab] / <summary>) or follow high-signal links (GitHub repos, arXiv papers, docs, technical discussions); "
                  "use BrowserModule.browser_type(selector, text, submit: true) on [search-input] bars to search inside sites. "
                  "Check BrowserModule's anchored visited_urls_do_not_reload and failed_urls_do_not_retry lists so you never reload finished pages or retry 404 URLs, and always cite the real http(s):// URLs of your visited/retrieved sources in research_report.md.\n";
    }
    return prompt;
}

std::string canonical_call_signature(const ActionCall& call) {
    Json normalized = call.args.is_object() ? call.args : Json::object();
    if (normalized.is_object()) {
        for (const char* key : {"path", "dir", "file"}) {
            if (normalized.contains(key) && normalized[key].is_string()) {
                std::string v = normalized[key].get<std::string>();
                while (v.size() > 1 && (v.back() == '/' || v.back() == '\\')) {
                    v.pop_back();
                }
                if (v == "./" || v == ".\\") {
                    v = ".";
                }
                normalized[key] = std::move(v);
            }
        }
    }
    return call.module + "::" + call.action + "::" + json_io::canonical_dump(normalized);
}

void emit_guidance(ContextCondenser& condenser,
                   const std::shared_ptr<logging::RunLogger>& logger,
                   std::uint64_t turn,
                   std::string text,
                   std::vector<std::string>* emitted_out = nullptr) {
    if (logger) {
        logger->log_guidance(turn, text);
    }
    if (emitted_out != nullptr) {
        emitted_out->push_back(text);
    }
    condenser.push_guidance(std::move(text));
}

std::vector<std::pair<std::string, Json>> collect_context_summaries(
    const std::vector<std::unique_ptr<IAgentModule>>& modules) {
    std::vector<std::pair<std::string, Json>> summaries;
    summaries.reserve(modules.size());
    for (const std::unique_ptr<IAgentModule>& module : modules) {
        summaries.emplace_back(module->module_id(), module->export_context_summary());
    }
    return summaries;
}

bool is_readonly_discovery_action(std::string_view action) noexcept {
    return action == "outline" || action == "read_region" || action == "inspect_symbol" ||
           action == "web_search" || action == "fetch_and_clean_url" ||
           action == "search_local_docs" || action == "get_all_facts";
}

bool is_state_mutating_action(std::string_view action) noexcept {
    return action == "surgical_edit" || action == "create_file" || action == "write_file" ||
           action == "revert_file" || action == "edit_file" || action == "restore" ||
           action == "execute" || action == "run_command" || action == "run_tests" ||
           action == "run_python" || action == "write_section" ||
           action == "browser_navigate" || action == "browser_click" ||
           action == "browser_type" || action == "browser_scroll";
}

bool is_progressive_browser_action(std::string_view module, std::string_view action) noexcept {
    return module == "BrowserModule" && (action == "browser_scroll" || action == "browser_click");
}

}  // namespace

Json AgentLoop::action_call_schema(const RecipeCartridge* recipe) {
    // The OutputConstraint::json_schema the backend enforces (R14). Mirrors M1
    // ActionCall: all four fields required, no extra keys permitted. When a recipe
    // is present, per-module `oneOf` couples each module constant to its own
    // expose_actions enum so cross-module hallucinations are grammatically impossible.
    if (recipe != nullptr && !recipe->load_modules.empty()) {
        Json branches = Json::array();
        for (const auto& lm : recipe->load_modules) {
            if (lm.expose_actions.empty()) {
                continue;
            }
            Json bprops = Json::object();
            bprops["thought"] = Json::object({{"type", "string"}});
            bprops["module"] = Json::object({{"const", lm.module}});
            bprops["action"] = Json::object({{"type", "string"}, {"enum", lm.expose_actions}});
            bprops["args"] = Json::object({{"type", "object"}});

            Json branch = Json::object();
            branch["type"] = "object";
            branch["properties"] = std::move(bprops);
            branch["required"] = Json::array({"thought", "module", "action", "args"});
            branch["additionalProperties"] = false;
            branches.push_back(std::move(branch));
        }
        if (branches.size() == 1) {
            return branches[0];
        }
        if (!branches.empty()) {
            Json schema = Json::object();
            schema["oneOf"] = std::move(branches);
            return schema;
        }
    }

    Json schema = Json::object();
    schema["type"] = "object";

    Json properties = Json::object();
    properties["thought"] = Json::object({{"type", "string"}});
    properties["module"] = Json::object({{"type", "string"}});
    properties["action"] = Json::object({{"type", "string"}});
    properties["args"] = Json::object({{"type", "object"}});
    schema["properties"] = std::move(properties);

    schema["required"] = Json::array({"thought", "module", "action", "args"});
    schema["additionalProperties"] = false;
    return schema;
}

GenerationParams AgentLoop::generation_params(const TierLimits& limits, const RecipeCartridge* recipe) const {
    GenerationParams params;
    // Non-greedy low-variance sampling calibrated for Qwen 3.5 structured tool calls
    // avoids greedy EOS/punctuation traps while preserving tight schema determinism.
    params.temperature = 0.2;
    params.top_k = 20;
    params.top_p = 0.95;
    params.presence_penalty = 0.5;
    params.think = false;
    params.max_tokens = std::max(static_cast<std::uint32_t>(limits.max_thought_tokens * 8U), 4096U);
    params.constraint = OutputConstraint::json_schema(action_call_schema(recipe));
    return params;
}

TerminalResult AgentLoop::run(const RecipeCartridge& recipe, const std::string& user_request,
                              const LoopConfig& config) {
    const TierLimits& limits = config.tier.limits;

    // Load-time validation (Req 5.4): a structurally invalid recipe — an unknown
    // module, an unexposed/undeclared action, a bad hook, or an initial_state that
    // configure() rejects — throws SchemaError here, before any turn runs.
    registry_.validate_recipe(recipe, module_ctx_);

    // Build the module set: instantiate each loaded module through the registry
    // (held as unique_ptr, no raw owning pointers) and apply its initial_state.
    ModuleContext ctx = module_ctx_;
    if (config.check_cancelled) {
        ctx.check_cancelled = config.check_cancelled;
    }
    std::vector<std::unique_ptr<IAgentModule>> modules;
    modules.reserve(recipe.load_modules.size());
    for (const ModuleLoad& load : recipe.load_modules) {
        std::unique_ptr<IAgentModule> module = registry_.create(load.module, ctx);
        module->configure(load.initial_state);
        modules.push_back(std::move(module));
    }

    // Locate the OrchestratorModule, if the recipe loaded one. The host-facing API
    // (take_intent(), scratchpad(), scratchpad_valid(), completion_output()) lives
    // on the derived type, not IAgentModule, so we down-cast once and keep a
    // non-owning observer pointer — ownership stays in the unique_ptr above (R1
    // forbids raw owning pointers, not observers). A recipe need not load the
    // Orchestrator; `orchestrator == nullptr` means no intent handling and no
    // scratchpad anchoring, handled gracefully below.
    OrchestratorModule* orchestrator = nullptr;
    for (const std::unique_ptr<IAgentModule>& module : modules) {
        if (auto* casted = dynamic_cast<OrchestratorModule*>(module.get()); casted != nullptr) {
            orchestrator = casted;
            break;
        }
    }

    if (orchestrator != nullptr) {
        TaskLedger init_ledger = orchestrator->ledger();
        if (init_ledger.task_id.empty()) {
            init_ledger.task_id = recipe.recipe_id;
        }
        if (init_ledger.objective.empty()) {
            init_ledger.objective = user_request;
        }
        if (init_ledger.steps.empty() && !recipe.scratchpad_checklist.empty()) {
            for (std::size_t i = 0; i < recipe.scratchpad_checklist.size(); ++i) {
                init_ledger.add_step(recipe.scratchpad_checklist[i], "step_" + std::to_string(i + 1));
            }
        }
        orchestrator->set_task_ledger(std::move(init_ledger));
    }

    // Seed the condenser from the active tier (Req 2.1): the pinned prefix carries
    // the system prompt and the rendered action-call schema that constrains every
    // reply, so it is the natural recipe schema text to pin.
    ContextCondenser condenser(limits, config.context_strategy);
    if (orchestrator != nullptr) {
        condenser.set_anchored(orchestrator->scratchpad(),
                               collect_context_summaries(modules),
                               &orchestrator->ledger());
    }
    const std::string sys_prompt = build_recipe_system_prompt(recipe, modules, config.system_prompt, user_request);
    condenser.set_pinned_prefix(sys_prompt,
                                json_io::canonical_dump(action_call_schema(&recipe)));

    // Pin the user's primary task request so all subsequent turns retain context across condensation.
    condenser.set_initial_user_prompt(user_request);

    // Precompute the deterministic generation parameters the turn cycle uses (R14)
    // and capture the backend's starting context position.
    const GenerationParams params = generation_params(limits, &recipe);
    const std::size_t context_baseline = backend_.mark_checkpoint();
    bool pinned_prefix_cached = false;
    std::size_t pinned_baseline = context_baseline;

    // One RunRecord per run (Req 6.1); starts fresh, never imported (Req 6.3).
    RunRecord run_record;
    run_record.task_id = config.task_id;
    run_record.mode = config.mode;
    run_record.instance_id = config.instance_id;
    run_record.step_index = 0;
    run_record.ground_truth = config.ground_truth;

    TerminalResult result;

    // Universal Recipe RunLogger
    std::shared_ptr<logging::RunLogger> logger = config.logger;
    if (!logger && config.enable_disk_logging) {
        logger = std::make_shared<logging::RunLogger>();
        const std::filesystem::path ws = module_ctx_.workspace_root.empty() ? "." : module_ctx_.workspace_root;
        logger->start_session(recipe.recipe_id, config.mode, config.instance_id, user_request, ws);
    }

    auto finish_and_return = [&](TerminalResult res) -> TerminalResult {
        if (logger) {
            std::string outcome_str = (res.outcome == LoopOutcome::success) ? "success" :
                                      (res.outcome == LoopOutcome::aborted) ? "aborted" : "turn_limit";
            logger->log_session_end(res.success, outcome_str, res.completion_output, res.transcript.size());
        }
        return res;
    };

    std::string last_call_sig;
    std::string last_action_output;
    std::string last_action_sig;
    std::string second_last_action_sig;
    std::string last_failed_module;
    std::string last_failed_action;
    std::uint32_t repeat_count = 0;
    std::uint32_t oscillation_count = 0;
    std::uint32_t consecutive_failures = 0;
    std::unordered_map<std::string, std::uint32_t> readonly_call_counts;

    // The deterministic turn cycle (Req 1.2-1.4). Each iteration builds the prompt,
    // regenerates against the full context, parses the reply, resolves and
    // dispatches exactly one action, and records the turn. Ids and any generated
    // text are derived from the turn index only — no clocks, no randomness (Req
    // 1.6). The loop is bounded here by the tier's turn cap; TODO(8.3) replaces
    // this bound with the orchestrator-intent handling, the should_condense() wipe,
    // and the turn-limit terminal semantics.
    for (std::uint64_t turn = 0; turn < limits.max_turns; ++turn) {
        if (config.check_cancelled && config.check_cancelled()) {
            result.outcome = LoopOutcome::aborted;
            result.success = false;
            result.run_record = std::move(run_record);
            return finish_and_return(std::move(result));
        }

        if (logger) {
            logger->log_turn_start(turn);
        }

        // 1. Assemble the prompt. When the backend supports KV/state reuse, cache the
        // invariant leading system prompt + schema prefix ONCE on turn 0 (merged into a
        // single leading Role::system message so Qwen 3.5 Jinja never drops system turns)
        // and only replay dynamic tail/anchored state on subsequent turns.
        const std::vector<Message> messages = condenser.build_messages();
        if (backend_.supports_kv_reuse() && messages.size() >= 2 &&
            messages[0].role == Role::system && messages[1].role == Role::system) {
            if (!pinned_prefix_cached) {
                backend_.rollback_to(context_baseline);
                backend_.append(Message{
                    Role::system,
                    messages[0].content + "\n\nRequired Output JSON Schema:\n" + messages[1].content,
                    {}});
                pinned_baseline = backend_.mark_checkpoint();
                pinned_prefix_cached = true;
            } else {
                backend_.rollback_to(pinned_baseline);
            }
            for (std::size_t i = 2; i < messages.size(); ++i) {
                backend_.append(messages[i]);
            }
        } else {
            backend_.rollback_to(context_baseline);
            for (const Message& message : messages) {
                backend_.append(message);
            }
        }

        // 2. Generate. Pass config.on_token (or empty if omitted). A backend failure
        // (ok == false) is a failed turn — record the backend error, nudge the
        // model, and continue without throwing (Req 1.2).
        const GenerationResult gen = backend_.generate(params, config.on_token);
        if (logger && !gen.thinking.empty()) {
            logger->log_thinking(turn, gen.thinking, "native_think");
        }
        if (!gen.ok) {
            const std::string note =
                "backend generation failed (" + gen.error_code + ": " + gen.error_detail +
                "); the previous attempt produced no usable reply, try again.";
            TurnRecord record;
            record.index = turn;
            record.raw_reply = gen.content;
            record.parsed = false;
            record.note = note;
            result.transcript.push_back(std::move(record));
            if (config.on_turn) {
                config.on_turn(result.transcript.back());
            }
            if (logger) {
                logger->log_guidance(turn, note);
            }
            condenser.push_guidance(note);
            continue;
        }

        // 3. Parse the reply as an ActionCall. A malformed reply (syntax error or a
        // schema violation) surfaces as a SchemaError — never let it escape the
        // loop (Req 1.3). Record the failed turn, push a corrective that restates
        // the required schema, and advance one turn.
        ActionCall call;
        try {
            call = parse<ActionCall>(gen.content);
        } catch (const SchemaError&) {
            const std::string note =
                "reply was not a valid action call; respond with a single JSON object "
                "{\"thought\", \"module\", \"action\", \"args\"} and nothing else.";
            TurnRecord record;
            record.index = turn;
            record.raw_reply = gen.content;
            record.parsed = false;
            record.note = note;
            result.transcript.push_back(std::move(record));
            if (config.on_turn) {
                config.on_turn(result.transcript.back());
            }
            if (logger) {
                logger->log_llm_response(turn, gen.content, false, "");
                logger->log_guidance(turn, note);
            }
            condenser.push_guidance(note);
            continue;
        }

        if (logger) {
            if (!call.thought.empty()) {
                logger->log_thinking(turn, call.thought, "action_thought");
            }
            logger->log_llm_response(turn, gen.content, true, call.thought);
            logger->log_action_call(turn, call.module, call.action, call.args);
        }

        // 4. Resolve the module/action and dispatch exactly one execute_action,
        // surfacing resolution failures (unknown_module, action_not_exposed) and
        // the module's own failures (unknown_action, invalid_args) as-is. All
        // control flow below branches on success/error_code only (Req 1.4, R19).
        const ActionResult action_result = resolve_and_dispatch(modules, recipe, call);

        if (logger) {
            logger->log_action_result(turn, call.module, call.action, action_result.success,
                                      action_result.llm_facing_output, action_result.error_code);
        }

        // 5. Wrap the outcome as a ToolInteraction with a turn-derived id (Req 1.6),
        // record the cycle in the condenser's rolling tail, and append the turn to
        // the transcript.
        ToolInteraction interaction;
        interaction.id = "t" + std::to_string(turn);
        interaction.module = call.module;
        interaction.action = call.action;
        interaction.args = call.args;
        interaction.result = action_result;
        interaction.images = action_result.images;
        condenser.record_tool_cycle(interaction);

        TurnRecord record;
        record.index = turn;
        record.raw_reply = gen.content;
        record.parsed = true;
        record.call = call;
        record.interaction = interaction;
        result.transcript.push_back(std::move(record));
        if (config.on_turn) {
            config.on_turn(result.transcript.back());
        }

        // Anti-repetition detection and loop circuit breaker.
        // Progressive browser actions (scrolling down a long page or clicking pagination/load-more)
        // legitimately reuse identical args across turns while advancing viewport/DOM state.
        const std::string current_call_sig = canonical_call_signature(call);
        const bool progressive_browser_advance =
            action_result.success &&
            is_progressive_browser_action(call.module, call.action) &&
            !last_action_output.empty() &&
            action_result.llm_facing_output != last_action_output;
        if (!progressive_browser_advance &&
            (current_call_sig == last_call_sig ||
             (!action_result.success && call.module == last_failed_module && call.action == last_failed_action))) {
            repeat_count++;
        } else {
            repeat_count = 0;
        }

        if (is_state_mutating_action(call.action)) {
            readonly_call_counts.clear();
        }
        std::uint32_t cumulative_repeat = 0;
        if (is_readonly_discovery_action(call.action)) {
            cumulative_repeat = readonly_call_counts[current_call_sig]++;
        }
        const std::uint32_t effective_repeat = std::max(repeat_count, cumulative_repeat);

        const std::string action_sig = call.module + "::" + call.action;
        if (!second_last_action_sig.empty() && action_sig == second_last_action_sig && action_sig != last_action_sig) {
            oscillation_count++;
        } else if (action_sig != last_action_sig) {
            oscillation_count = 0;
        }

        second_last_action_sig = last_action_sig;
        last_action_sig = action_sig;
        last_call_sig = current_call_sig;
        last_action_output = action_result.llm_facing_output;

        if (!action_result.success) {
            last_failed_module = call.module;
            last_failed_action = call.action;
            consecutive_failures++;
        } else {
            last_failed_module.clear();
            last_failed_action.clear();
            consecutive_failures = 0;
            condenser.clear_guidance();
        }

        std::vector<std::string> pending_turn_guidance;
        if (!action_result.success && (effective_repeat >= 1 || consecutive_failures >= 2)) {
            const bool gated = recipe.post_llm_validation_hook.has_value();
            const std::string recovery_hint = (call.module == "BrowserModule")
                ? "Switch strategy: navigate directly to a known authoritative URL with BrowserModule.browser_navigate, scroll/click a different CSS selector, or inspect local docs with KnowledgeModule.search_local_docs"
                : "Read the error above, inspect or edit the code/arguments (e.g. via WorkspaceModule.surgical_edit or write_file) to fix the root cause";
            emit_guidance(
                condenser, logger, turn,
                "[CRITICAL SYSTEM NOTICE: Action '" + call.module + "::" + call.action +
                "' failed (" + action_result.llm_facing_output +
                "). You MUST NOT re-run this failing action unchanged. " + recovery_hint +
                (gated ? std::string(", then re-verify before calling OrchestratorModule.complete_recipe")
                       : std::string(", or switch strategy")) +
                ".]",
                &pending_turn_guidance);
        } else if (effective_repeat == 1) {
            emit_guidance(
                condenser, logger, turn,
                "[SYSTEM NOTICE: You just called '" + call.module + "::" + call.action +
                "' with identical arguments. Doing this again will trigger the circuit breaker. Change your query/arguments, choose a different module/action, or call OrchestratorModule.complete_recipe to conclude.]",
                &pending_turn_guidance);
        } else if (effective_repeat >= 2) {
            emit_guidance(
                condenser, logger, turn,
                "[CRITICAL SYSTEM WARNING: Repetition loop detected! You must NOT call '" + call.module + "::" + call.action +
                "' again. Immediately call OrchestratorModule.complete_recipe to conclude the task.]",
                &pending_turn_guidance);
        } else if (oscillation_count >= 2) {
            emit_guidance(
                condenser, logger, turn,
                "[SYSTEM WARNING: Oscillation loop detected! You are alternating between '" + call.module + "::" + call.action +
                "' and the previous action without making new progress. Stop repeating this cycle; proceed to store facts with KnowledgeModule.store_fact, finalize the output file, and call OrchestratorModule.complete_recipe.]",
                &pending_turn_guidance);
        }
        if (config.max_repeated_calls > 0 &&
            (effective_repeat >= config.max_repeated_calls || oscillation_count >= config.max_repeated_calls + 2)) {
            result.outcome = LoopOutcome::turn_limit;
            result.success = false;
            result.completion_output = "Task halted by anti-repetition circuit breaker: repeated call '" +
                                       call.module + "::" + call.action + "'";
            result.run_record = std::move(run_record);
            return finish_and_return(std::move(result));
        }

        // 6. Advance the RunRecord (Req 6.2): step_index counts completed turns and
        // last_interaction tracks the most recent dispatch. No session field is
        // ever copied into the scratchpad (D12).
        run_record.step_index = turn + 1;
        run_record.last_interaction = std::move(interaction);

        // 7. Re-anchor the scratchpad into the condenser (Req 6/R6 anchored block).
        // The dispatch above may have mutated the Orchestrator's scratchpad (e.g.
        // checkpoint_notes) or any module's state, so — once per turn after the
        // dispatch — refresh the anchored block from the latest scratchpad plus a
        // lightweight context summary of every loaded module. Skipped when no
        // Orchestrator is loaded: there is no scratchpad to anchor.
        if (orchestrator != nullptr) {
            condenser.set_anchored(orchestrator->scratchpad(), collect_context_summaries(modules), &orchestrator->ledger());
        }

        // 8. Handle the Orchestrator's intent (Req 3.3, Req 5). The module records
        // an intent inside execute_action and the loop acts on it here, after the
        // turn is recorded. take_intent() reads and clears.
        if (orchestrator != nullptr) {
            switch (orchestrator->take_intent()) {
            case OrchestratorModule::Intent::completion_requested: {
                // Completion request -> run the deterministic exit gate (Req 5). On
                // success the loop terminates with the gate's completion output; on
                // a must_succeed failure the gate returns a non-success result whose
                // completion_output carries the hook's on_failure_instruction, which
                // we push as next-turn guidance before continuing the loop.
                TerminalResult gate =
                    run_exit_gate(recipe, modules, orchestrator->completion_output(), logger);
                if (gate.success) {
                    result.outcome = LoopOutcome::success;
                    result.success = true;
                    result.completion_output = std::move(gate.completion_output);
                    result.run_record = std::move(run_record);
                    return finish_and_return(std::move(result));
                }
                // Non-success gate: completion_output carries the hook's
                // on_failure_instruction (see run_exit_gate's contract). Inject it
                // as guidance so the next turn can satisfy the gate.
                if (!gate.completion_output.empty()) {
                    emit_guidance(condenser, logger, turn, std::move(gate.completion_output),
                                  &pending_turn_guidance);
                }
                break;
            }
            case OrchestratorModule::Intent::condense_requested: {
                // The module only requests a condense after validating the
                // scratchpad (Req 3.3), so the loop trusts it. The anchor was just
                // refreshed above, so the wipe re-renders from the latest
                // scratchpad. Re-push any turn guidance so condense() never drops it.
                condenser.condense();
                for (const std::string& g : pending_turn_guidance) {
                    condenser.push_guidance(g);
                }
                break;
            }
            case OrchestratorModule::Intent::none:
                break;
            }
        }

        // Gentle wrap-up reminder when any sufficiently long recipe nears turn exhaustion.
        if (limits.max_turns >= 8 && pending_turn_guidance.empty()) {
            const auto remaining = limits.max_turns - (turn + 1);
            const std::size_t warn_window = (limits.max_turns >= 16) ? 5 : 3;
            if (remaining >= 1 && remaining <= warn_window) {
                std::string pending_ids;
                std::string pending_summary;
                if (orchestrator != nullptr && !orchestrator->ledger().all_mandatory_completed()) {
                    for (const auto& st : orchestrator->ledger().steps) {
                        if (st.status == LedgerStepStatus::pending || st.status == LedgerStepStatus::in_progress) {
                            std::string desc_low = st.description;
                            std::transform(desc_low.begin(), desc_low.end(), desc_low.begin(),
                                           [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
                            // OrchestratorModule.complete_recipe auto-satisfies trailing complete_recipe meta-steps.
                            if (desc_low.find("complete_recipe") != std::string::npos) {
                                continue;
                            }
                            if (!pending_ids.empty()) pending_ids += ", ";
                            pending_ids += "\"" + st.id + "\"";
                            if (!pending_summary.empty()) pending_summary += "; ";
                            pending_summary += st.id + " (" + st.description.substr(0, 60) + ")";
                        }
                    }
                }
                if (remaining == 1 && pending_ids.empty()) {
                    emit_guidance(
                        condenser, logger, turn,
                        "[TURN BUDGET NOTICE: FINAL TURN! All work steps are complete — call OrchestratorModule.complete_recipe NOW.]",
                        &pending_turn_guidance);
                } else {
                    std::string ledger_hint;
                    if (!pending_ids.empty()) {
                        ledger_hint = " Remaining mandatory work steps: " + pending_summary +
                                      ". Finish any unwritten deliverable (e.g. store_fact / create_file research_report.md), "
                                      "then call OrchestratorModule.update_task_ledger with completed_steps: [" +
                                      pending_ids + "] BEFORE calling complete_recipe!";
                    }
                    emit_guidance(
                        condenser, logger, turn,
                        "[TURN BUDGET NOTICE: Only " + std::to_string(remaining) +
                        (remaining == 1 ? " turn remains" : " turns remain") +
                        " before the turn limit. Stop extra web exploration now." +
                        ledger_hint +
                        (pending_ids.empty() ? " Call OrchestratorModule.complete_recipe now." : "") + "]",
                        &pending_turn_guidance);
                }
            }
        }

        // 9. Post-turn condense pressure (Req 2.6). A wipe clears history, so it may
        // only happen once the scratchpad is valid — otherwise the agent would lose
        // its tail before its required notes were saved (Req 3.3). Only condense when
        // there is collapsible tail/summary history, and preserve turn guidance across
        // the wipe so warnings remain visible on the next turn.
        if (condenser.should_condense() && condenser.has_collapsible_history()) {
            const bool scratchpad_ok = orchestrator == nullptr || orchestrator->scratchpad_valid();
            if (scratchpad_ok) {
                if (orchestrator != nullptr) {
                    condenser.set_anchored(orchestrator->scratchpad(),
                                           collect_context_summaries(modules),
                                           &orchestrator->ledger());
                }
                condenser.condense();
                for (const std::string& g : pending_turn_guidance) {
                    condenser.push_guidance(g);
                }
            } else {
                condenser.push_guidance(
                    "context is nearly full; call OrchestratorModule.checkpoint_notes to save "
                    "the required notes so history can be condensed without losing progress.");
            }
        }
    }

    // Turn-limit terminal (Req 1.5): the loop ran every allowed turn without a
    // passed exit gate. Return the accumulated transcript and RunRecord with a
    // non-success turn_limit outcome.
    result.outcome = LoopOutcome::turn_limit;
    result.success = false;
    result.run_record = std::move(run_record);
    return finish_and_return(std::move(result));
}

TerminalResult AgentLoop::run_exit_gate(
    const RecipeCartridge& recipe, const std::vector<std::unique_ptr<IAgentModule>>& modules,
    std::string completion_output, std::shared_ptr<logging::RunLogger> logger) {
    // The deterministic recipe exit gate (Req 5). This runs on a complete_recipe
    // request and issues NO backend generate() call — it never touches backend_.

    // No hook: completion completes immediately (Req 5.2).
    if (!recipe.post_llm_validation_hook) {
        TerminalResult result;
        result.outcome = LoopOutcome::success;
        result.success = true;
        result.completion_output = std::move(completion_output);
        return result;
    }

    const ValidationHook& hook = *recipe.post_llm_validation_hook;

    // Run the hook as a deterministic HookCall: find the loaded module by id and
    // call execute_action directly. A HookCall is a recipe-runner call, not an LLM
    // dispatch (Req 5.5), so the expose_actions check that resolve_and_dispatch
    // applies is deliberately NOT applied here — the hook MAY target an action
    // outside expose_actions. Load-time validate_recipe already guaranteed the
    // module is loaded and the action exists, but we defensively treat a missing
    // module as a gate failure. ValidationHook carries no args, so pass an empty
    // object. The module/action is invoked exactly once (Req 5.1 / Property 15).
    IAgentModule* target = nullptr;
    IAgentModule* browser_mod = nullptr;
    for (const std::unique_ptr<IAgentModule>& module : modules) {
        if (module->module_id() == hook.module) {
            target = module.get();
        }
        if (module->module_id() == "BrowserModule") {
            browser_mod = module.get();
        }
    }

    ActionResult hook_result;
    if (target == nullptr) {
        // Should be unreachable after load-time validation; treat as a failure.
        hook_result.success = false;
        hook_result.error_code = "unknown_module";
        hook_result.llm_facing_output = "hook module '" + hook.module + "' is not loaded";
    } else {
        Json hook_args = Json::object();
        if (hook.module == "KnowledgeModule" &&
            hook.action == "verify_research_deliverable" &&
            browser_mod != nullptr) {
            hook_args["require_urls"] = true;
            Json grounded = Json::array();
            const Json bsnap = browser_mod->export_state_snapshot();
            if (bsnap.is_object()) {
                if (bsnap.contains("visited_urls") && bsnap["visited_urls"].is_array()) {
                    for (const auto& v : bsnap["visited_urls"]) {
                        if (v.is_object() && v.contains("url") && v["url"].is_string()) {
                            grounded.push_back(v["url"].get<std::string>());
                        }
                    }
                }
                if (bsnap.contains("discovered_urls") && bsnap["discovered_urls"].is_array()) {
                    for (const auto& d : bsnap["discovered_urls"]) {
                        if (d.is_string()) {
                            grounded.push_back(d.get<std::string>());
                        }
                    }
                }
                if (grounded.empty() && bsnap.contains("current_url") && bsnap["current_url"].is_string()) {
                    const std::string cur = bsnap["current_url"].get<std::string>();
                    if (!cur.empty()) grounded.push_back(cur);
                }
            }
            hook_args["grounded_urls"] = std::move(grounded);
        }
        hook_result = target->execute_action(hook.action, hook_args);
    }

    if (logger) {
        logger->log_exit_gate(hook.module, hook.action, hook_result.success,
                              hook_result.llm_facing_output, hook_result.error_code);
    }

    // Hook passed: completion succeeds with the completion output (Req 5.3).
    if (hook_result.success) {
        TerminalResult result;
        result.outcome = LoopOutcome::success;
        result.success = true;
        result.completion_output = std::move(completion_output);
        return result;
    }

    // Hook failed with must_succeed==false: an advisory gate. The spec's exit
    // semantics center on must_succeed; a soft gate does not block completion, so
    // allow it to complete with the completion output.
    if (!hook.must_succeed) {
        TerminalResult result;
        result.outcome = LoopOutcome::success;
        result.success = true;
        result.completion_output = std::move(completion_output);
        return result;
    }

    // Hook failed with must_succeed==true: the loop must NOT exit (Req 5.2).
    // Return a non-success result whose completion_output carries the hook's
    // on_failure_instruction plus the granular failure output.
    TerminalResult result;
    result.outcome = LoopOutcome::turn_limit;
    result.success = false;
    std::string failure_feedback = hook.on_failure_instruction;
    if (!hook_result.llm_facing_output.empty()) {
        failure_feedback += "\n\n[VALIDATION FAILURE DETAIL]:\n" + hook_result.llm_facing_output;
    }
    result.completion_output = std::move(failure_feedback);
    return result;
}

ActionResult AgentLoop::resolve_and_dispatch(
    const std::vector<std::unique_ptr<IAgentModule>>& modules, const RecipeCartridge& recipe,
    const ActionCall& call) {
    // Find the loaded module the decision targets. A module the recipe never
    // loaded (or an id the LLM invented) is unresolvable (Req 1.4).
    IAgentModule* target = nullptr;
    for (const std::unique_ptr<IAgentModule>& module : modules) {
        if (module->module_id() == call.module) {
            target = module.get();
            break;
        }
    }
    if (target == nullptr) {
        ActionResult synthetic;
        synthetic.success = false;
        synthetic.error_code = "unknown_module";
        std::string loaded;
        for (std::size_t i = 0; i < modules.size(); ++i) {
            if (i > 0) loaded += ", ";
            loaded += modules[i]->module_id();
        }
        synthetic.llm_facing_output = "no module named '" + call.module + "' is loaded. Loaded modules are: [" + loaded + "]. Only invoke loaded modules.";
        return synthetic;
    }

    // The LLM may only call actions the recipe exposed for this module. Hooks (a
    // deterministic recipe-driven path, not an LLM dispatch) are task 8.4 and are
    // not consulted here. Resolution is purely by identity and the expose list;
    // llm_facing_output text is never inspected (R19).
    for (const ModuleLoad& load : recipe.load_modules) {
        if (load.module != call.module) {
            continue;
        }
        const bool exposed =
            std::find(load.expose_actions.begin(), load.expose_actions.end(), call.action) !=
            load.expose_actions.end();
        if (!exposed) {
            ActionResult synthetic;
            synthetic.success = false;
            synthetic.error_code = "action_not_exposed";
            std::string exp;
            for (std::size_t i = 0; i < load.expose_actions.size(); ++i) {
                if (i > 0) exp += ", ";
                exp += load.expose_actions[i];
            }
            synthetic.llm_facing_output =
                "action '" + call.action + "' is not exposed by module '" + call.module +
                "'. Exposed actions are: [" + exp + "].";
            return synthetic;
        }
        break;
    }

    // Dispatch exactly one action. execute_action never throws on bad LLM input:
    // unknown actions and invalid args come back as failed ActionResults
    // (unknown_action, invalid_args), which are surfaced as-is (Req 1.4).
    return target->execute_action(call.action, call.args);
}

}  // namespace aquila
