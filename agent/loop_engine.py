"""
Aquila OS 3.4 execution loop: continuous agent turns, episode budgets, step entry ritual.
"""
from __future__ import annotations

import json
import os
import re

from plan_validator import get_step_kind_hint, sanitize_step_description
from context_budget import get_context_profile
from context_manager import (
    build_loop_messages,
    estimate_messages_tokens,
    on_step_advance,
    should_force_summarize,
    should_proactive_summarize,
)
from instance_registry import load_workspace_summary
from tool_catalog import CHARACTER_BUILD_FORBIDDEN_FILE_TOOLS
from tool_policy import build_allowed_tool_names
from timeout_policy import is_system_error_response, timeout_compress_retry_enabled
from url_visit_registry import UrlVisitRegistry
from path_visit_registry import PathVisitRegistry
from recon_policy import RECON_PLAYBOOK_MARKDOWN, code_explore_hint
from doc_write_policy import (
    WRITE_PROJECT_MARKDOWN_MAX_CHARS,
    WRITE_PROJECT_MARKDOWN_SOFT_CHARS,
    compact_read_code_outline_result,
)
from episode_tracker import (
    StepRunState,
    episode_count_from_history,
    should_inject_checkpoint_nudge,
)
from web_enrichment import (
    SourceRegistry,
    enrich_search_result,
    register_read_webpage_source,
)
from web_enrichment import quality_from_tool_result

from main import (
    MAX_TOOLS_PER_TURN,
    advance_json_state,
    assemble_agent_response,
    build_strict_schema,
    complete_ledger_state,
    format_attachment_context,
    parse_agent_response,
    save_task_deliverable,
    read_json_state,
    validate_tool_arguments,
    validate_tool_calls,
)


class LoopEngine:
    def __init__(
        self,
        *,
        client,
        executor,
        console,
        action_schema: dict,
        system_prompt: str,
        mode: str,
        mode_label: str,
        plan_dir: str,
        instance_id: str = "default",
        memory=None,
        base_tools: dict | None = None,
        human_research_notes: str = "",
        persona_research_lore: bool = False,
    ):
        self.client = client
        self.executor = executor
        self.console = console
        self.action_schema = action_schema
        self.base_tools = base_tools or {}
        self.system_prompt = system_prompt
        self.mode = mode
        self.mode_label = mode_label
        self.plan_dir = plan_dir
        self.instance_id = instance_id or "default"
        if memory is None:
            from memory_singleton import get_memory
            self.memory = get_memory(self.instance_id)
        else:
            self.memory = memory
        self.workspace_summary = load_workspace_summary(self.instance_id)
        self._schema_widen_attempts = 0
        self._parse_failures = 0
        self._force_full_schema = False
        self.human_research_notes = (human_research_notes or "").strip()
        self.persona_research_lore = bool(persona_research_lore)

    @staticmethod
    def _use_legacy_loop() -> bool:
        return os.getenv("AQUILA_LEGACY_ACT_REFLECT", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    def run(
        self,
        task_name: str,
        user_request: str,
        task_file: str,
        ui_callback=None,
        cancel_check=None,
        text_chunks=None,
        image_payloads=None,
    ) -> str:
        if self._use_legacy_loop():
            from loop_engine_legacy_snapshot import LoopEngine as _LegacyEngine

            legacy = _LegacyEngine(
                client=self.client,
                executor=self.executor,
                console=self.console,
                action_schema=self.action_schema,
                system_prompt=self.system_prompt,
                mode=self.mode,
                mode_label=self.mode_label,
                plan_dir=self.plan_dir,
                instance_id=self.instance_id,
                memory=self.memory,
                base_tools=self.base_tools,
            )
            legacy._user_request = user_request
            legacy._schema_widen_attempts = self._schema_widen_attempts
            legacy._parse_failures = self._parse_failures
            legacy._force_full_schema = self._force_full_schema
            return legacy.run(
                task_name,
                user_request,
                task_file,
                ui_callback=ui_callback,
                cancel_check=cancel_check,
                text_chunks=text_chunks,
                image_payloads=image_payloads,
            )
        return self._run_continuous(
            task_name,
            user_request,
            task_file,
            ui_callback=ui_callback,
            cancel_check=cancel_check,
            text_chunks=text_chunks,
            image_payloads=image_payloads,
        )

    def _run_continuous(
        self,
        task_name: str,
        user_request: str,
        task_file: str,
        ui_callback=None,
        cancel_check=None,
        text_chunks=None,
        image_payloads=None,
    ) -> str:
        ledger_text = f"Initializing {self.mode.title()} Engine for: {task_name}\n"
        self._user_request = user_request
        conversation_history: list[dict] = []
        loop_tick = 0
        max_loop_ticks = int(os.getenv("AQUILA_MAX_LOOP_TICKS", "50"))
        attachments_injected = False
        parse_retries = 0
        recent_tool_signatures: list[str] = []
        step_entry_injected = False
        grace_used_this_step = False
        tools_succeeded_this_step: set[str] = set()
        final_step_stalls = 0
        finalize_nudge_sent = False
        stall_limit = int(os.getenv("AQUILA_FINAL_STEP_STALL_LIMIT", "8"))
        last_reasoning_text = ""
        scrape_seen_urls: set[str] = set()
        url_registry = UrlVisitRegistry()
        path_registry = PathVisitRegistry()
        scrape_budget_remaining: list[int] = [0]
        explore_tool_turns = 0
        timeout_compress_used = False
        outline_logged_this_step = False
        source_registry = SourceRegistry() if self.mode == "research" else None
        self._research_deliverable_draft: str | None = None
        self._persona_read_autosave_done = False

        while loop_tick < max_loop_ticks:
            if cancel_check and cancel_check():
                return "🛑 Task was manually aborted by the user."

            try:
                has_finish = False
                state = read_json_state(task_file)
                if state["status"] == "completed":
                    return (
                        f"✅ {self.mode_label} completed successfully. "
                        "Check the directory for final outputs."
                    )

                current_idx = state["current_step_index"]
                if current_idx >= len(state["steps"]):
                    return "✅ All steps are completed."

                step = state["steps"][current_idx]
                step_kind = step.get("step_kind", "code")
                current_objective, desc_fixed = sanitize_step_description(
                    step.get("description", ""),
                    step_kind=step_kind,
                    step_index=current_idx,
                    total_steps=len(state["steps"]),
                )
                if desc_fixed and current_objective != step.get("description"):
                    step["description"] = current_objective
                    state["steps"][current_idx] = step
                    with open(task_file, "w", encoding="utf-8") as f:
                        json.dump(state, f, indent=4)
                max_step_iterations = step.get("max_iterations", 4)
                url_registry.set_step_index(current_idx)
                path_registry.set_step_index(current_idx)

                episode_count = episode_count_from_history(conversation_history)
                step_run = StepRunState(
                    plan_step_index=current_idx,
                    total_steps=len(state["steps"]),
                    step_kind=step_kind,
                    max_episodes=max_step_iterations,
                    episode_count=episode_count,
                    loop_tick=loop_tick,
                    grace_used=grace_used_this_step,
                    tools_succeeded=set(tools_succeeded_this_step),
                )

                step_entry_msgs: list[dict] = []
                if episode_count == 0 and not step_entry_injected:
                    step_entry_msgs = self._build_step_entry_messages(
                        task_name,
                        step_kind,
                        conversation_history=conversation_history,
                    )
                    step_entry_injected = True

                if (
                    self.mode == "character_build"
                    and step_kind in ("read", "search")
                    and episode_count == 0
                    and not self._persona_read_autosave_done
                ):
                    auto_msg = self._auto_ingest_persona_attachments(
                        task_name,
                        user_request,
                        text_chunks,
                        skip_advance=self.persona_research_lore,
                    )
                    if auto_msg:
                        self._persona_read_autosave_done = True
                        conversation_history.append({
                            "role": "user",
                            "content": f"Tool Outputs:\n{auto_msg}",
                        })
                        ledger_text += f"\n{auto_msg}\n"
                        if ui_callback:
                            ui_callback(ledger_text)
                        if not self.persona_research_lore:
                            advance_json_state(
                                task_file,
                                "OS auto-ingested attachment/user lore into scratchpad.",
                            )
                            self.workspace_summary = on_step_advance(
                                conversation_history=conversation_history,
                                instance_id=self.instance_id,
                                task_name=task_name,
                                advance_summary="OS auto-ingested persona source material.",
                                client=self.client,
                                memory=self.memory,
                            )
                            recent_tool_signatures = []
                            step_entry_injected = False
                            grace_used_this_step = False
                            tools_succeeded_this_step = set()
                            outline_logged_this_step = False
                            path_registry.set_step_index(state["current_step_index"])
                            continue

                user_msg = self._build_user_message(
                    user_request=user_request,
                    current_idx=current_idx,
                    total_steps=len(state["steps"]),
                    current_objective=current_objective,
                    step_run=step_run,
                    step_kind=step_kind,
                )

                if step_run.at_episode_limit():
                    if step_run.can_apply_grace():
                        new_max = step_run.apply_grace(step)
                        max_step_iterations = new_max
                        state["steps"][current_idx] = step
                        with open(task_file, "w", encoding="utf-8") as f:
                            json.dump(state, f, indent=4)
                        grace_used_this_step = True
                        user_msg += (
                            "\n\n⚠️ OS: Budget extended by 2 episodes because tools "
                            "succeeded this step. Finish or save progress soon."
                        )
                        ledger_text += "\n📊 OS: Grace budget extension (+2 episodes).\n"
                    elif current_idx == len(state["steps"]) - 1:
                        user_msg += (
                            "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Output final report "
                            "into `final_report` and use `finish_task`."
                        )
                    else:
                        user_msg += (
                            "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Use `save_research_note` "
                            "then use `mark_objective_complete` to move on."
                        )
                else:
                    user_msg += (
                        "\n\nWork autonomously toward the objective. Each response: brief "
                        "`reasoning`, then `tools`. Continue after tool results until done, "
                        f"then `mark_objective_complete`.\n({step_run.format_progress()})"
                    )
                    if should_inject_checkpoint_nudge(step_run):
                        user_msg += (
                            "\n\n⚠️ OS: Episode budget almost exhausted — complete the step "
                            "or call mark_objective_complete with a summary."
                        )

                if not attachments_injected and text_chunks:
                    user_msg += format_attachment_context(text_chunks)
                    attachments_injected = True

                if (
                    self.mode == "research"
                    and source_registry is not None
                    and current_idx == len(state["steps"]) - 1
                ):
                    source_summary = source_registry.summary_for_prompt()
                    if source_summary:
                        user_msg += f"\n\n{source_summary}"

                message_dict = self._format_user_message(user_msg, image_payloads)
                profile = get_context_profile()
                if (
                    self.mode == "code"
                    and step_kind == "explore"
                    and explore_tool_turns >= 8
                    and not self._recon_tools_used(conversation_history)
                ):
                    user_msg += (
                        "\n\n⚠️ OS: Stuck in explore — call get_directory_tree then "
                        "read_code_outline before more list_directory/search_files."
                    )
                    message_dict = self._format_user_message(user_msg, image_payloads)
                if profile.max_scrape_chars_per_turn > 0:
                    scrape_budget_remaining[0] = profile.max_scrape_chars_per_turn
                self._maybe_compress_conversation(
                    conversation_history,
                    profile,
                    task_name,
                    proactive_note=True,
                )

                active_memory = build_loop_messages(
                    system_prompt=self.system_prompt,
                    rolling_summary=self.workspace_summary,
                    step_entry=step_entry_msgs,
                    conversation_history=conversation_history,
                    user_message=message_dict,
                    profile=profile,
                )

                bt = chr(96) * 3
                prefill_text = f"{bt}json\n" + '{\n  "reasoning": "'
                active_memory.append({"role": "assistant", "content": prefill_text})

                if ui_callback:
                    ui_callback(
                        f"{ledger_text}\n\n⏳ {step_run.format_progress()} · working..."
                    )

                if self._force_full_schema:
                    schema = self.action_schema
                else:
                    schema = self._schema_for_step(current_objective, step_kind)
                temperature = 0.2
                est_tokens = estimate_messages_tokens(active_memory)

                result_dict = self.client.chat(
                    active_memory,
                    temperature=temperature,
                    format=schema,
                    stream=False,
                    estimated_prompt_tokens=est_tokens,
                )
                raw_response = ""
                if isinstance(result_dict, dict):
                    raw_response = result_dict.get("message", {}).get("content", "") or ""

                if is_system_error_response(raw_response):
                    self.console.event(
                        "os_warning",
                        message=raw_response[:200],
                        est_tokens=est_tokens,
                        iteration=loop_tick + 1,
                        phase="act",
                    )
                    cap = profile.in_step_token_cap
                    if (
                        not timeout_compress_used
                        and timeout_compress_retry_enabled(profile)
                        and est_tokens > int(cap * 0.8)
                    ):
                        from context_manager import compress_step_transcript

                        timeout_compress_used = True
                        summary = compress_step_transcript(
                            conversation_history, self.client, task_name
                        )
                        self.workspace_summary = (
                            (self.workspace_summary or "") + "\n" + summary
                        )[-profile.workspace_summary_max_chars or 2000 :]
                        conversation_history[:] = conversation_history[-4:]
                        self.console.event(
                            "context_compress",
                            message="timeout compress retry",
                            est_tokens=est_tokens,
                        )
                        continue
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n❌ {raw_response}",
                    })
                    ledger_text += f"\n\n❌ OS: {raw_response[:300]}\n"
                    if ui_callback:
                        ui_callback(ledger_text)
                    final_step_stalls += 1
                    loop_tick += 1
                    continue

                response_text = assemble_agent_response(prefill_text, raw_response)

                ep_display = step_run.episode_count + 1
                if hasattr(self.console, "log_agent_turn"):
                    self.console.log_agent_turn(
                        step_run.plan_step_index,
                        step_run.total_steps,
                        step_run.step_kind,
                        ep_display,
                        loop_tick + 1,
                        "llm",
                        response_text,
                        est_tokens=est_tokens,
                    )
                else:
                    self.console.log_iteration(
                        loop_tick + 1,
                        response_text,
                        phase="act",
                        est_tokens=est_tokens,
                    )
                header = (
                    f"--- {step_run.format_progress()} · LLM turn {loop_tick + 1} ---"
                )
                ledger_text += f"\n\n{header}\n{response_text}\n"
                if ui_callback:
                    ui_callback(ledger_text)

                conversation_history.append({
                    "role": "assistant",
                    "content": response_text,
                    "_counts_as_episode": False,
                })

                parsed_response = parse_agent_response(response_text, quiet=False)
                if not parsed_response:
                    self._parse_failures += 1
                    if self._parse_failures >= 2:
                        self._force_full_schema = True
                        self.console.print(
                            "[yellow]⚠️ OS: Routed tool schema failed twice; "
                            "falling back to full tool set for this step.[/yellow]"
                        )
                else:
                    self._parse_failures = 0

                parse_ok = bool(parsed_response) and isinstance(
                    parsed_response.get("tools"), list
                )
                if not parse_ok:
                    parse_retries += 1
                    self._pop_last_assistant(conversation_history)
                    retry_msg = (
                        "Tool Outputs:\n❌ OS PARSE ERROR: Your last response was not valid JSON "
                        "with a 'tools' array. Output ONLY a single JSON object matching the schema."
                    )
                    conversation_history.append({"role": "user", "content": retry_msg})
                    ledger_text += f"\n{retry_msg}\n"
                    if ui_callback:
                        ui_callback(ledger_text)
                    if parse_retries >= 2:
                        if self._handle_forced_advance(
                            task_file, task_name, current_idx, state, conversation_history
                        ):
                            parse_retries = 0
                            recent_tool_signatures = []
                            step_entry_injected = False
                            grace_used_this_step = False
                            tools_succeeded_this_step = set()
                            outline_logged_this_step = False
                    continue

                parse_retries = 0

                pending_final_report = parsed_response.get("final_report") or ""

                from main import normalize_tool_calls_list

                tool_calls = normalize_tool_calls_list(parsed_response.get("tools", []))
                last_reasoning_text = str(parsed_response.get("reasoning", "") or "")

                tool_calls, pending_final_report = self._normalize_tool_calls(
                    tool_calls, pending_final_report
                )

                if pending_final_report:
                    save_task_deliverable(
                        task_name,
                        self.mode,
                        pending_final_report,
                        source_registry,
                        memory=self.memory,
                        instance_id=self.instance_id,
                        research_body_fallback=getattr(
                            self, "_research_deliverable_draft", None
                        ),
                    )

                schema_ok, schema_err = validate_tool_calls(tool_calls)
                if not schema_ok:
                    parse_retries += 1
                    self._pop_last_assistant(conversation_history)
                    retry_msg = (
                        f"Tool Outputs:\n❌ OS SCHEMA VIOLATION: {schema_err} "
                        "Constrained decoding requires each tool to use keys "
                        "'name' and 'arguments' only."
                    )
                    conversation_history.append({"role": "user", "content": retry_msg})
                    if parse_retries >= 2 and self._handle_forced_advance(
                        task_file, task_name, current_idx, state, conversation_history
                    ):
                        parse_retries = 0
                        recent_tool_signatures = []
                        step_entry_injected = False
                        grace_used_this_step = False
                        tools_succeeded_this_step = set()
                    continue

                args_ok, args_err = validate_tool_arguments(tool_calls)
                if not args_ok:
                    parse_retries += 1
                    self._pop_last_assistant(conversation_history)
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n❌ OS ARGUMENT VIOLATION: {args_err}",
                    })
                    if parse_retries >= 2 and self._handle_forced_advance(
                        task_file, task_name, current_idx, state, conversation_history
                    ):
                        parse_retries = 0
                        step_entry_injected = False
                    continue

                if len(tool_calls) > MAX_TOOLS_PER_TURN:
                    tool_calls = tool_calls[:MAX_TOOLS_PER_TURN]

                last_tool_output = ""
                has_advance = False
                has_finish = False
                advance_summary = ""
                finish_msg = ""
                ran_non_meta_tool = False
                doc_markdown_writes_this_turn = 0

                for tc in tool_calls:
                    tool_name = tc.get("name", "")
                    if tool_name == "mark_objective_complete":
                        if current_idx == len(state["steps"]) - 1:
                            result = "❌ OS BLOCK: On final step. Use `finish_task`."
                        else:
                            gate = self._tdd_advance_gate(
                                step_kind, conversation_history, last_tool_output
                            )
                            if not gate and step_kind == "explore":
                                gate = self._explore_advance_gate(
                                    conversation_history,
                                    last_tool_output,
                                    tools_succeeded_this_step,
                                )
                            if gate:
                                suffix = (
                                    " Run sync_project_to_disk then run_pytest."
                                    if step_kind in ("tdd_red", "tdd_green")
                                    else ""
                                )
                                result = gate + suffix
                            else:
                                has_advance = True
                                advance_summary = tc.get("arguments", {}).get(
                                    "summary_of_work", "Completed."
                                )
                                result = "✅ State marked complete."
                    elif tool_name == "finish_task":
                        has_finish = True
                        args = tc.get("arguments", {})
                        finish_msg = (
                            args.get("message_to_user")
                            or args.get("summary")
                            or "Task completed."
                        )
                        report_in_args = args.get("final_report")
                        if report_in_args:
                            pending_final_report = report_in_args
                        result = "✅ Finish task triggered."
                    else:
                        ran_non_meta_tool = True
                        args = tc.get("arguments") or {}
                        path_block = path_registry.check_before_execute(tool_name, args)
                        if path_block and path_block.startswith("❌"):
                            result = path_block
                        elif (
                            self.mode == "character_build"
                            and step_kind == "read"
                            and tool_name == "save_research_note"
                            and "save_research_note" in tools_succeeded_this_step
                        ):
                            result = (
                                "❌ OS BLOCK: Ingest note already saved for this step. "
                                "Call mark_objective_complete(summary_of_work="
                                "'Ingested persona lore from user text and attachments.') "
                                "— do NOT call save_research_note again."
                            )
                        elif (
                            self.mode == "character_build"
                            and step_kind == "read"
                            and tool_name == "read_all_research_notes"
                        ):
                            notes = ""
                            try:
                                notes = self.memory.get_scratchpad_notes(task_name) or ""
                            except Exception:
                                pass
                            empty = (
                                not notes.strip()
                                or "No research notes found" in notes
                            )
                            if empty or "read_all_research_notes" in tools_succeeded_this_step:
                                result = (
                                    "❌ OS BLOCK: read_all_research_notes is not allowed on "
                                    "persona ingest. The scratchpad is empty until you "
                                    "call save_research_note with gathered_data from the "
                                    "user description and attachments, then "
                                    "mark_objective_complete."
                                )
                            else:
                                result = (
                                    "❌ OS BLOCK: On ingest step use save_research_note, not "
                                    "read_all_research_notes. Reading notes is for the "
                                    "synthesize step only."
                                )
                        elif (
                            self.mode == "character_build"
                            and tool_name in CHARACTER_BUILD_FORBIDDEN_FILE_TOOLS
                        ):
                            result = (
                                f"❌ OS BLOCK: {tool_name} cannot create persona files. "
                                "On the synthesize step use write_persona_file("
                                "file_path='initialization.md', content='...') with the "
                                "full character bible (800+ characters)."
                            )
                        elif (
                            self.mode == "character_build"
                            and tool_name == "summarize_sources"
                        ):
                            result = (
                                "❌ OS BLOCK: summarize_sources is for research mode only. "
                                "On persona build, use write_persona_file for initialization.md "
                                "(synthesize step) or save_research_note (ingest step)."
                            )
                        elif (
                            self.mode == "character_build"
                            and step_kind == "synthesize"
                            and tool_name == "read_all_research_notes"
                            and "read_all_research_notes" in tools_succeeded_this_step
                        ):
                            result = (
                                "❌ OS BLOCK: Scratchpad notes already loaded this step. "
                                "Call write_persona_file for initialization.md now, "
                                "then mark_objective_complete."
                            )
                        elif (
                            self.mode == "character_build"
                            and step_kind == "synthesize"
                            and tool_name in ("save_research_note", "read_webpage", "web_search")
                        ):
                            result = (
                                f"❌ OS BLOCK: {tool_name} is not used on persona synthesize. "
                                "Call write_persona_file for initialization.md."
                            )
                        elif (
                            self.mode == "character_build"
                            and step_kind in ("read", "search")
                            and tool_name == "write_persona_file"
                        ):
                            result = (
                                f"❌ OS BLOCK: {step_kind} step is ingest/research only. Use "
                                "save_research_note / web_search then mark_objective_complete. "
                                "write_persona_file belongs on the synthesize step."
                            )
                        elif (
                            step_kind in ("explore", "read")
                            and tool_name in ("write_project_markdown", "append_project_markdown")
                        ):
                            result = (
                                "❌ OS BLOCK: write_project_markdown belongs on a "
                                "'code' step after recon. Finish explore with "
                                "mark_objective_complete, then write ARCHITECTURE.md "
                                "and README.md on the code step."
                            )
                        elif tool_name in (
                            "write_project_markdown",
                            "append_project_markdown",
                        ) and doc_markdown_writes_this_turn >= 1:
                            result = (
                                f"❌ OS BLOCK: Only one {tool_name} call per turn "
                                "(JSON truncation). Run again next turn for the other file "
                                "or use append_project_markdown."
                            )
                        elif tool_name in (
                            "search_files",
                            "get_directory_tree",
                            "list_directory",
                        ):
                            from recon_policy import normalize_code_tool_path

                            norm_path, path_note = normalize_code_tool_path(
                                str(args.get("path", "."))
                            )
                            if norm_path != args.get("path"):
                                args = {**args, "path": norm_path}
                                tc = {**tc, "arguments": args}
                            self.console.log_tool_start(tool_name, args)
                            execution_results = self.executor.execute([tc])
                            result = (
                                execution_results[0] if execution_results else "No output."
                            )
                            if path_note:
                                result += (
                                    f"\n⚠️ OS: {tool_name} path normalized ({path_note}). "
                                    "Use path '.' for CODE_PROJECT_ROOT."
                                )
                            if tool_name in (
                                "list_directory",
                                "get_directory_tree",
                                "read_code_outline",
                            ):
                                path_registry.record_tool(tool_name, args)
                        elif tool_name == "read_webpage":
                            page_url = args.get("url", "")
                            block_msg = url_registry.check_read_webpage(page_url)
                            if block_msg:
                                result = block_msg
                            else:
                                self.console.log_tool_start(tool_name, args)
                                execution_results = self.executor.execute([tc])
                                result = (
                                    execution_results[0]
                                    if execution_results
                                    else "No output."
                                )
                                quality = quality_from_tool_result(result, page_url)
                                url_registry.register_visit(
                                    page_url,
                                    via="read_webpage",
                                    quality=quality,
                                    body=result,
                                    step_index=current_idx,
                                )
                                register_read_webpage_source(
                                    source_registry,
                                    page_url,
                                    result,
                                    step_index=current_idx,
                                )
                        elif path_block:
                            result = path_block
                        else:
                            args, research_note = self._normalize_research_tool_args(
                                tool_name, args, task_name
                            )
                            if research_note:
                                tc = {**tc, "arguments": args}
                            self.console.log_tool_start(tool_name, args)
                            execution_results = self.executor.execute([tc])
                            result = (
                                execution_results[0] if execution_results else "No output."
                            )
                            if (
                                self.mode == "research"
                                and tool_name == "save_research_note"
                                and research_note
                                and result
                                and not str(result).startswith("❌")
                            ):
                                from research_deliverable import pick_best_deliverable_body

                                body = pick_best_deliverable_body(research_note)
                                if body:
                                    self._research_deliverable_draft = body
                                    result += (
                                        "\n⚠️ OS: Large synthesis note stored as deliverable "
                                        "draft. On the final step, put the report in top-level "
                                        "`final_report` (or call finish_task — the OS will "
                                        "recover this draft if final_report is empty)."
                                    )
                            if (
                                self.mode == "character_build"
                                and step_kind == "read"
                                and tool_name == "save_research_note"
                                and result
                                and not str(result).startswith("❌")
                            ):
                                result += (
                                    "\n✅ OS: Lore saved. Call mark_objective_complete now "
                                    "(or the OS will auto-advance after this turn)."
                                )
                            if (
                                self.mode == "character_build"
                                and step_kind == "synthesize"
                                and tool_name == "read_all_research_notes"
                                and result
                                and not str(result).startswith("❌")
                            ):
                                result += (
                                    "\n✅ OS: Notes loaded. Call write_persona_file for "
                                    "initialization.md now — do NOT call summarize_sources."
                                )
                            if (
                                self.mode == "character_build"
                                and step_kind == "synthesize"
                                and tool_name == "write_persona_file"
                                and result
                                and result.startswith("✅")
                            ):
                                result += (
                                    "\n✅ OS: initialization.md written. Call "
                                    "mark_objective_complete (or OS will auto-advance)."
                                )
                            if tool_name == "read_code_outline":
                                if outline_logged_this_step:
                                    result = (
                                        "Tool read_code_outline returned: "
                                        "(outline already in context — see prior turn)"
                                    )
                                else:
                                    result = compact_read_code_outline_result(result)
                                    outline_logged_this_step = True
                            if tool_name in (
                                "list_directory",
                                "get_directory_tree",
                                "read_code_outline",
                            ):
                                path_registry.record_tool(tool_name, args)
                            if tool_name == "web_search":
                                result = enrich_search_result(
                                    result,
                                    scrape_seen_urls,
                                    source_registry,
                                    get_context_profile(),
                                    step_index=current_idx,
                                    console=self.console,
                                    url_registry=url_registry,
                                    scrape_budget_remaining=scrape_budget_remaining,
                                    run_logger=self.console,
                                )
                        if result and "❌ Error" not in result and not result.startswith("❌"):
                            tools_succeeded_this_step.add(tool_name)
                        if tool_name in (
                            "write_project_markdown",
                            "append_project_markdown",
                        ) and result and result.startswith("✅"):
                            doc_markdown_writes_this_turn += 1

                    last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                    self.console.log_tool_execution(
                        tool_name, tc.get("arguments", {}), result
                    )

                if last_tool_output:
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:{last_tool_output}",
                    })
                    self._maybe_compress_conversation(
                        conversation_history,
                        profile,
                        task_name,
                        proactive_note=True,
                    )
                    ledger_text += f"\n{last_tool_output}\n"
                    if ui_callback:
                        ui_callback(ledger_text)

                if (
                    not has_advance
                    and not has_finish
                    and self.mode == "character_build"
                    and step_kind == "read"
                    and "save_research_note" in tools_succeeded_this_step
                ):
                    has_advance = True
                    advance_summary = (
                        "Ingested persona source material into scratchpad; "
                        "advancing to synthesize initialization.md."
                    )
                    last_tool_output += (
                        "\n\n✅ OS: Read-step ingest complete. Advancing to synthesize — "
                        "call write_persona_file once (lore is in scratchpad)."
                    )
                    conversation_history[-1] = {
                        "role": "user",
                        "content": f"Tool Outputs:{last_tool_output}",
                    }

                if (
                    not has_advance
                    and not has_finish
                    and self.mode == "character_build"
                    and step_kind == "synthesize"
                    and "write_persona_file" in tools_succeeded_this_step
                ):
                    has_advance = True
                    advance_summary = (
                        "Wrote initialization.md; advancing to finalize_persona."
                    )
                    last_tool_output += (
                        "\n\n✅ OS: Synthesize step complete. Advancing to finalize — "
                        "call finalize_persona then finish_task."
                    )
                    conversation_history[-1] = {
                        "role": "user",
                        "content": f"Tool Outputs:{last_tool_output}",
                    }

                if has_advance:
                    timeout_compress_used = False
                    advance_json_state(task_file, advance_summary)
                    self.workspace_summary = on_step_advance(
                        conversation_history=conversation_history,
                        instance_id=self.instance_id,
                        task_name=task_name,
                        advance_summary=advance_summary,
                        client=self.client,
                        memory=self.memory,
                    )
                    recent_tool_signatures = []
                    step_entry_injected = False
                    grace_used_this_step = False
                    tools_succeeded_this_step = set()
                    explore_tool_turns = 0
                    outline_logged_this_step = False
                    path_registry.set_step_index(state["current_step_index"])
                    self._schema_widen_attempts = 0
                    self._parse_failures = 0
                    self._force_full_schema = False
                    self._persona_read_autosave_done = False

                if has_finish:
                    saved = save_task_deliverable(
                        task_name,
                        self.mode,
                        pending_final_report,
                        source_registry,
                        memory=self.memory,
                        instance_id=self.instance_id,
                        research_body_fallback=getattr(
                            self, "_research_deliverable_draft", None
                        ),
                    )
                    complete_ledger_state(task_file, finish_msg)
                    self.memory.store_experience(
                        task_name, finish_msg, instance_id=self.instance_id
                    )
                    if saved:
                        finish_msg += f"\n\n📄 Final report saved to: {saved}"
                    return finish_msg

                if (
                    episode_count_from_history(conversation_history)
                    >= max_step_iterations
                    and not has_advance
                    and not has_finish
                ):
                    if current_idx == len(state["steps"]) - 1:
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                "Tool Outputs:\n⚠️ OS FORCED: Iteration limit reached on final step. "
                                "You must use finish_task now."
                            ),
                        })
                    elif not self._try_smart_override(
                        task_file,
                        conversation_history,
                        grace_used_this_step,
                        tools_succeeded_this_step,
                    ):
                        advance_json_state(
                            task_file, "OS forced advance (iteration limit)"
                        )
                        self.workspace_summary = on_step_advance(
                            conversation_history=conversation_history,
                            instance_id=self.instance_id,
                            task_name=task_name,
                            advance_summary="OS forced advance (iteration limit)",
                            client=self.client,
                            memory=self.memory,
                        )
                        recent_tool_signatures = []
                        step_entry_injected = False
                        grace_used_this_step = False
                        tools_succeeded_this_step = set()
                    continue

                for tc in tool_calls:
                    if isinstance(tc, dict):
                        sig = json.dumps(
                            {"name": tc.get("name"), "arguments": tc.get("arguments")},
                            sort_keys=True,
                        )
                        recent_tool_signatures.append(sig)

                block_msg = url_registry.duplicate_tool_block(recent_tool_signatures)
                if block_msg:
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n{block_msg}",
                    })
                    recent_tool_signatures = []
                else:
                    dup_msg = url_registry.duplicate_tool_warning(
                        recent_tool_signatures
                    )
                    if dup_msg:
                        conversation_history.append({
                            "role": "user",
                            "content": f"Tool Outputs:\n{dup_msg}",
                        })

                if ran_non_meta_tool:
                    if step_kind == "explore":
                        explore_tool_turns += 1
                    for msg in reversed(conversation_history):
                        if msg.get("role") == "assistant":
                            msg["_counts_as_episode"] = True
                            break

                if (
                    current_idx == len(state["steps"]) - 1
                    and not has_finish
                    and ran_non_meta_tool
                ):
                    final_step_stalls += 1
                    if final_step_stalls == 6 and not finalize_nudge_sent:
                        finalize_nudge_sent = True
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                "Tool Outputs:\n⚠️ OS: You have enough sources. Call "
                                "`save_research_note` with key findings, then output "
                                "`final_report` and `finish_task` in one JSON turn."
                            ),
                        })
                    if final_step_stalls >= stall_limit:
                        partial = self._build_partial_research_report(
                            task_name,
                            last_reasoning_text,
                            source_registry,
                        )
                        out_path = save_task_deliverable(
                            task_name,
                            self.mode,
                            partial,
                            source_registry,
                            memory=self.memory,
                            instance_id=self.instance_id,
                        )
                        complete_ledger_state(
                            task_file, "OS forced completion (final step stall limit)"
                        )
                        if out_path:
                            return (
                                "⚠️ OS forced task completion: too many retries on the final step. "
                                f"Partial report saved: {out_path}"
                            )
                        return (
                            "⚠️ OS forced task completion: too many retries on the final step."
                        )

                loop_tick += 1

            except Exception as e:
                return f"OS Error: {str(e)}"

        return "⚠️ OS halted: Maximum loop ticks reached."

    @staticmethod
    def _normalize_tool_calls(
        tool_calls: list, pending_final_report: str
    ) -> tuple[list, str]:
        """Hoist final_report from finish_task args (legacy shape) before arg validation."""
        report = pending_final_report or ""
        for tc in tool_calls:
            if not isinstance(tc, dict) or tc.get("name") != "finish_task":
                continue
            args = tc.get("arguments")
            if not isinstance(args, dict):
                continue
            if "final_report" in args:
                report = args.pop("final_report") or report
        return tool_calls, report

    def _schema_for_step(self, current_objective: str, step_kind: str) -> dict:
        profile = get_context_profile()
        if not self.base_tools or os.getenv("AQUILA_ROUTE_TOOLS", "1").strip().lower() in (
            "0",
            "false",
            "no",
            "off",
        ):
            return self.action_schema
        routed = self.memory.route_tools(
            current_objective, max_tools=profile.routed_tool_cap
        )
        allowed = build_allowed_tool_names(
            mode=self.mode,
            step_kind=step_kind,
            routed=routed,
            all_tool_names=set(self.base_tools.keys()),
            objective=current_objective,
            user_request=getattr(self, "_user_request", ""),
            persona_research_lore=self.persona_research_lore,
        )
        if (
            len(allowed) < 8
            and self._schema_widen_attempts < 2
            and self.mode != "character_build"
        ):
            self._schema_widen_attempts += 1
            routed = self.memory.route_tools(
                current_objective, max_tools=min(32, profile.routed_tool_cap + 8)
            )
            allowed = build_allowed_tool_names(
                mode=self.mode,
                step_kind=step_kind,
                routed=routed,
                all_tool_names=set(self.base_tools.keys()),
                objective=current_objective,
                user_request=getattr(self, "_user_request", ""),
                persona_research_lore=self.persona_research_lore,
            )
        subset = {k: self.base_tools[k] for k in allowed if k in self.base_tools}
        if not subset:
            return self.action_schema
        return build_strict_schema(subset)

    def _execute_tool_batch(
        self,
        tool_calls: list[dict],
        *,
        path_registry: PathVisitRegistry,
        outline_logged_flag: bool,
    ) -> dict:
        """Run a small batch of tools (e.g. stashed from reflect). Returns summary dict."""
        from main import normalize_tool_calls_list

        last_parts: list[str] = []
        executed = 0
        outline_logged = outline_logged_flag
        for tc in normalize_tool_calls_list(tool_calls):
            if not isinstance(tc, dict):
                continue
            tool_name = tc.get("name", "")
            args = tc.get("arguments") or {}
            path_block = path_registry.check_before_execute(tool_name, args)
            if path_block and path_block.startswith("❌"):
                result = path_block
            elif tool_name in (
                "search_files",
                "get_directory_tree",
                "list_directory",
            ):
                from recon_policy import normalize_code_tool_path

                norm_path, path_note = normalize_code_tool_path(str(args.get("path", ".")))
                if norm_path != args.get("path"):
                    args = {**args, "path": norm_path}
                    tc = {**tc, "arguments": args}
                self.console.log_tool_start(tool_name, args)
                execution_results = self.executor.execute([tc])
                result = execution_results[0] if execution_results else "No output."
                if path_note:
                    result += f"\n⚠️ OS: {tool_name} path normalized ({path_note})."
                path_registry.record_tool(tool_name, args)
            else:
                self.console.log_tool_start(tool_name, args)
                execution_results = self.executor.execute([tc])
                result = execution_results[0] if execution_results else "No output."
            if tool_name == "read_code_outline":
                if outline_logged:
                    result = (
                        "Tool read_code_outline returned: "
                        "(outline already in context — see prior turn)"
                    )
                else:
                    result = compact_read_code_outline_result(result)
                    outline_logged = True
            last_parts.append(f"\nTool '{tool_name}' result:\n{result}\n")
            self.console.log_tool_execution(tool_name, args, result)
            executed += 1
        return {
            "last_output": "".join(last_parts),
            "executed": executed,
            "outline_logged": outline_logged,
        }

    @staticmethod
    def _recon_complete_in_history(conversation_history: list[dict]) -> bool:
        blob = LoopEngine._tool_output_blob(conversation_history, "")
        lower = blob.lower()
        return "read_code_outline" in lower or "get_directory_tree" in lower

    def _build_step_entry_messages(
        self,
        task_name: str,
        step_kind: str,
        *,
        conversation_history: list[dict] | None = None,
    ) -> list[dict]:
        try:
            notes = self.memory.get_scratchpad_notes(task_name)
        except Exception:
            notes = "No research notes found for this task."
        if self.mode == "code" and step_kind == "explore":
            hint = code_explore_hint()
        elif self.mode == "character_build" and step_kind == "search":
            hint = (
                "Web lore research: web_search and read_webpage for authoritative sources; "
                "save_research_note with distilled lore. No write_persona_file. "
                "Then mark_objective_complete."
            )
        elif self.mode == "character_build" and step_kind == "read":
            hint = (
                "Persona ingest only: save_research_note once with user+attachment lore, "
                "then mark_objective_complete. Do NOT call read_all_research_notes "
                "(scratchpad is empty until you save). Do NOT call write_persona_file."
            )
        elif self.mode == "character_build" and step_kind == "synthesize":
            hint = (
                "Lore is in the SCRATCHPAD section below. write_persona_file once for "
                "initialization.md (800+ chars) including a **Scene agency** section "
                "(proactive play, minimal questions, no assistant deferral), then "
                "mark_objective_complete. Do NOT call summarize_sources. "
                "read_all_research_notes at most once."
            )
        else:
            hint = get_step_kind_hint(step_kind)
        cwd = os.getcwd()
        parts = [
            f"WORKSPACE_ROOT: {cwd}",
            f"INSTANCE: {self.instance_id}",
            f"STEP_KIND: {step_kind}",
            f"OS HINT: {hint}",
        ]
        if self.mode == "code":
            parts.append(RECON_PLAYBOOK_MARKDOWN)
            if (
                step_kind == "code"
                and conversation_history
                and self._recon_complete_in_history(conversation_history)
            ):
                parts.append(
                    "RECON COMPLETE: Documentation workflow — one file per turn, "
                    f"<= {WRITE_PROJECT_MARKDOWN_SOFT_CHARS} chars per write_project_markdown call. "
                    "Turn A: write_project_markdown('ARCHITECTURE.md', …). "
                    "Turn B: write_project_markdown('README.md', …) or append_project_markdown "
                    "if a file needs more sections. "
                    "Do not bundle two writes in one tools array. "
                    "Do not re-run get_directory_tree or read_code_outline."
                )
        if self.workspace_summary:
            parts.append(
                f"--- WORKSPACE SUMMARY ---\n{self.workspace_summary[:8000]}\n--- END ---"
            )
        if self.mode == "code":
            try:
                from tool_library.code_canvas_tools import get_active_project_scope

                scope = get_active_project_scope()
                if scope:
                    parts.insert(
                        1,
                        f"CODE_PROJECT_ROOT: {scope['root']} "
                        f"(project={scope['project_name']}, {scope['workspace_mode']})",
                    )
                    parts.insert(
                        2,
                        "SCOPE: Work ONLY inside CODE_PROJECT_ROOT. Use get_directory_tree "
                        "(max_depth=2) on the project root, then read_code_outline — NOT "
                        "list_directory on the parent workspace or get_directory_tree on agent-projects.",
                    )
                else:
                    parts.insert(
                        1,
                        "CODE_PROJECT_ROOT: (none) — call init_code_project or "
                        "attach_existing_repo before file edits.",
                    )
            except ImportError:
                pass
        if (
            notes
            and "No research notes found" not in notes
            and not (self.mode == "character_build" and step_kind == "read")
        ):
            if self.mode == "character_build" and step_kind == "synthesize":
                from tool_library.agent_tools import _scratchpad_byte_limit

                cap = _scratchpad_byte_limit() * 4
                if len(notes) > cap:
                    notes = (
                        notes[:cap]
                        + "\n... [step brief capped — call read_all_research_notes once "
                        "if you need remaining scratchpad text, then write_persona_file]"
                    )
            parts.append(f"--- SCRATCHPAD (prior steps) ---\n{notes}\n--- END SCRATCHPAD ---")
        if self.mode == "research" and self.human_research_notes:
            from research_journal import format_journal_context

            parts.append(format_journal_context(self.human_research_notes).strip())
        return [{"role": "user", "content": "\n".join(parts)}]

    def _build_user_message(
        self,
        *,
        user_request: str,
        current_idx: int,
        total_steps: int,
        current_objective: str,
        step_run: StepRunState | None = None,
        step_attempts: int | None = None,
        max_step_iterations: int | None = None,
        turn_phase: str | None = None,
        step_kind: str,
    ) -> str:
        progress = step_run.format_progress() if step_run else (
            f"Step {current_idx + 1}/{total_steps} ({step_kind})"
        )
        return (
            f"**Ultimate Topic/Goal:** {user_request}\n\n"
            f"**YOUR CURRENT OBJECTIVE ({progress}):**\n"
            f"> {current_objective}\n"
            f"**Step kind:** {step_kind}"
        )

    def _format_user_message(self, user_msg: str, image_payloads) -> dict:
        if image_payloads:
            content_list = [{"type": "text", "text": user_msg}]
            for img_b64 in image_payloads:
                prefix = "data:image/jpeg;base64,"
                clean_b64 = img_b64.split(",", 1)[-1] if "," in img_b64 else img_b64
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"{prefix}{clean_b64}"},
                })
            return {"role": "user", "content": content_list}
        return {"role": "user", "content": user_msg}

    @staticmethod
    def _pop_last_assistant(conversation_history: list[dict]) -> None:
        if conversation_history and conversation_history[-1].get("role") == "assistant":
            conversation_history.pop()

    def _handle_forced_advance(
        self,
        task_file: str,
        task_name: str,
        current_idx: int,
        state: dict,
        conversation_history: list[dict],
    ) -> bool:
        if current_idx == len(state["steps"]) - 1:
            conversation_history.append({
                "role": "user",
                "content": (
                    "Tool Outputs:\n⚠️ OS OVERRIDE: Parse failures exceeded. "
                    "Put final_report at the top level of your JSON (not inside finish_task) "
                    "and call finish_task with only message_to_user."
                ),
            })
            return False
        advance_json_state(task_file, "OS forced advance (parse failure limit)")
        on_step_advance(
            conversation_history=conversation_history,
            instance_id=self.instance_id,
            task_name=task_name,
            advance_summary="OS forced advance (parse failure limit)",
            client=self.client,
            memory=self.memory,
        )
        return True

    @staticmethod
    def _try_smart_override(
        task_file: str,
        conversation_history: list[dict],
        grace_used: bool,
        tools_succeeded: set[str],
    ) -> bool:
        """Inject save-and-advance hint before forcing advance. Returns True if injected."""
        if tools_succeeded or grace_used:
            conversation_history.append({
                "role": "user",
                "content": (
                    "Tool Outputs:\n⚠️ OS: Step budget exhausted. "
                    "Call save_research_note with partial progress, then mark_objective_complete."
                ),
            })
            return True
        return False

    @staticmethod
    def _recent_pytest_output(conversation_history: list[dict], current_chunk: str) -> str:
        parts = [current_chunk or ""]
        for msg in reversed(conversation_history):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and "Tool 'run_pytest' result:" in content:
                parts.append(content)
                break
        return "\n".join(parts)

    @staticmethod
    def _tdd_advance_gate(
        step_kind: str,
        conversation_history: list[dict],
        last_tool_output: str,
    ) -> str | None:
        """Soft gates for Code Mode TDD steps."""
        if step_kind not in ("tdd_red", "tdd_green"):
            return None
        blob = LoopEngine._recent_pytest_output(conversation_history, last_tool_output)
        lower = blob.lower()
        if step_kind == "tdd_red":
            if "failed" not in lower and "error" not in lower:
                return (
                    "❌ OS BLOCK (tdd_red): Call run_pytest and confirm failing tests "
                    "(output should mention failed) before mark_objective_complete."
                )
        if step_kind == "tdd_green":
            failed_m = re.search(r"(\d+) failed", blob)
            if failed_m and int(failed_m.group(1)) > 0:
                return (
                    "❌ OS BLOCK (tdd_green): run_pytest must show 0 failed "
                    "before mark_objective_complete."
                )
            if "✅ pytest" not in blob and "passed" not in lower:
                return (
                    "❌ OS BLOCK (tdd_green): Call run_pytest until tests pass "
                    "before mark_objective_complete."
                )
        return None

    @staticmethod
    def _tool_output_blob(conversation_history: list[dict], last_tool_output: str) -> str:
        parts = [last_tool_output or ""]
        for msg in conversation_history:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and "Tool '" in content:
                parts.append(content)
        return "\n".join(parts)

    @staticmethod
    def _recon_tools_used(conversation_history: list[dict]) -> bool:
        blob = LoopEngine._tool_output_blob(conversation_history, "")
        lower = blob.lower()
        return "get_directory_tree" in lower or "read_code_outline" in lower

    @staticmethod
    def _explore_advance_gate(
        conversation_history: list[dict],
        last_tool_output: str,
        tools_succeeded: set[str] | None = None,
    ) -> str | None:
        succeeded = tools_succeeded or set()
        read_tools = {
            "read_file_region",
            "read_file",
            "read_file_smart",
            "grep_repo",
            "search_files",
            "index_codebase_for_search",
            "write_project_markdown",
        }
        if (
            "get_directory_tree" in succeeded
            and "read_code_outline" in succeeded
            and (succeeded & read_tools)
        ):
            return None

        blob = LoopEngine._tool_output_blob(conversation_history, last_tool_output)
        lower = blob.lower()
        has_outline = "read_code_outline" in lower or "project:" in lower
        has_tree = "get_directory_tree" in lower or "directory tree for:" in lower
        has_search = (
            "index_codebase" in lower
            or "semantic_code_search" in lower
            or "grep_repo" in lower
            or "search_files" in lower
            or "web_search" in lower
            or "read_webpage" in lower
        )
        has_region = "read_file_region" in lower or "read_file" in lower
        has_doc = "write_project_markdown" in lower
        if has_outline and (has_search or has_region or has_doc):
            return None
        if has_tree and has_outline and (has_region or has_doc):
            return None
        if has_tree and has_region:
            return None
        if has_search and has_region:
            return None
        return (
            "❌ OS BLOCK (explore): Complete reconnaissance first — "
            "get_directory_tree + read_code_outline, then read_file_region or grep_repo "
            "(or write_project_markdown for doc tasks) before mark_objective_complete."
        )

    def _maybe_compress_conversation(
        self,
        conversation_history: list[dict],
        profile,
        task_name: str,
        *,
        proactive_note: bool = False,
    ) -> bool:
        """Compress in-step history when approaching token cap. Returns True if compressed."""
        from context_manager import compress_step_transcript

        est = estimate_messages_tokens(conversation_history)
        if not (
            should_force_summarize(profile, est)
            or should_proactive_summarize(profile, est)
        ):
            return False
        summary = compress_step_transcript(conversation_history, self.client, task_name)
        self.workspace_summary = (
            (self.workspace_summary or "") + "\n" + summary
        )[-profile.workspace_summary_max_chars or 2000 :]
        conversation_history[:] = conversation_history[-4:]
        if proactive_note and should_proactive_summarize(profile, est):
            conversation_history.append({
                "role": "user",
                "content": (
                    "Tool Outputs:\n⚠️ OS: Prior tool output was summarized to stay within "
                    "context limits. Do not repeat the same search query."
                ),
            })
        self.console.event(
            "context_compress",
            message="proactive/post-tool compress",
            est_tokens=est,
        )
        return True

    def _auto_ingest_persona_attachments(
        self,
        task_name: str,
        user_request: str,
        text_chunks: list | None,
        *,
        skip_advance: bool = False,
    ) -> str | None:
        """Save user description + attachment chunks to scratchpad; optionally skip LLM ingest."""
        chunks = [c for c in (text_chunks or []) if c and str(c).strip()]
        if not chunks:
            return None
        try:
            notes = self.memory.get_scratchpad_notes(task_name) or ""
        except Exception:
            notes = ""
        if notes.strip() and "No research notes found" not in notes:
            return None

        from main import format_attachment_context
        from tool_library.agent_tools import save_research_note

        parts: list[str] = []
        if (user_request or "").strip():
            parts.append(f"## User description\n{user_request.strip()}")
        attachment_block = format_attachment_context(chunks).strip()
        if attachment_block:
            parts.append(attachment_block)
        body = "\n\n".join(p for p in parts if p)
        if not body.strip():
            return None

        result = save_research_note(task_name, body)
        if str(result).startswith("❌"):
            return result
        advance_line = (
            "Attachment lore saved — continue this step (web_search if research enabled)."
            if skip_advance
            else "Skipping LLM ingest turn — advancing to synthesize step."
        )
        return (
            f"✅ OS: Pre-ingested {len(chunks)} attachment chunk(s) and user description "
            f"into scratchpad.\n{result}\n{advance_line}"
        )

    @staticmethod
    def _normalize_research_tool_args(
        tool_name: str, args: dict, task_name: str
    ) -> tuple[dict, str | None]:
        """Force scratchpad tools to use the active task name; return note text if present."""
        if tool_name not in (
            "save_research_note",
            "read_all_research_notes",
            "summarize_sources",
        ):
            return args, None
        args = dict(args or {})
        note_text = None
        if tool_name == "save_research_note":
            note_text = str(args.get("gathered_data", "") or "")
        if args.get("task_name") and args.get("task_name") != task_name:
            args["task_name"] = task_name
        elif not args.get("task_name"):
            args["task_name"] = task_name
        return args, note_text

    def _build_partial_research_report(
        self,
        task_name: str,
        last_reasoning: str,
        source_registry: SourceRegistry | None,
    ) -> str:
        """Assemble a partial markdown report when finalize stalls out."""
        parts = [
            "# Partial report (task hit iteration limit)",
            "",
            "The agent could not call `finish_task` before the final-step stall limit.",
            "",
        ]
        if last_reasoning.strip():
            parts.extend(["## Last reasoning", "", last_reasoning.strip(), ""])
        try:
            notes = self.memory.get_scratchpad_notes(task_name)
        except Exception:
            notes = ""
        if notes and notes.strip():
            parts.extend(["## Research notes (scratchpad)", "", notes.strip(), ""])
        if source_registry is not None and source_registry.records:
            parts.extend(["", source_registry.format_bibliography_markdown()])
        return "\n".join(parts)

    @staticmethod
    def _duplicate_tool_warning(recent_tool_signatures: list[str]) -> str | None:
        if len(recent_tool_signatures) < 2:
            return None
        if recent_tool_signatures[-1] == recent_tool_signatures[-2]:
            if len(recent_tool_signatures) >= 3 and recent_tool_signatures[-3] == recent_tool_signatures[-1]:
                return (
                    "⚠️ OS WARNING: You repeated the same tool call three times. "
                    "Use mark_objective_complete or a different tool."
                )
            return (
                "⚠️ OS WARNING: You repeated the same tool call twice. "
                "Try a different approach or mark_objective_complete."
            )
        return None
