"""
Aquila OS 3.5 execution loop: continuous agent turns, episode budgets, step entry ritual.
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .plan_validator import DELEGATE_MODES, get_step_kind_hint, sanitize_step_description
from .mcp_bridge import mcp_allowed_for_mode
from agent.policies import get_context_profile
from agent.policies import (
    build_loop_messages,
    estimate_messages_tokens,
    on_step_advance,
    should_force_summarize,
    should_proactive_summarize,
)
from agent.storage import load_workspace_summary
from agent.core.loop_settings import run_state_enabled, capability_repeat_guard_enabled
from agent.core.run_state import TaskRunContext
from agent.policies import CHARACTER_BUILD_FORBIDDEN_FILE_TOOLS
from agent.policies import build_allowed_tool_names
from agent.policies import is_system_error_response, timeout_compress_retry_enabled
from agent.research import UrlVisitRegistry
from agent.coding import PathVisitRegistry
from .loop_coach import LoopCoach
from agent.policies import get_step_policy
from agent.policies import RECON_PLAYBOOK_MARKDOWN
from agent.policies import (
    compact_read_code_outline_result,
)
from .episode_tracker import (
    StepRunState,
    TaskRunState,
    episode_count_from_history,
    should_inject_checkpoint_nudge,
)
from agent.research import (
    SourceRegistry,
    enrich_search_result,
    register_read_webpage_source,
    MIN_SUB_BUDGET_PER_SEARCH,
)
from agent.research import quality_from_tool_result

from .main import (
    MAX_TOOLS_PER_TURN,
    advance_json_state,
    assemble_agent_response,
    complete_ledger_state,
    format_attachment_context,
    parse_agent_response,
    save_task_deliverable,
    read_json_state,
    should_attach_json_prefill,
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
        learn_syllabus_web: bool = False,
        offline_research: bool = False,
        writing_brief: dict | None = None,
        agent=None,
        parent_task_id: str | None = None,
        micro_plan: bool = False,
        mcp_bridge=None,
    ):
        mode_norm = (mode or "").strip().lower()
        if mode_norm == "code":
            raise RuntimeError(
                "LoopEngine no longer runs code mode. "
                "Use agent.core.code_agent.run_tool_session instead "
                "(see main.run_unified_task early return)."
            )
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
            from agent.storage import get_memory
            self.memory = get_memory(self.instance_id)
        else:
            self.memory = memory
        self.workspace_summary = load_workspace_summary(self.instance_id)
        self._schema_widen_attempts = 0
        self._parse_failures = 0
        self._force_full_schema = False
        self._schema_tool_names: frozenset[str] = frozenset()
        self._last_format_mode: str = "strict_schema"
        self.human_research_notes = (human_research_notes or "").strip()
        self.persona_research_lore = bool(persona_research_lore)
        self.learn_syllabus_web = bool(learn_syllabus_web)
        self.offline_research = bool(offline_research)
        self.writing_brief = dict(writing_brief) if writing_brief else None
        self._offline_sources_available = False
        self._scratchpad_injected_this_step: bool = False
        self._agent = agent
        self._parent_task_id = parent_task_id
        self._micro_plan = bool(micro_plan)
        self._mcp_bridge = mcp_bridge
        self._act_turns = 0
        self._last_act_needs_reflect = False
        self._bound_cap_id = ""
        self._slot_fill_active = False
        self._slot_fill_path = ""
        self._dynamic_loop_active = False
        self._milestone_tracker = None
        self._task_episode_state: TaskRunState | None = None
        self._dynamic_palette_logged = False
        self._milestone_advance_nudged = False
        self._dynamic_schema_minimal = False
        self._create_file_block_counts: dict[str, int] = {}
        self._create_file_path_attempts: dict[str, int] = {}
        self._read_region_step_counts: dict[int, int] = {}
        self._update_checklist_step_counts: dict[int, int] = {}
        self._sync_project_step_counts: dict[int, int] = {}

    def _writing_brief_for_policy(self, state: dict | None = None) -> dict | None:
        if self.mode != "writing":
            return None
        if state and isinstance(state.get("writing_brief"), dict):
            return state["writing_brief"]
        return self.writing_brief

    _READ_ONLY_TOOLS = frozenset({
        "read_file",
        "read_file_region",
        "read_file_lines",
        "read_file_smart",
        "list_directory",
        "get_directory_tree",
        "grep_repo",
        "search_in_file",
        "search_files",
        "read_code_outline",
        "read_outline",
    })

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
        thinking_callback=None,
        attachment_paths: list | None = None,
    ) -> str:
        if (self.mode or "").strip().lower() == "code":
            # DEAD: code uses code_agent.py — constructor should already have blocked this.
            raise RuntimeError(
                "LoopEngine.run() refused mode=code. Use code_agent.run_tool_session."
            )
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
            thinking_callback=thinking_callback,
            attachment_paths=attachment_paths,
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
        thinking_callback=None,
        attachment_paths: list | None = None,
    ) -> str:
        from .task_context import reset_active_task_id, set_active_task_id

        task_token = set_active_task_id(task_name)
        try:
            return self._run_continuous_body(
                task_name,
                user_request,
                task_file,
                ui_callback=ui_callback,
                cancel_check=cancel_check,
                text_chunks=text_chunks,
                image_payloads=image_payloads,
                thinking_callback=thinking_callback,
                attachment_paths=attachment_paths,
            )
        finally:
            reset_active_task_id(task_token)

    def _run_continuous_body(
        self,
        task_name: str,
        user_request: str,
        task_file: str,
        ui_callback=None,
        cancel_check=None,
        text_chunks=None,
        image_payloads=None,
        thinking_callback=None,
        attachment_paths: list | None = None,
    ) -> str:
        ledger_text = f"Initializing {self.mode.title()} Engine for: {task_name}\n"
        self._user_request = user_request
        self._run_text_chunks = text_chunks
        self._attachment_paths = list(attachment_paths or [])
        self._capability_attachments_ingested = False
        self._offline_sources_available = bool(self.offline_research) and (
            bool(self.human_research_notes)
            or any(c and str(c).strip() for c in (text_chunks or []))
        )
        conversation_history: list[dict] = []
        loop_tick = 0
        step_episodes_run = 0
        last_step_idx = None
        max_loop_ticks = int(os.getenv("AQUILA_MAX_LOOP_TICKS", "50"))
        attachments_injected = False
        parse_retries = 0
        consecutive_llm_errors = 0
        skip_think_phase = False
        read_notes_this_step = False
        try:
            from .loop_settings import llm_error_limit

            llm_error_limit_val = llm_error_limit()
        except ImportError:
            llm_error_limit_val = 3
        recent_tool_signatures: list[str] = []
        recent_reasoning_hashes: list[int] = []
        _stall_turns: int = 0
        _last_milestone_snapshot: tuple = ()
        step_entry_injected = False
        grace_used_this_step = False
        tools_succeeded_this_step: set[str] = set()
        caps_succeeded_this_step: set[str] = set()
        self._last_capability_feedback = ""
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
        source_registry = (
            SourceRegistry() if self._uses_capability_act() else None
        )
        self._research_deliverable_draft: str | None = None
        self._persona_read_autosave_done = False
        loop_coach = LoopCoach(
            mode=self.mode,
            persona_research_lore=self.persona_research_lore,
            learn_syllabus_web=self.learn_syllabus_web,
            offline_research=self.offline_research,
            capability_research=self._capability_research_active(),
        )
        try:
            from .loop_settings import (
                auto_advance_milestones_enabled,
                dynamic_loop_enabled,
                task_episode_max,
                task_web_search_cap,
            )
            from .loop_objectives import MilestoneTracker

            self._dynamic_loop_active = dynamic_loop_enabled()
            if self._dynamic_loop_active:
                self._milestone_tracker = MilestoneTracker()
                self._milestone_tracker.state.offline_research = self.offline_research
                self._milestone_tracker.state.offline_sources_available = (
                    self._offline_sources_available
                )
                self._task_episode_state = TaskRunState(
                    episode_max=task_episode_max()
                )
                self._task_web_search_cap = task_web_search_cap()
                self._auto_advance_milestones = auto_advance_milestones_enabled()
            else:
                self._task_episode_state = None
                self._task_web_search_cap = 0
                if self.mode == "code":
                    self._milestone_tracker = MilestoneTracker()
                    self._auto_advance_milestones = True
                else:
                    self._milestone_tracker = None
                    self._auto_advance_milestones = False
        except ImportError:
            self._dynamic_loop_active = False
            self._milestone_tracker = None
            self._task_episode_state = None
            self._task_web_search_cap = 0
            self._auto_advance_milestones = False
        self._dynamic_palette_logged = False
        self._milestone_advance_nudged = False
        self._dynamic_schema_minimal = False
        self._run_ctx = TaskRunContext.load(
            task_name,
            self.mode,
            goal=user_request,
            instance_id=self.instance_id,
            workspace_summary=self.workspace_summary or "",
        )
        if self.mode == "code" and self._milestone_tracker is not None:
            from .loop_objectives import apply_ground_truth_to_milestone_state

            apply_ground_truth_to_milestone_state(
                self._milestone_tracker.state,
                self.mode,
                self._run_ctx.ground_truth,
            )
        self._create_file_block_counts: dict[str, int] = {}
        self._create_file_path_attempts: dict[str, int] = {}
        self._read_region_step_counts: dict[int, int] = {}
        self._update_checklist_step_counts: dict[int, int] = {}
        self._sync_project_step_counts: dict[int, int] = {}

        while loop_tick < max_loop_ticks:
            if cancel_check and cancel_check():
                return "🛑 Task was manually aborted by the user."

            try:
                has_finish = False
                state = read_json_state(task_file)
                if self.mode == "writing" and self._milestone_tracker:
                    brief = state.get("writing_brief")
                    if isinstance(brief, dict):
                        self._milestone_tracker.state.writing_brief = brief
                        self.writing_brief = brief
                if state["status"] == "completed":
                    return (
                        f"✅ {self.mode_label} completed successfully. "
                        "Check the directory for final outputs."
                    )

                current_idx = state["current_step_index"]
                if last_step_idx is not None and current_idx != last_step_idx:
                    step_episodes_run = 0
                    self._create_file_block_counts = {}
                    self._create_file_path_attempts = {}
                    self._read_region_step_counts = {}
                    self._update_checklist_step_counts = {}
                    self._sync_project_step_counts = {}
                last_step_idx = current_idx
                if getattr(self, "_run_ctx", None):
                    self._run_ctx.step_index = current_idx
                if current_idx >= len(state["steps"]):
                    return "✅ All steps are completed."

                step = state["steps"][current_idx]
                default_kind = "code"
                if self.mode in ("task", "autonomous"):
                    default_kind = "work"
                elif self.mode == "research":
                    default_kind = "search"
                elif self.mode == "writing":
                    default_kind = "write"
                step_kind = step.get("step_kind") or default_kind
                self._bound_cap_id = str(step.get("capability_id") or "").strip()
                self._slot_fill_path = str(step.get("slot_fill_path") or "").strip()
                self._slot_fill_active = self._should_slot_fill(step, step_kind)
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
                loop_coach.step_kind = step_kind
                step_policy = get_step_policy(
                    self.mode,
                    step_kind,
                    persona_research_lore=self.persona_research_lore,
                    learn_syllabus_web=self.learn_syllabus_web,
                    offline_research=self.offline_research,
                    writing_brief=self._writing_brief_for_policy(state),
                )
                is_final_step = current_idx == len(state["steps"]) - 1
                if (
                    self._dynamic_loop_active
                    and self._milestone_tracker
                    and hasattr(self.console, "event")
                ):
                    self.console.event(
                        "milestone_update",
                        step_index=current_idx,
                        **self._milestone_tracker.to_log_dict(
                            self.mode, is_final_step=is_final_step
                        ),
                    )

                episode_count = step_episodes_run
                if getattr(self, "_run_ctx", None):
                    self._run_ctx.episode = episode_count
                if (
                    self.mode == "code"
                    and episode_count == 0
                    and self._maybe_advance_satisfied_code_step(
                        step_kind, state, task_file
                    )
                ):
                    ledger_text += (
                        f"\n✅ OS: `{step_kind}` deliverable already in buffer — advancing.\n"
                    )
                    if ui_callback:
                        ui_callback(ledger_text)
                    step_episodes_run = 0
                    continue
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
                    self._scratchpad_injected_this_step = False
                    step_entry_msgs = self._build_step_entry_messages(
                        task_name,
                        step_kind,
                        conversation_history=conversation_history,
                    )
                    step_entry_injected = True

                if (
                    self._capability_research_active()
                    and self.mode == "research"
                    and episode_count == 0
                    and not self._capability_attachments_ingested
                    and self._has_attachment_sources(text_chunks)
                    and step_kind in ("read", "work", "search")
                ):
                    auto_msg = self._auto_ingest_persona_attachments(
                        task_name,
                        user_request,
                        text_chunks,
                        skip_advance=True,
                    )
                    if auto_msg:
                        self._capability_attachments_ingested = True
                        # Pre-ingest satisfies offline ingest for this step — do not re-run it.
                        caps_succeeded_this_step.add("cap.research.ingest_offline@v1")
                        if self._milestone_tracker:
                            self._milestone_tracker.record_tool(
                                "save_research_note", auto_msg, mode=self.mode
                            )
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                f"Tool Outputs:\n{auto_msg}\n\n"
                                "✅ OS: Offline ingest complete via pre-ingest. "
                                "Next capability: `cap.research.synthesize_notes@v1` "
                                "(do not call ingest_offline again)."
                            ),
                        })
                        ledger_text += f"\n{auto_msg}\n"
                        if ui_callback:
                            ui_callback(ledger_text)

                if (
                    self._capability_research_active()
                    and self.mode == "writing"
                    and episode_count == 0
                    and not self._capability_attachments_ingested
                    and self._has_attachment_sources(text_chunks)
                    and step_kind in ("read", "write", "work")
                ):
                    auto_msg = self._auto_ingest_persona_attachments(
                        task_name,
                        user_request,
                        text_chunks,
                        skip_advance=True,
                    )
                    if auto_msg:
                        self._capability_attachments_ingested = True
                        caps_succeeded_this_step.add("cap.writing.ingest_sources@v1")
                        if self._milestone_tracker:
                            self._milestone_tracker.record_capability(
                                "cap.writing.ingest_sources@v1",
                                auto_msg,
                                mode=self.mode,
                            )
                        advance_hint = (
                            "Next: `cap.writing.draft_sections@v1` using SCRATCHPAD sources."
                            if step_kind in ("write", "work")
                            else "Next: mark_objective_complete or call ingest once if needed."
                        )
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                f"Tool Outputs:\n{auto_msg}\n\n"
                                f"✅ OS: Source attachments pre-ingested into scratchpad. {advance_hint}"
                            ),
                        })
                        ledger_text += f"\n{auto_msg}\n"
                        if ui_callback:
                            ui_callback(ledger_text)

                if (
                    step_kind == "delegate"
                    and episode_count == 0
                    and self.mode in ("task", "autonomous")
                ):
                    delegate_result = self._run_delegate_step(
                        step,
                        task_name=task_name,
                        ui_callback=ui_callback,
                        cancel_check=cancel_check,
                    )
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n{delegate_result}",
                    })
                    ledger_text += f"\n{delegate_result}\n"
                    if ui_callback:
                        ui_callback(ledger_text)
                    advance_json_state(task_file, delegate_result[:500])
                    self.workspace_summary = on_step_advance(
                        conversation_history=conversation_history,
                        instance_id=self.instance_id,
                        task_name=task_name,
                        advance_summary=delegate_result[:500],
                        client=self.client,
                        memory=self.memory,
                        run_ctx=getattr(self, "_run_ctx", None),
                    )
                    recent_tool_signatures = []
                    step_entry_injected = False
                    grace_used_this_step = False
                    tools_succeeded_this_step = set()
                    caps_succeeded_this_step = set()
                    outline_logged_this_step = False
                    path_registry.set_step_index(
                        read_json_state(task_file)["current_step_index"]
                    )
                    if self.console:
                        self.console.event("delegate_mode_complete", mode=step.get("target_mode"))
                    continue

                if (
                    self.mode == "character_build"
                    and step_kind == "read"
                    and self.persona_research_lore
                    and episode_count == 0
                    and self._scratchpad_has_lore(task_name)
                ):
                    skip_msg = loop_coach.persona_read_skip_hint()
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:{skip_msg}",
                    })
                    ledger_text += f"\n{skip_msg}\n"
                    if ui_callback:
                        ui_callback(ledger_text)
                    has_attachments = any(
                        c and str(c).strip() for c in (text_chunks or [])
                    )
                    if not has_attachments:
                        advance_json_state(
                            task_file,
                            "OS auto-advance: scratchpad already has search lore.",
                        )
                        self.workspace_summary = on_step_advance(
                            conversation_history=conversation_history,
                            instance_id=self.instance_id,
                            task_name=task_name,
                            advance_summary="Skipped read ingest — lore from search step.",
                            client=self.client,
                            memory=self.memory,
                            run_ctx=getattr(self, "_run_ctx", None),
                        )
                        recent_tool_signatures = []
                        step_entry_injected = False
                        grace_used_this_step = False
                        tools_succeeded_this_step = set()
                        caps_succeeded_this_step = set()
                        outline_logged_this_step = False
                        path_registry.set_step_index(
                            read_json_state(task_file)["current_step_index"]
                        )
                        continue

                if (
                    self.mode in ("character_build", "learn_syllabus_build")
                    and step_kind in ("read", "search")
                    and episode_count == 0
                    and not self._persona_read_autosave_done
                ):
                    skip_adv = self.persona_research_lore or (
                        self.mode == "learn_syllabus_build" and self.learn_syllabus_web
                    )
                    auto_msg = self._auto_ingest_persona_attachments(
                        task_name,
                        user_request,
                        text_chunks,
                        skip_advance=skip_adv,
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
                        if not skip_adv:
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
                                run_ctx=getattr(self, "_run_ctx", None),
                            )
                            recent_tool_signatures = []
                            step_entry_injected = False
                            grace_used_this_step = False
                            tools_succeeded_this_step = set()
                            caps_succeeded_this_step = set()
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
                    episode_count=episode_count,
                )

                if (
                    self.mode == "code"
                    and episode_count == 0
                    and step_kind in ("work", "code", "tdd_red", "tdd_green", "verify")
                ):
                    try:
                        from agent.core.code_scaffolds import (
                            dispatch_scaffold_files,
                            scaffold_dispatch_should_run,
                        )

                        goal = getattr(self, "_user_request", "") or ""
                        if scaffold_dispatch_should_run(goal):
                            written = dispatch_scaffold_files(goal)
                            if written:
                                user_msg += (
                                    "\n\n✅ OS: Scaffold files written to buffer: "
                                    + ", ".join(f"`{p}`" for p in written)
                                    + ". Run `cap.dev.run_tests@v1`, then sync."
                                )
                                if self._milestone_tracker:
                                    self._milestone_tracker.state.file_edited = True
                                    self._milestone_tracker.state.tests_drafted = True
                                    self._milestone_tracker.state.deliverable_draft = True
                                fast_msg = self._try_habit_tracker_scaffold_fast_path(
                                    task_file=task_file,
                                    task_name=task_name,
                                    state=state,
                                    source_registry=source_registry,
                                    cancel_check=cancel_check,
                                    attachment_text_chunks=text_chunks,
                                )
                                if fast_msg is not None:
                                    ledger_text += fast_msg
                                    if ui_callback:
                                        ui_callback(ledger_text)
                                    return ledger_text
                    except Exception:
                        pass

                if self.mode == "research" and step.get("capability_id"):
                    try:
                        from agent.functions.research import recommended_capability_for_step

                        rec_cap, _rec_args = recommended_capability_for_step(
                            step,
                            user_request,
                            offline=self.offline_research,
                            has_attachments=self._has_attachment_sources(text_chunks),
                            caps_succeeded=caps_succeeded_this_step,
                        )
                        if episode_count == 0:
                            user_msg += (
                                f"\n\n**OS hint:** Start this step with capability "
                                f"`{rec_cap}` (from plan step or recipe)."
                            )
                    except ImportError:
                        pass

                if (
                    self.mode == "research"
                    and episode_count == 0
                    and not tools_succeeded_this_step
                    and step.get("capability_id")
                ):
                    try:
                        from agent.core.loop_settings import research_recipe_strict_enabled
                        from agent.functions.research import recommended_capability_for_step

                        if research_recipe_strict_enabled():
                            cap_id, cap_args = recommended_capability_for_step(
                                step,
                                user_request,
                                offline=self.offline_research,
                                has_attachments=self._has_attachment_sources(text_chunks),
                                caps_succeeded=caps_succeeded_this_step,
                            )
                            cap_batch = self._execute_capability_batch(
                                [{"id": cap_id, "arguments": cap_args}],
                                task_name=task_name,
                                step_kind=step_kind,
                                step_index=current_idx,
                                source_registry=source_registry,
                                cancel_check=cancel_check,
                                attachment_paths=self._attachment_paths,
                                attachment_text_chunks=text_chunks,
                                pending_final_report=pending_final_report,
                                caps_succeeded=caps_succeeded_this_step,
                            )
                            last_tool_output = cap_batch.get("last_output", "")
                            if cap_batch.get("finish_ok"):
                                has_finish = True
                                finish_msg = last_tool_output
                            if cap_batch.get("executed", 0) > 0:
                                tools_succeeded_this_step.add("capability")
                                conversation_history.append({
                                    "role": "user",
                                    "content": f"Tool Outputs:\n{last_tool_output}",
                                })
                                ledger_text += f"\n{last_tool_output}\n"
                                if ui_callback:
                                    ui_callback(ledger_text)
                            episode_count += 1
                            continue
                    except ImportError:
                        pass

                task_at_limit = (
                    self._dynamic_loop_active
                    and self._task_episode_state is not None
                    and self._task_episode_state.at_episode_limit()
                )
                if task_at_limit:
                    user_msg += self._capability_budget_override_msg(is_final_step=is_final_step)
                elif step_run.at_episode_limit():
                    if step_run.can_apply_grace() and not self._dynamic_loop_active:
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
                    elif is_final_step:
                        user_msg += self._capability_step_budget_final_override()
                    else:
                        user_msg += (
                            "\n\n⚠️ OS: Step episode budget reached (soft). "
                            "Continue if needed — tools are not phase-locked."
                            if self._dynamic_loop_active
                            else (
                                " Use capabilities then advance."
                                if self._uses_capability_act()
                                else " Use `save_research_note` then `mark_objective_complete`."
                            )
                        )
                else:
                    act_keys = (
                        "`reasoning`, then `capabilities` (one capability ID per turn)."
                        if self._capability_research_active()
                        else "`reasoning`, then `tools`."
                    )
                    user_msg += (
                        "\n\nWork autonomously toward the objective. Each response: brief "
                        f"{act_keys} Continue after results until done, "
                        f"then `mark_objective_complete`.\n({step_run.format_progress()})"
                    )
                if self._dynamic_loop_active and self._milestone_tracker:
                    user_msg += (
                        "\n\n"
                        + self._milestone_tracker.state.progress_line(
                            self.mode, is_final_step=is_final_step
                        )
                        + " Tools are not phase-locked in dynamic loop mode."
                    )
                    if (
                        is_final_step
                        and self._milestone_tracker.should_allow_finish(
                            self.mode, is_final_step=True
                        )
                        and hasattr(self.console, "event")
                    ):
                        self.console.event("early_finish_eligible", step_index=current_idx)
                    if should_inject_checkpoint_nudge(step_run):
                        user_msg += (
                            "\n\n⚠️ OS: Episode budget almost exhausted — complete the step "
                            "or call mark_objective_complete with a summary."
                        )

                if self.mode == "research":
                    user_msg += (
                        f"\n\n**Task ID:** `{task_name}` — scratchpad notes are bound to this "
                        "task automatically. Do not pass `task_name` on save/read note tools."
                    )
                    if is_final_step or step_kind == "finalize":
                        user_msg += self._research_finalize_os_hint(
                            scratchpad_injected=self._scratchpad_injected_this_step,
                            capability_mode=self._capability_research_active(),
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
                # Keep last capability outcome visible when RunState is disabled.
                feedback = (getattr(self, "_last_capability_feedback", "") or "").strip()
                if feedback and not run_state_enabled():
                    banner = (
                        "**LAST CAPABILITY RESULT (do not ignore — continue from this, "
                        "do not restart as if the project were empty):**\n"
                        f"{feedback[:2500]}\n\n"
                    )
                    user_msg = banner + user_msg
                    message_dict = self._format_user_message(user_msg, image_payloads)
                if (
                    self.mode == "code"
                    and step_kind == "explore"
                    and explore_tool_turns >= 8
                    and not self._recon_tools_used(conversation_history)
                ):
                    user_msg += (
                        "\n\n⚠️ OS: Stuck in explore — call `cap.dev.recon@v1` "
                        "(tree + outline) before more reads."
                    )
                    message_dict = self._format_user_message(user_msg, image_payloads)
                if profile.max_scrape_chars_per_turn > 0:
                    scrape_budget_remaining[0] = profile.max_scrape_chars_per_turn
                if self._micro_plan and len(conversation_history) > 4:
                    conversation_history[:] = conversation_history[-4:]
                self._maybe_compress_conversation(
                    conversation_history,
                    profile,
                    task_name,
                    proactive_note=True,
                )

                active_memory = self._assemble_loop_messages(
                    system_prompt=self.system_prompt,
                    step_entry=step_entry_msgs,
                    conversation_history=conversation_history,
                    user_message=message_dict,
                    profile=profile,
                    include_full_goal=episode_count == 0,
                )

                if self._force_full_schema and not self._dynamic_loop_active:
                    schema = self.action_schema
                    self._schema_tool_names = frozenset(self.base_tools.keys())
                elif self._capability_research_active():
                    schema = self._schema_for_capability_step(
                        step_kind,
                        is_final_step=is_final_step,
                        step=step,
                    )
                else:
                    schema = self._schema_for_step(
                        current_objective,
                        step_kind,
                        is_final_step=is_final_step,
                    )

                run_think_phase = self._should_run_think_phase(
                    parse_retries,
                    skip_think_phase=skip_think_phase,
                    step_kind=step_kind,
                )
                if run_think_phase:
                    tool_preview = self._format_tool_preview_for_think(step_kind=step_kind)
                    think_anchor = ""
                    if run_state_enabled() and getattr(self, "_run_ctx", None):
                        think_anchor = (
                            "\n\n**PROGRESS ANCHOR (authoritative):**\n"
                            + self._run_ctx.render_think_anchor()
                        )
                    think_user_msg = (
                        user_msg
                        + think_anchor
                        + tool_preview
                        + "\n\n**THINK TURN:** Continue from **RUN STATE** / last capability "
                        "and Tool Outputs above. Plan the *next* action only — do not restate "
                        "the whole goal as if nothing ran."
                        + (
                            " If RUN STATE shows a failed last capability, do not claim an "
                            "earlier step succeeded."
                            if run_state_enabled()
                            else ""
                        )
                        + " You cannot execute tools in this message — no JSON. Name which tool "
                        "from the list above you will call on the **next** act turn."
                    )
                    think_message_dict = self._format_user_message(
                        think_user_msg, image_payloads
                    )
                    think_memory = self._assemble_loop_messages(
                        system_prompt=self.system_prompt,
                        step_entry=step_entry_msgs,
                        conversation_history=conversation_history,
                        user_message=think_message_dict,
                        profile=profile,
                        include_full_goal=episode_count == 0,
                    )
                    if ui_callback:
                        ui_callback(
                            f"{ledger_text}\n\n⏳ {step_run.format_progress()} · thinking..."
                        )
                    think_outcome, think_ledger = self._run_think_phase(
                        think_memory,
                        step_run=step_run,
                        loop_tick=loop_tick,
                        thinking_callback=thinking_callback,
                        profile=profile,
                        task_name=task_name,
                        conversation_history=conversation_history,
                        timeout_compress_used=timeout_compress_used,
                        ledger_text=ledger_text,
                        ui_callback=ui_callback,
                    )
                    if think_outcome == "compress_retry":
                        timeout_compress_used = True
                        continue
                    if think_outcome == "error":
                        consecutive_llm_errors += 1
                        skip_think_phase = True
                        ledger_text += (
                            "\n\n❌ OS (LLM): Think pass unreachable — continuing to act.\n"
                        )
                        if ui_callback:
                            ui_callback(ledger_text)
                        if consecutive_llm_errors >= llm_error_limit_val:
                            return self._llm_circuit_breaker_message()
                    elif think_outcome == "ok":
                        consecutive_llm_errors = 0
                        ledger_text += think_ledger
                        if ui_callback:
                            ui_callback(ledger_text)
                        user_msg += (
                            "\n\n**ACT TURN:** Output ONLY valid JSON (no prose outside "
                            "the JSON object) with brief `reasoning` and a "
                            + (
                                "`capabilities` array (keys `id` and `arguments`)."
                                if self._capability_research_active()
                                else "`tools` array."
                            )
                        )
                        message_dict = self._format_user_message(user_msg, image_payloads)
                        active_memory = self._assemble_loop_messages(
                            system_prompt=self.system_prompt,
                            step_entry=step_entry_msgs,
                            conversation_history=conversation_history,
                            user_message=message_dict,
                            profile=profile,
                            include_full_goal=episode_count == 0,
                        )

                # Never pair assistant JSON prefill with a JSON Schema format dict —
                # stock Ollama returns HTTP 400 (Failed to initialize samplers).
                # Prefill is only for non-schema formats (json_object / plain).
                prefill_text = ""
                prefill_flag = os.getenv("AQUILA_ACT_JSON_PREFILL", "1").strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "off",
                )
                if (
                    prefill_flag
                    and run_think_phase
                    and should_attach_json_prefill(schema)
                ):
                    bt = chr(96) * 3
                    prefill_text = f"{bt}json\n" + '{\n  "reasoning": "'
                    active_memory.append({
                        "role": "assistant",
                        "content": prefill_text,
                    })

                if ui_callback:
                    ui_callback(
                        f"{ledger_text}\n\n⏳ {step_run.format_progress()} · working..."
                    )
                temperature = 0.2
                est_tokens = estimate_messages_tokens(active_memory)
                structured_act = isinstance(schema, dict)
                use_stream = (
                    ui_callback is not None
                    and not structured_act
                    and os.getenv("AQUILA_ACT_STREAM", "1").strip().lower()
                    not in ("0", "false", "no", "off")
                )
                self._act_turns += 1
                if self.console:
                    self.console.event("act_turn", iteration=loop_tick + 1, step_kind=step_kind)

                import time as _time

                from agent.parser import throughput_from_llm_turn

                _turn_start = _time.time()
                result_dict = self.client.chat(
                    active_memory,
                    temperature=temperature,
                    format=schema,
                    stream=use_stream,
                    estimated_prompt_tokens=est_tokens,
                    surface="act",
                    force_think_disabled=structured_act,
                )
                _turn_duration_ms = int((_time.time() - _turn_start) * 1000)
                raw_response = ""
                last_thinking_trace = ""
                if isinstance(schema, dict):
                    self._last_format_mode = "strict_schema"
                elif schema == "json_object":
                    self._last_format_mode = "json_object"
                else:
                    self._last_format_mode = "plain"
                if isinstance(result_dict, dict):
                    raw_response = result_dict.get("message", {}).get("content", "") or ""
                    last_thinking_trace = str(
                        result_dict.get("message", {}).get("thinking", "") or ""
                    )
                    self._last_format_mode = str(
                        result_dict.get("format_mode_used", "strict_schema")
                    )
                else:
                    raw_response, last_thinking_trace = self._consume_act_stream(
                        result_dict
                    )

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
                        from agent.policies import compress_step_transcript

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
                    consecutive_llm_errors += 1
                    if consecutive_llm_errors >= llm_error_limit_val:
                        return self._llm_circuit_breaker_message()
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

                consecutive_llm_errors = 0
                response_text = (
                    assemble_agent_response(prefill_text, raw_response)
                    if prefill_text
                    else raw_response
                )

                ep_display = step_run.episode_count + 1
                _tp_extra = throughput_from_llm_turn(
                    raw_response,
                    _turn_duration_ms,
                    thinking=last_thinking_trace,
                    ollama_base_url=getattr(self.client, "base_url", "") or "",
                )
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
                        duration_ms=_turn_duration_ms,
                        thinking_preview=last_thinking_trace,
                        ollama_base_url=_tp_extra.get("ollama_base_url"),
                        ollama_engine=_tp_extra.get("ollama_engine"),
                        throughput_extra=_tp_extra,
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
                ledger_text += f"\n\n{header}\n"
                if last_thinking_trace.strip():
                    preview = last_thinking_trace.strip()
                    if len(preview) > 1200:
                        preview = preview[:1200] + "…"
                    ledger_text += (
                        f"<details class='thinking-block'><summary>Thinking</summary>\n"
                        f"{preview}\n</details>\n\n"
                    )
                ledger_text += f"{response_text}\n"
                if ui_callback:
                    ui_callback(ledger_text)

                conversation_history.append({
                    "role": "assistant",
                    "content": response_text,
                    "_counts_as_episode": False,
                })

                _schema_kind = (
                    "capability_slot_fill"
                    if self._slot_fill_active and self._bound_cap_id
                    else (
                        "capability_action"
                        if self._capability_research_active()
                        else "agent_action"
                    )
                )
                _parse_tool_names = (
                    frozenset({self._bound_cap_id})
                    if self._slot_fill_active and self._bound_cap_id
                    else (self._schema_tool_names or None)
                )
                parsed_response = parse_agent_response(
                    response_text,
                    quiet=False,
                    tool_names=_parse_tool_names,
                    format_mode=self._last_format_mode,
                    registry=self.base_tools,
                    schema_kind=_schema_kind,
                )
                if not parsed_response:
                    self._parse_failures += 1
                    if self._parse_failures >= 2:
                        if self._dynamic_loop_active:
                            self._dynamic_schema_minimal = True
                            self._parse_failures = 0
                            self.console.print(
                                "[yellow]⚠️ OS: Dynamic schema parse failed twice; "
                                "shrinking to minimal mode tool schema.[/yellow]"
                            )
                        else:
                            self._force_full_schema = True
                            self.console.print(
                                "[yellow]⚠️ OS: Routed tool schema failed twice; "
                                "falling back to full tool set for this step.[/yellow]"
                            )
                else:
                    self._parse_failures = 0

                parse_ok = bool(parsed_response) and (
                    isinstance(parsed_response.get("capabilities"), list)
                    if self._capability_research_active()
                    else isinstance(parsed_response.get("tools"), list)
                )
                if not parse_ok:
                    parse_retries += 1
                    self._pop_last_assistant(conversation_history)
                    if parse_retries == 1 and isinstance(schema, dict):
                        retry_result = self.client.chat(
                            active_memory,
                            temperature=temperature,
                            format=schema,
                            stream=False,
                            estimated_prompt_tokens=est_tokens,
                            surface="act",
                            force_think_disabled=True,
                        )
                        if isinstance(retry_result, dict):
                            retry_raw = (
                                retry_result.get("message", {}).get("content", "") or ""
                            )
                            retry_text = (
                                assemble_agent_response(prefill_text, retry_raw)
                                if prefill_text
                                else retry_raw
                            )
                            retry_parsed = parse_agent_response(
                                retry_text,
                                quiet=False,
                                tool_names=self._schema_tool_names or None,
                                format_mode=str(
                                    retry_result.get("format_mode_used", "strict_schema")
                                ),
                                registry=self.base_tools,
                                schema_kind=_schema_kind,
                            )
                            _retry_key = (
                                "capabilities"
                                if self._capability_research_active()
                                else "tools"
                            )
                            if retry_parsed and isinstance(
                                retry_parsed.get(_retry_key), list
                            ):
                                response_text = retry_text
                                parsed_response = retry_parsed
                                parse_ok = True
                                parse_retries = 0
                    if not parse_ok:
                        parse_retries += 1
                        # In dynamic loop mode, also handle persistent parse failures
                        if parse_retries >= 3 and self._dynamic_loop_active:
                            # Force schema to full tool set and reset counter
                            self._force_full_schema = True
                            self._dynamic_schema_minimal = False
                            parse_retries = 0
                            conversation_history.append({
                                "role": "user",
                                "content": (
                                    "Tool Outputs:\n⚠️ OS: Persistent parse failures. "
                                    "Schema widened to full tool set. Output valid JSON."
                                ),
                            })
                            continue
                        self._pop_last_assistant(conversation_history)
                        from agent.policies import schema_hint_tool_names

                        hint_names = (
                            sorted(self._schema_tool_names)
                            if self._capability_research_active()
                            else schema_hint_tool_names(
                                set(self._schema_tool_names),
                                mode=self.mode,
                            )
                        )
                        if self._capability_research_active():
                            retry_msg = (
                                "Tool Outputs:\n❌ OS PARSE ERROR: Your last response was not valid JSON. "
                                "Rules: (1) Output ONLY a raw JSON object. "
                                "(2) Keys 'reasoning' (string) and 'capabilities' (array). "
                                "(3) Each capability: {'id': '...', 'arguments': {...}}. "
                                f"Available capabilities: {hint_names}"
                            )
                        else:
                            retry_msg = (
                                "Tool Outputs:\n❌ OS PARSE ERROR: Your last response was not valid JSON. "
                                "Rules: (1) Output ONLY a raw JSON object — no markdown fences, no prose. "
                                "(2) Must contain keys 'reasoning' (string) and 'tools' (array). "
                                "(3) Each tool: {'name': '...', 'arguments': {...}}. "
                                f"Available tool names: {hint_names}"
                            )
                        conversation_history.append({"role": "user", "content": retry_msg})
                        ledger_text += f"\n{retry_msg}\n"
                        if ui_callback:
                            ui_callback(ledger_text)
                        if parse_retries >= 2:
                            if not self._dynamic_loop_active and self._handle_forced_advance(
                                task_file, task_name, current_idx, state, conversation_history
                            ):
                                parse_retries = 0
                                recent_tool_signatures = []
                                step_entry_injected = False
                                grace_used_this_step = False
                                tools_succeeded_this_step = set()
                                caps_succeeded_this_step = set()
                                outline_logged_this_step = False
                        continue

                parse_retries = 0
                self._last_act_needs_reflect = False

                pending_final_report = parsed_response.get("final_report") or ""
                if pending_final_report and self._milestone_tracker:
                    self._milestone_tracker.note_final_report()

                from .main import normalize_tool_calls_list

                capability_calls: list[dict] = []
                if self._capability_research_active():
                    capability_calls = self._normalize_capability_calls(
                        parsed_response.get("capabilities", [])
                    )

                tool_calls = normalize_tool_calls_list(parsed_response.get("tools", []))
                last_reasoning_text = str(parsed_response.get("reasoning", "") or "")

                if not self._capability_research_active():
                    tool_calls, pending_final_report = self._normalize_tool_calls(
                        tool_calls, pending_final_report
                    )
                    tool_calls = self._strip_scratchpad_task_name_from_tool_calls(tool_calls)

                has_finish_in_batch = any(
                    isinstance(tc, dict) and tc.get("name") == "finish_task" 
                    for tc in tool_calls
                )
                if pending_final_report and not has_finish_in_batch:
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

                try:
                    from agent.parser import log_structured_parse_event

                    log_structured_parse_event(
                        self.console,
                        ok=bool(parse_ok),
                        meta={
                            "format_mode": self._last_format_mode,
                            "error_kind": "ok" if parse_ok else "empty",
                            "healed": False,
                        },
                        tool_count=(
                            len(capability_calls)
                            if self._capability_research_active()
                            else len(tool_calls)
                        )
                        if parse_ok
                        else 0,
                    )
                except Exception:
                    pass

                _empty_turn = (
                    not capability_calls
                    if self._capability_research_active()
                    else not tool_calls
                )
                if _empty_turn:
                    parse_retries += 1
                    self._last_act_needs_reflect = True
                    fallback_applied = False
                    if self._capability_research_active() and parse_retries >= 2:
                        from agent.functions.research import recommended_capability_for_step

                        has_attachments = self._has_attachment_sources(text_chunks)
                        cap_id, cap_args = recommended_capability_for_step(
                            step,
                            user_request,
                            offline=self.offline_research,
                            has_attachments=has_attachments,
                            caps_succeeded=caps_succeeded_this_step,
                        )
                        if not cap_id and step.get("capability_id"):
                            cap_id = step["capability_id"]
                            cap_args = {"topic": user_request}
                        if cap_id:
                            capability_calls = [{
                                "id": cap_id,
                                "arguments": cap_args,
                            }]
                            parse_retries = 0
                            fallback_applied = True
                            ledger_text += (
                                f"\n⚙️ OS: Empty capability turn — auto-running `{cap_id}`.\n"
                            )
                            if ui_callback:
                                ui_callback(ledger_text)
                    if not fallback_applied:
                        self._pop_last_assistant(conversation_history)
                        retry_msg = (
                            "Tool Outputs:\n❌ OS SCHEMA VIOLATION: "
                            + (
                                "No capabilities found in 'capabilities' array. "
                                "Use keys 'id' and 'arguments'."
                                if self._capability_research_active()
                                else "No tool calls found in 'tools' array. "
                                "Constrained decoding requires each tool to use keys "
                                "'name' and 'arguments' only."
                            )
                        )
                        conversation_history.append({"role": "user", "content": retry_msg})
                        if (
                            parse_retries >= 2
                            and not self._dynamic_loop_active
                            and self._handle_forced_advance(
                                task_file, task_name, current_idx, state, conversation_history
                            )
                        ):
                            parse_retries = 0
                            recent_tool_signatures = []
                            step_entry_injected = False
                            grace_used_this_step = False
                            tools_succeeded_this_step = set()
                            caps_succeeded_this_step = set()
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
                web_search_in_turn = sum(
                    1 for tc in tool_calls if tc.get("name") == "web_search"
                )
                web_search_done_this_turn = 0
                parallel_read_results: dict[str, str] = {}
                if (
                    not self._capability_research_active()
                    and step_kind in ("explore", "read", "verify", "micro")
                ):
                    parallel_read_results = self._execute_reads_parallel(tool_calls)

                if self._capability_research_active() and capability_calls:
                    if capability_repeat_guard_enabled():
                        rep_block = self._capability_repeat_pre_execute_block(
                            capability_calls,
                            recent_tool_signatures,
                            loop_coach=loop_coach,
                            is_final_step=is_final_step,
                        )
                        if rep_block:
                            conversation_history.append({
                                "role": "user",
                                "content": f"Tool Outputs:\n{rep_block}",
                            })
                            recent_reasoning_hashes.clear()
                            recent_tool_signatures.clear()
                            if hasattr(self.console, "event"):
                                tool_names = sorted(
                                    str(c.get("id") or "")
                                    for c in capability_calls
                                    if isinstance(c, dict)
                                )
                                self.console.event(
                                    "repetition_loop_detected",
                                    step_index=current_idx,
                                    capability_ids=tool_names,
                                    hint_preview=str(rep_block)[:400],
                                    blocked_before_execute=True,
                                )
                            self._last_act_needs_reflect = True
                            continue
                        path_rep = self._create_file_path_repeat_pre_execute_block(
                            capability_calls,
                            loop_coach=loop_coach,
                        )
                        if path_rep:
                            conversation_history.append({
                                "role": "user",
                                "content": f"Tool Outputs:\n{path_rep}",
                            })
                            recent_reasoning_hashes.clear()
                            if hasattr(self.console, "event"):
                                self.console.event(
                                    "create_file_path_repeat_blocked",
                                    step_index=current_idx,
                                    hint_preview=str(path_rep)[:400],
                                    blocked_before_execute=True,
                                )
                            self._last_act_needs_reflect = True
                            continue
                    # Detect identical capability+reasoning loops BEFORE execute so
                    # the 3rd repeat never re-runs setup/recon (soft coach was too late).
                    if self._dynamic_loop_active:
                        tool_names = sorted(
                            str(c.get("id") or "")
                            for c in capability_calls
                            if isinstance(c, dict)
                        )
                        reasoning = (
                            parsed_response.get("reasoning", "")
                            if isinstance(parsed_response, dict)
                            else ""
                        )
                        combo_hash = hash(reasoning + "".join(tool_names))
                        recent_reasoning_hashes.append(combo_hash)
                        if (
                            len(recent_reasoning_hashes) >= 3
                            and len(set(recent_reasoning_hashes[-3:])) == 1
                        ):
                            pending_ms = [
                                lbl
                                for lbl, ok in self._milestone_tracker.state._checks(
                                    self.mode, is_final_step=is_final_step
                                )
                                if not ok
                            ] if self._milestone_tracker else []
                            rep_call = capability_calls[0] if capability_calls else {}
                            rep_hint = loop_coach.repetition_break_hint(
                                pending_ms,
                                self._schema_tool_names or frozenset(),
                                repeat_cap_id=str(rep_call.get("id") or "") if isinstance(rep_call, dict) else "",
                                repeat_file_path=str(
                                    (rep_call.get("arguments") or {}).get("file_path") or ""
                                )
                                if isinstance(rep_call, dict)
                                else "",
                            )
                            conversation_history.append({
                                "role": "user",
                                "content": f"Tool Outputs:\n{rep_hint}",
                            })
                            recent_reasoning_hashes.clear()
                            recent_tool_signatures.clear()
                            if hasattr(self.console, "event"):
                                self.console.event(
                                    "repetition_loop_detected",
                                    step_index=current_idx,
                                    capability_ids=tool_names,
                                    reasoning_preview=str(reasoning)[:300],
                                    hint_preview=str(rep_hint)[:400],
                                    blocked_before_execute=True,
                                )
                            continue
                    cap_batch = self._execute_capability_batch(
                        capability_calls,
                        task_name=task_name,
                        step_kind=step_kind,
                        step_index=current_idx,
                        source_registry=source_registry,
                        cancel_check=cancel_check,
                        attachment_paths=self._attachment_paths,
                        attachment_text_chunks=text_chunks,
                        pending_final_report=pending_final_report,
                        caps_succeeded=caps_succeeded_this_step,
                    )
                    if capability_repeat_guard_enabled() and capability_calls:
                        self._track_capability_signatures(
                            capability_calls, recent_tool_signatures
                        )
                    last_tool_output = cap_batch.get("last_output", "")
                    if cap_batch.get("last_cap_ok"):
                        self._last_act_needs_reflect = False
                    else:
                        self._last_act_needs_reflect = True
                    if cap_batch.get("finish_ok"):
                        has_finish = True
                        finish_msg = last_tool_output
                    ran_non_meta_tool = cap_batch.get("executed", 0) > 0
                    tools_succeeded_this_step.add("capability")
                    if (
                        not has_advance
                        and not has_finish
                        and self._uses_capability_act()
                        and cap_batch.get("last_cap_ok")
                        and cap_batch.get("last_cap_id")
                    ):
                        cap_policy = get_step_policy(
                            self.mode,
                            step_kind,
                            persona_research_lore=self.persona_research_lore,
                            learn_syllabus_web=self.learn_syllabus_web,
                            offline_research=self.offline_research,
                            writing_brief=self._writing_brief_for_policy(state),
                        )
                        last_cap = str(cap_batch["last_cap_id"])
                        advance_fn = getattr(
                            cap_policy, "should_auto_advance_after_capability", None
                        )
                        if callable(advance_fn) and advance_fn(
                            last_cap,
                            True,
                            step_kind=step_kind,
                            result_summary=str(cap_batch.get("last_output") or ""),
                            result_data=cap_batch.get("last_cap_data") or {},
                            milestone_tracker=self._milestone_tracker,
                        ):
                            gate = (
                                self._habit_tracker_advance_block(step_kind=step_kind)
                                if step_kind in ("work", "code", "finalize")
                                else None
                            )
                            if gate:
                                has_advance = False
                                last_tool_output += f"\n\n{gate}"
                            else:
                                has_advance = True
                                summary_fn = getattr(
                                    cap_policy, "advance_summary_for_capability", None
                                )
                                advance_summary = (
                                    summary_fn(last_cap)
                                    if callable(summary_fn)
                                    else f"Completed {last_cap}."
                                )
                                last_tool_output += (
                                    f"\n\n✅ OS: {advance_summary} Advancing to next plan step."
                                )

                    if (
                        not has_advance
                        and not has_finish
                        and self.mode == "code"
                        and step_kind in ("work", "code")
                        and getattr(self, "_run_ctx", None)
                    ):
                        from agent.core.implementation_plan import code_work_checklist_complete

                        if code_work_checklist_complete(self._run_ctx.checklist):
                            gate = self._habit_tracker_advance_block(step_kind=step_kind)
                            if gate:
                                last_tool_output += f"\n\n{gate}"
                            else:
                                has_advance = True
                                advance_summary = "Checklist complete for work step."
                                last_tool_output += (
                                    f"\n\n✅ OS: {advance_summary} Advancing to next plan step."
                                )

                # Legacy tool-act path; skipped when `_uses_capability_act()`
                # (research/character/learn/writing/code). Code-mode tool OS BLOCK
                # arms below are unreachable for mode=code after CAPABILITY_ACT_MODES.
                for i, tc in enumerate(tool_calls):
                    if self._uses_capability_act():
                        break
                    tool_name = tc.get("name", "")
                    
                    schema_ok, schema_err = validate_tool_calls(
                        [tc],
                        valid_names=(
                            set(self._schema_tool_names)
                            if self._schema_tool_names
                            else None
                        ),
                    )
                    if not schema_ok:
                        # Meta tools must stay usable even if schema tool list is stale/truncated.
                        if tool_name not in ("mark_objective_complete", "finish_task"):
                            err_msg = schema_err.replace('tools[0]', f'tools[{i}]')
                            if "missing required key 'name'" in err_msg:
                                err_msg += " (Did you hit the max token limit? Keep your reasoning and data concise to prevent truncation!)"
                            result = f"❌ OS SCHEMA VIOLATION: {err_msg}"
                            last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                            self.console.log_tool_execution(tool_name, tc.get("arguments", {}), result)
                            continue
                        
                    args_ok, args_err = validate_tool_arguments(
                        [tc], registry=self.base_tools
                    )
                    if not args_ok:
                        if tool_name not in ("mark_objective_complete", "finish_task"):
                            result = f"❌ OS ARGUMENT VIOLATION: {args_err.replace('tools[0]', f'tools[{i}]')}"
                            last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                            self.console.log_tool_execution(tool_name, tc.get("arguments", {}), result)
                            continue
                    
                    # Defensive: skip remaining tools if task already finishing/advancing
                    if has_finish or has_advance:
                        break
                        
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
                                
                            if not gate and self._dynamic_loop_active and self._milestone_tracker:
                                max_step_iterations = state["steps"][current_idx].get("max_iterations", 8)
                                episodes = step_episodes_run
                                if episodes < max_step_iterations:
                                    if not self._milestone_tracker.should_suggest_advance(self.mode, is_final_step=False):
                                        gate = (
                                            f"❌ OS BLOCK: Milestones are not complete yet. "
                                            f"{self._milestone_tracker.state.progress_line(self.mode, is_final_step=False)} "
                                            f"Complete them before advancing, or exhaust your step iteration budget ({episodes}/{max_step_iterations})."
                                        )

                            if gate:
                                suffix = (
                                    " Call `cap.dev.sync_project@v1` then "
                                    "`cap.dev.run_tests@v1`."
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
                                last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                                self.console.log_tool_execution(
                                    tool_name, tc.get("arguments", {}), result
                                )
                                break
                    elif tool_name == "delegate_mode":
                        if self.mode not in ("task", "autonomous"):
                            result = (
                                "❌ OS BLOCK: delegate_mode is only available in "
                                "Autonomous Task mode."
                            )
                        else:
                            result = self._run_delegate_from_tool(
                                args,
                                task_name=task_name,
                                cancel_check=cancel_check,
                            )
                            has_advance = True
                            advance_summary = result[:500]
                    elif tool_name == "finish_task":
                        allow_early_finish = (
                            self._dynamic_loop_active
                            and self._milestone_tracker
                            and self._milestone_tracker.should_allow_finish(
                                self.mode,
                                is_final_step=is_final_step,
                                pending_final_report=bool(pending_final_report),
                            )
                        )
                        if (
                            self.mode == "research"
                            and current_idx < len(state["steps"]) - 1
                            and not allow_early_finish
                        ):
                            result = (
                                "❌ OS BLOCK: finish_task is only allowed on the final plan step. "
                                "Use save_research_note for findings, then mark_objective_complete "
                                "to advance."
                            )
                            if self.console:
                                self.console.event(
                                    "premature_finish_blocked",
                                    step_index=current_idx,
                                )
                        else:
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
                            if (
                                self.mode == "research"
                                and is_final_step
                                and not str(pending_final_report or "").strip()
                                and not (
                                    self._milestone_tracker
                                    and self._milestone_tracker._saw_final_report
                                )
                            ):
                                has_finish = False
                                result = (
                                    "❌ OS BLOCK: On the final step include top-level "
                                    "`final_report` in the same JSON object as `finish_task` "
                                    "(not only in message_to_user). Use SCRATCHPAD and prior "
                                    "tool outputs for evidence."
                                )
                            else:
                                result = "✅ Finish task triggered."
                                last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                                self.console.log_tool_execution(
                                    tool_name, tc.get("arguments", {}), result
                                )
                                break
                    else:
                        ran_non_meta_tool = True
                        args = tc.get("arguments") or {}
                        read_sig = (
                            f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                            if tool_name in self._READ_ONLY_TOOLS
                            else ""
                        )
                        cached_read = parallel_read_results.get(read_sig) if read_sig else None
                        if cached_read is not None:
                            result = cached_read
                        path_block = path_registry.check_before_execute(tool_name, args)
                        if cached_read is not None:
                            pass
                        elif path_block and path_block.startswith("❌"):
                            result = path_block
                        elif (
                            self.mode == "research"
                            and self.offline_research
                            and tool_name in ("web_search", "read_webpage")
                        ):
                            result = (
                                f"❌ OS BLOCK: Offline research mode — {tool_name} is disabled. "
                                "Use only user attachments, human journal, and "
                                "save_research_note."
                            )
                        elif (
                            self.mode == "research"
                            and tool_name == "web_search"
                            and not self._dynamic_loop_active
                            and step_kind == "search"
                            and web_search_done_this_turn >= 1
                        ):
                            result = (
                                "❌ OS BLOCK: One web_search per turn on research search steps. "
                                "Split topics (email, caldav, scheduler) across iterations."
                            )
                        elif (
                            self.mode == "research"
                            and tool_name == "web_search"
                            and self._dynamic_loop_active
                            and self._milestone_tracker
                            and self._milestone_tracker.state.web_search_count
                            >= self._task_web_search_cap
                        ):
                            result = (
                                f"❌ OS BLOCK: web_search cap ({self._task_web_search_cap}) "
                                "for this task. Synthesize from saved notes."
                            )
                        elif tool_name in (
                            "search_files",
                            "get_directory_tree",
                            "list_directory",
                        ):
                            from agent.policies import normalize_code_tool_path

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
                                result = loop_coach.enhance_url_block(
                                    block_msg, page_url, url_registry
                                )
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
                        elif tool_name == "save_research_note" and self.mode in (
                            "character_build",
                            "research",
                            "learn_syllabus_build",
                        ):
                            gathered = str(args.get("gathered_data", ""))
                            try:
                                existing_notes = (
                                    self.memory.get_scratchpad_notes(task_name) or ""
                                )
                            except Exception:
                                existing_notes = ""
                            merged = loop_coach.try_merge_scratchpad(
                                gathered, existing_notes
                            )
                            if merged:
                                gathered = merged
                                args = {**args, "gathered_data": gathered}
                            quality_block = loop_coach.scratchpad_quality_block(gathered)
                            if quality_block:
                                result = quality_block
                                if self.console:
                                    self.console.event("scratchpad_block")
                            else:
                                args, research_note = self._normalize_research_tool_args(
                                    tool_name, args, task_name
                                )
                                tc = {**tc, "arguments": args}
                                self.console.log_tool_start(tool_name, args)
                                execution_results = self.executor.execute([tc])
                                result = (
                                    execution_results[0]
                                    if execution_results
                                    else "No output."
                                )
                                suffix = step_policy.os_suffix_after_tool(
                                    tool_name, str(result)
                                )
                                if suffix:
                                    result += suffix
                                if (
                                    self.mode == "research"
                                    and research_note
                                    and result
                                    and not str(result).startswith("❌")
                                ):
                                    draft_msg = self._maybe_store_research_deliverable_draft(
                                        research_note,
                                        step_kind=step_kind,
                                        is_final_step=is_final_step,
                                        read_notes_this_step=read_notes_this_step,
                                    )
                                    if draft_msg:
                                        result += draft_msg
                                if (
                                    self.mode == "character_build"
                                    and step_kind == "search"
                                    and result
                                    and not str(result).startswith("❌")
                                ):
                                    result += loop_coach.persona_search_complete_hint()
                        else:
                            args, research_note = self._normalize_research_tool_args(
                                tool_name, args, task_name
                            )
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
                                draft_msg = self._maybe_store_research_deliverable_draft(
                                    research_note,
                                    step_kind=step_kind,
                                    is_final_step=is_final_step,
                                    read_notes_this_step=read_notes_this_step,
                                )
                                if draft_msg:
                                    result += draft_msg
                            if (
                                tool_name == "read_all_research_notes"
                                and result
                                and not str(result).startswith("❌")
                            ):
                                read_notes_this_step = True
                            if (
                                tool_name == "save_task_deliverable"
                                and result
                                and not str(result).startswith("❌")
                            ):
                                result += "\n⚠️ OS: Deliverable saved. If this completes your objective, you MUST now call finish_task to formally end the run."
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
                                tool_name == "read_all_research_notes"
                                and self._scratchpad_injected_this_step
                                and result
                                and not str(result).startswith("❌")
                            ):
                                read_notes_this_step = True
                                if (
                                    self.mode == "research"
                                    and is_final_step
                                ):
                                    result = (
                                        "✅ OS: Prior findings are in the SCRATCHPAD section above "
                                        "(and in tool outputs). Next: output top-level `final_report` "
                                        "and `finish_task` with only `message_to_user` in the "
                                        "**same** JSON object. Do not call read_all_research_notes "
                                        "again."
                                    )
                                else:
                                    result = (
                                        "✅ OS: Research notes are already in the step brief "
                                        "(SCRATCHPAD section)."
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
                                web_search_done_this_turn += 1
                                max_urls_override = None
                                budget_cap = None
                                if web_search_in_turn > 1:
                                    max_urls_override = 1
                                    if scrape_budget_remaining[0] > 0:
                                        budget_cap = max(
                                            MIN_SUB_BUDGET_PER_SEARCH,
                                            scrape_budget_remaining[0]
                                            // web_search_in_turn,
                                        )
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
                                    max_urls_override=max_urls_override,
                                    budget_cap=budget_cap,
                                )
                                loop_coach.record_web_search_result(str(result))
                                if (
                                    self.mode == "research"
                                    and not self.offline_research
                                    and self._milestone_tracker is not None
                                    and self._milestone_tracker.state.read_webpage_count < 1
                                    and "http" in str(result).lower()
                                    and "❌" not in str(result)[:80]
                                ):
                                    result += (
                                        "\n💡 OS: Call `read_webpage` on at least one result "
                                        "URL before `save_research_note`."
                                    )
                        if result and "❌ Error" not in result and not result.startswith("❌"):
                            tools_succeeded_this_step.add(tool_name)
                        if tool_name in (
                            "write_project_markdown",
                            "append_project_markdown",
                        ) and result and result.startswith("✅"):
                            doc_markdown_writes_this_turn += 1

                    # Guardrail: cap oversized tool outputs before they enter conversation history.
                    # This prevents single-tool blowups (e.g., large scratchpad reads, scrapes).
                    try:
                        raw_text = result if isinstance(result, str) else str(result)
                    except Exception:
                        raw_text = ""
                    if raw_text:
                        try:
                            env_cap = int(os.getenv("AQUILA_TOOL_OUTPUT_CHAR_CAP", "").strip() or "0")
                        except ValueError:
                            env_cap = 0
                        default_cap = max(2000, int(get_context_profile().read_file_preview_chars * 2))
                        cap = env_cap if env_cap > 0 else default_cap
                        if len(raw_text) > cap:
                            raw_text = (
                                raw_text[:cap]
                                + f"\n... [tool output truncated to {cap} chars; "
                                "see scratchpad/files or re-run tool with narrower scope]"
                            )
                        result = raw_text

                    if (
                        result
                        and tool_name in ("read_file_region", "get_directory_tree", "read_file")
                        and (
                            "not found" in str(result).lower()
                            or str(result).startswith("❌")
                        )
                    ):
                        fail_path = str(
                            tc.get("arguments", {}).get("file_path")
                            or tc.get("arguments", {}).get("path")
                            or ""
                        )
                        if fail_path:
                            path_registry.record_path_failure(tool_name, fail_path)
                            if self.console and (
                                "/Aquila/" in fail_path.replace("\\", "/")
                                or (
                                    fail_path.startswith("/")
                                    and not fail_path.startswith("//")
                                )
                            ):
                                self.console.event(
                                    "explore_path_hallucination",
                                    path=fail_path,
                                    tool=tool_name,
                                )

                    if (
                        tool_name == "read_webpage"
                        and result
                        and "404" in str(result)
                        and "github.com" in str(tc.get("arguments", {}).get("url", "")).lower()
                        and "/blob/" in str(tc.get("arguments", {}).get("url", "")).lower()
                    ):
                        result += loop_coach.github_blob_404_hint()

                    last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                    self.console.log_tool_execution(
                        tool_name, tc.get("arguments", {}), result
                    )
                    if self._milestone_tracker is not None:
                        self._milestone_tracker.record_tool(
                            tool_name, str(result), mode=self.mode
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
                    and self._milestone_tracker
                    and self._auto_advance_milestones
                    and (
                        self._dynamic_loop_active
                        or self.mode == "code"
                    )
                    and self._milestone_tracker.should_suggest_advance(
                        self.mode, is_final_step=is_final_step
                    )
                ):
                    has_advance = True
                    advance_summary = (
                        "Milestones complete for this step (dynamic loop auto-advance)."
                    )
                    last_tool_output += (
                        "\n\n✅ OS: Step milestones satisfied. Advancing ledger — "
                        + (
                            "continue on the next step or finalize via capability on finalize."
                            if self._uses_capability_act()
                            else "continue on the next step or call finish_task on finalize."
                        )
                    )
                    if last_tool_output and conversation_history:
                        conversation_history[-1] = {
                            "role": "user",
                            "content": f"Tool Outputs:{last_tool_output}",
                        }

                if (
                    not has_advance
                    and not has_finish
                    and not self._uses_capability_act()
                    and not self._dynamic_loop_active
                    and self.mode == "character_build"
                    and step_kind == "search"
                    and self.persona_research_lore
                    and "save_research_note" in tools_succeeded_this_step
                ):
                    has_advance = True
                    advance_summary = (
                        "Captured web lore on search step; advancing to read/ingest or synthesize."
                    )
                    last_tool_output += (
                        "\n\n✅ OS: Search-step lore complete. Advancing — use read step "
                        "only for user attachments, then write_persona_file on synthesize."
                    )
                    conversation_history[-1] = {
                        "role": "user",
                        "content": f"Tool Outputs:{last_tool_output}",
                    }

                if (
                    not has_advance
                    and not has_finish
                    and not self._uses_capability_act()
                    and not self._dynamic_loop_active
                    and self.mode == "character_build"
                    and step_kind == "read"
                    and (
                        "save_research_note" in tools_succeeded_this_step
                        or (
                            self.persona_research_lore
                            and self._scratchpad_has_lore(task_name)
                            and step_episodes_run <= 1
                        )
                    )
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
                    and not self._uses_capability_act()
                    and self.mode == "learn_syllabus_build"
                    and step_kind in ("read", "search")
                    and "save_research_note" in tools_succeeded_this_step
                ):
                    has_advance = True
                    advance_summary = (
                        "Ingested course research; advancing to syllabus synthesis."
                    )
                    last_tool_output += (
                        "\n\n✅ OS: Ingest/search step complete. Advancing — on synthesize "
                        "call read_all_research_notes at most once, then write_syllabus_file."
                    )
                    conversation_history[-1] = {
                        "role": "user",
                        "content": f"Tool Outputs:{last_tool_output}",
                    }

                if (
                    not has_advance
                    and not has_finish
                    and not self._uses_capability_act()
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

                if (
                    not has_advance
                    and not has_finish
                    and not self._uses_capability_act()
                    and self.mode == "learn_syllabus_build"
                    and step_kind == "synthesize"
                    and "write_syllabus_file" in tools_succeeded_this_step
                ):
                    has_advance = True
                    advance_summary = "Wrote syllabus.json; advancing to finalize_course."
                    last_tool_output += (
                        "\n\n✅ OS: Synthesize complete. Advancing to finalize — "
                        "call finalize_course then finish_task."
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
                        run_ctx=getattr(self, "_run_ctx", None),
                    )
                    recent_tool_signatures = []
                    step_entry_injected = False
                    grace_used_this_step = False
                    tools_succeeded_this_step = set()
                    caps_succeeded_this_step = set()
                    explore_tool_turns = 0
                    outline_logged_this_step = False
                    path_registry.set_step_index(state["current_step_index"])
                    self._schema_widen_attempts = 0
                    self._parse_failures = 0
                    self._force_full_schema = False
                    self._dynamic_schema_minimal = False
                    self._persona_read_autosave_done = False
                    if self._milestone_tracker is not None:
                        from .loop_objectives import MilestoneState, MilestoneTracker

                        prev = self._milestone_tracker.state
                        saw_report = self._milestone_tracker._saw_final_report
                        self._milestone_tracker = MilestoneTracker()
                        if self.mode == "research":
                            self._milestone_tracker.state = MilestoneState(
                                ingest_done=prev.ingest_done,
                                evidence_count=prev.evidence_count,
                                deliverable_draft=prev.deliverable_draft,
                                web_search_count=prev.web_search_count,
                                read_webpage_count=prev.read_webpage_count,
                                notes_saved=prev.notes_saved,
                            )
                            if saw_report:
                                self._milestone_tracker.note_final_report()
                    read_notes_this_step = False
                    self._milestone_advance_nudged = False
                    loop_tick += 1
                    continue

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
                    walkthrough_path = None
                    episodic_summary = finish_msg
                    plan_approach = None
                    try:
                        from .loop_settings import walkthrough_enabled
                        from .task_artifacts import read_plan_dict, write_walkthrough_artifact
                        from .walkthrough import generate_walkthrough, summarize_tool_log

                        plan = read_plan_dict(task_name, self.mode)
                        plan_approach = str(plan.get("approach_summary") or "")[:500] or None
                        if walkthrough_enabled():
                            tool_log = summarize_tool_log(conversation_history)
                            wt = generate_walkthrough(
                                self.client,
                                task_name=task_name,
                                mode=self.mode,
                                user_goal=str(plan.get("user_goal") or user_request),
                                plan_summary=str(plan.get("approach_summary") or ""),
                                tool_summary=tool_log,
                                deliverable_path=saved,
                                finish_msg=finish_msg,
                            )
                            walkthrough_path, _refl = write_walkthrough_artifact(
                                task_name, self.mode, wt
                            )
                            parts = [wt.get("summary", ""), ""]
                            parts.extend(wt.get("what_we_did") or [])
                            episodic_summary = "\n".join(p for p in parts if p)[:4000]
                    except Exception:
                        pass
                    self.memory.store_experience(
                        task_name,
                        episodic_summary,
                        instance_id=self.instance_id,
                        mode=self.mode,
                        walkthrough_path=walkthrough_path,
                        deliverable_path=saved,
                        plan_approach=plan_approach,
                    )
                    if saved:
                        finish_msg += f"\n\n📄 Final report saved to: {saved}"
                    return finish_msg

                if (
                    step_episodes_run
                    >= max_step_iterations
                    and not has_advance
                    and not has_finish
                ):
                    if (
                        self._dynamic_loop_active
                        and self._task_episode_state is not None
                        and not self._task_episode_state.at_episode_limit()
                    ):
                        soft_limit_msg = (
                            "Tool Outputs:\n💡 OS: Step episode soft limit reached — "
                            "task budget remains. Continue with capabilities or "
                        )
                        if self._uses_capability_act():
                            if self.mode == "code":
                                soft_limit_msg += (
                                    "complete checklist items / run_tests; step auto-advances "
                                    "when milestones are met."
                                )
                            else:
                                soft_limit_msg += (
                                    "complete step milestones; step will auto-advance when ready."
                                )
                        else:
                            soft_limit_msg += (
                                "mark_objective_complete when milestones are met."
                            )
                        conversation_history.append({
                            "role": "user",
                            "content": soft_limit_msg,
                        })
                        continue
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
                        mode=self.mode,
                        capability_act=self._uses_capability_act(),
                    ):
                        self._log_forced_advance(
                            "iteration_limit", step_index=current_idx
                        )
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
                            run_ctx=getattr(self, "_run_ctx", None),
                        )
                        recent_tool_signatures = []
                        step_entry_injected = False
                        grace_used_this_step = False
                        tools_succeeded_this_step = set()
                        caps_succeeded_this_step = set()
                    continue

                for tc in tool_calls:
                    if isinstance(tc, dict):
                        sig = json.dumps(
                            {"name": tc.get("name"), "arguments": tc.get("arguments")},
                            sort_keys=True,
                        )
                        recent_tool_signatures.append(sig)
                if self._capability_research_active() and capability_calls:
                    for call in capability_calls:
                        if not isinstance(call, dict):
                            continue
                        sig = json.dumps(
                            {
                                "id": call.get("id"),
                                "arguments": {
                                    k: v
                                    for k, v in dict(call.get("arguments") or {}).items()
                                    if k != "topic"
                                },
                            },
                            sort_keys=True,
                        )
                        recent_tool_signatures.append(sig)

                # --- Repetition loop detector (legacy tool path; capabilities checked pre-execute) ---
                if self._dynamic_loop_active and not (
                    self._capability_research_active() and capability_calls
                ):
                    tool_names = sorted(
                        tc.get("name") or ""
                        for tc in tool_calls
                        if isinstance(tc, dict)
                    )
                    reasoning = (
                        parsed_response.get("reasoning", "")
                        if isinstance(parsed_response, dict)
                        else ""
                    )
                    combo_hash = hash(reasoning + "".join(tool_names))
                    recent_reasoning_hashes.append(combo_hash)

                    if len(recent_reasoning_hashes) >= 3 and len(set(recent_reasoning_hashes[-3:])) == 1:
                        pending_ms = [
                            lbl for lbl, ok in self._milestone_tracker.state._checks(self.mode, is_final_step=is_final_step)
                            if not ok
                        ] if self._milestone_tracker else []
                        rep_hint = loop_coach.repetition_break_hint(pending_ms, self._schema_tool_names or frozenset())
                        conversation_history.append({
                            "role": "user",
                            "content": f"Tool Outputs:\n{rep_hint}",
                        })
                        recent_reasoning_hashes.clear()
                        recent_tool_signatures.clear()
                        if hasattr(self.console, "event"):
                            self.console.event(
                                "repetition_loop_detected",
                                step_index=current_idx,
                                capability_ids=tool_names,
                                reasoning_preview=str(reasoning)[:300],
                                hint_preview=str(rep_hint)[:400],
                            )
                        continue
                # --- END ---

                block_msg = url_registry.duplicate_tool_block(recent_tool_signatures)
                if block_msg:
                    block_msg = loop_coach.enhance_duplicate_tool_block(block_msg)
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
                        dup_msg = loop_coach.enhance_duplicate_tool_warning(dup_msg)
                        conversation_history.append({
                            "role": "user",
                            "content": f"Tool Outputs:\n{dup_msg}",
                        })

                if ran_non_meta_tool:
                    if step_kind == "explore":
                        explore_tool_turns += 1
                    step_episodes_run += 1
                    for msg in reversed(conversation_history):
                        if msg.get("role") == "assistant":
                            msg["_counts_as_episode"] = True
                            break
                    if self._task_episode_state is not None:
                        self._task_episode_state.episode_count += 1
                        if (
                            self._dynamic_loop_active
                            and self._task_episode_state.can_apply_grace()
                            and tools_succeeded_this_step
                        ):
                            self._task_episode_state.apply_grace(4)
                            ledger_text += (
                                "\n📊 OS: Task episode grace (+4) after productive tools.\n"
                            )

                # --- NEW: Progress stall early-halt ---
                if self._dynamic_loop_active and self._milestone_tracker:
                    current_snapshot = tuple(
                        label for label, ok in 
                        self._milestone_tracker.state._checks(self.mode, is_final_step=is_final_step) 
                        if ok
                    )
                    if current_snapshot == _last_milestone_snapshot:
                        _stall_turns += 1
                    else:
                        _stall_turns = 0
                        _last_milestone_snapshot = current_snapshot
                    
                    stall_limit_turns = int(os.getenv("AQUILA_STALL_HALT_TURNS", "8"))
                    if _stall_turns >= stall_limit_turns:
                        if len(recent_reasoning_hashes) >= 3 and len(set(recent_reasoning_hashes[-3:])) == 1:
                            if hasattr(self.console, "event"):
                                self.console.event("stall_halt", step_index=current_idx, stall_turns=_stall_turns)
                            
                            if is_final_step:
                                ledger_text += "\n🛑 OS: Progress stall detected — forcing task completion.\n"
                                has_finish = True
                            else:
                                ledger_text += "\n🛑 OS: Progress stall detected — forcing step advance.\n"
                                advance_json_state(task_file, "OS forced advance (stall halt)")
                                self.workspace_summary = on_step_advance(
                                    conversation_history=conversation_history,
                                    instance_id=self.instance_id,
                                    task_name=task_name,
                                    advance_summary="OS forced advance (stall halt)",
                                    client=self.client,
                                    memory=self.memory,
                                    run_ctx=getattr(self, "_run_ctx", None),
                                )
                                recent_tool_signatures = []
                                step_entry_injected = False
                                grace_used_this_step = False
                                tools_succeeded_this_step = set()
                                caps_succeeded_this_step = set()
                                continue
                # --- END NEW ---

                if (
                    not has_advance
                    and not has_finish
                    and self._milestone_tracker
                    and not self._auto_advance_milestones
                    and not self._milestone_advance_nudged
                    and (
                        self._dynamic_loop_active
                        or self.mode == "code"
                    )
                    and self._milestone_tracker.should_suggest_advance(
                        self.mode, is_final_step=is_final_step
                    )
                ):
                    self._milestone_advance_nudged = True
                    if self._uses_capability_act() and self.mode == "code":
                        nudge = (
                            "Tool Outputs:\n💡 OS: Checklist/milestones look complete. "
                            "Run `cap.dev.run_tests@v1` or finish remaining checklist items — "
                            "the step will auto-advance when criteria are met."
                        )
                    elif self._uses_capability_act():
                        nudge = (
                            "Tool Outputs:\n💡 OS: Step milestones look complete. "
                            "The step will auto-advance on the next successful verify capability, "
                            "or keep working if something is still missing."
                        )
                    else:
                        nudge = (
                            "Tool Outputs:\n💡 OS: Step milestones look complete. "
                            "Call mark_objective_complete to advance, or keep working "
                            "if something is still missing."
                        )
                    conversation_history.append({
                        "role": "user",
                        "content": nudge,
                    })

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
                                "Tool Outputs:\n⚠️ OS: You have enough sources. "
                                + self._capability_final_stall_nudge()
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

            except UnicodeEncodeError as e:
                return (
                    f"OS Error (console encoding): {e}. "
                    "Set PYTHONIOENCODING=utf-8 or run via aquila-mcp-serve."
                )
            except Exception as e:
                return f"OS Error: {str(e)}"

        return "⚠️ OS halted: Maximum loop ticks reached."

    @staticmethod
    def _research_finalize_os_hint(
        *,
        scratchpad_injected: bool,
        capability_mode: bool = False,
    ) -> str:
        if capability_mode:
            if scratchpad_injected:
                return (
                    "\n\n**FINALIZE:** SCRATCHPAD notes are already in this step brief. "
                    "Put the full report in top-level `final_report` and call "
                    "`cap.research.finalize_deliverable@v1` in the `capabilities` array "
                    "(same JSON response). Example: "
                    '`{"reasoning":"...", "final_report":"# Report\\n...", '
                    '"capabilities":[{"id":"cap.research.finalize_deliverable@v1",'
                    '"arguments":{"topic":"..."}}]}`'
                )
            return (
                "\n\n**FINALIZE:** Use `cap.research.read_notes@v1` if needed, then put the "
                "full report in top-level `final_report` and call "
                "`cap.research.finalize_deliverable@v1` in `capabilities` (same JSON response)."
            )
        if scratchpad_injected:
            return (
                "\n\n**FINALIZE:** SCRATCHPAD notes are already in this step brief. "
                "Do **not** call `read_all_research_notes` unless you need text not shown "
                "above. Put the full report in top-level `final_report` and call "
                "`finish_task` with only `message_to_user` in the **same** JSON response. "
                "Example: "
                '`{"reasoning":"...", "final_report":"# Report\\n...", '
                '"tools":[{"name":"finish_task","arguments":{"message_to_user":"Done."}}]}`'
            )
        return (
            "\n\n**FINALIZE:** Call `read_all_research_notes` once if needed, then put the "
            "full report in top-level `final_report` and call `finish_task` with only "
            "`message_to_user` in the **same** JSON response."
        )

    def _capability_budget_override_msg(self, *, is_final_step: bool) -> str:
        if not self._uses_capability_act():
            if is_final_step:
                return (
                    "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                    "Output `final_report` and call `finish_task` now."
                )
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                "Call `mark_objective_complete` or `finish_task` if done."
            )
        if self.mode == "research":
            if is_final_step:
                return (
                    "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                    "Output top-level `final_report` and call "
                    "`cap.research.finalize_deliverable@v1` now."
                )
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                "Call `mark_objective_complete` or the next research capability if done."
            )
        if self.mode == "character_build":
            if is_final_step:
                return (
                    "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                    "Call `cap.persona.finalize@v1` with greeting and tagline now."
                )
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                "Call `mark_objective_complete` or the next persona capability if done."
            )
        if self.mode == "learn_syllabus_build":
            if is_final_step:
                return (
                    "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                    "Call `cap.learn.finalize_course@v1` now."
                )
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                "Call `mark_objective_complete` or the next learn capability if done."
            )
        if self.mode == "writing":
            if is_final_step:
                return (
                    "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                    "Call `cap.writing.finalize_deliverable@v1` now."
                )
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                "Call `mark_objective_complete` or `cap.writing.draft_sections@v1` if done."
            )
        if self.mode == "code":
            if is_final_step:
                return (
                    "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                    "Call `cap.dev.sync_project@v1` now."
                )
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
                "Work step auto-advances when core checklist items are done or tests pass."
            )
        return (
            "\n\n⚠️ CRITICAL OS OVERRIDE: Task episode budget exhausted. "
            "Call `mark_objective_complete` if done."
        )

    def _capability_step_budget_final_override(self) -> str:
        if not self._uses_capability_act():
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Output final report "
                "into `final_report` and use `finish_task`."
            )
        if self.mode == "research":
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Output top-level "
                "`final_report` and call `cap.research.finalize_deliverable@v1`."
            )
        if self.mode == "character_build":
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Call "
                "`cap.persona.finalize@v1` with greeting and tagline."
            )
        if self.mode == "learn_syllabus_build":
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Call "
                "`cap.learn.finalize_course@v1`."
            )
        if self.mode == "writing":
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Call "
                "`cap.writing.finalize_deliverable@v1`."
            )
        if self.mode == "code":
            block = self._finalize_habit_tracker_block()
            if block:
                return (
                    "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Create missing files "
                    "with `cap.dev.create_file@v1` (e.g. README.md), then call "
                    "`cap.dev.sync_project@v1` once."
                )
            return (
                "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Call "
                "`cap.dev.sync_project@v1`."
            )
        return (
            "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Finalize via capability now."
        )

    def _capability_final_stall_nudge(self) -> str:
        if self._uses_capability_act():
            if self.mode == "research":
                return (
                    "Put findings in top-level `final_report` and call "
                    "`cap.research.finalize_deliverable@v1` in one JSON turn."
                )
            if self.mode == "character_build":
                return (
                    "Call `cap.persona.finalize@v1` with greeting and tagline "
                    "in one JSON turn."
                )
            if self.mode == "learn_syllabus_build":
                return "Call `cap.learn.finalize_course@v1` in one JSON turn."
            if self.mode == "writing":
                return "Call `cap.writing.finalize_deliverable@v1` in one JSON turn."
            if self.mode == "code":
                return "Call `cap.dev.sync_project@v1` in one JSON turn."
        return (
            "Call `save_research_note` with key findings, then output "
            "`final_report` and `finish_task` in one JSON turn."
        )

    @staticmethod
    def _normalize_tool_calls(
        tool_calls: list, pending_final_report: str
    ) -> tuple[list, str]:
        """Hoist final_report from finish_task args (legacy shape) before arg validation."""
        report = pending_final_report or ""
        healed: list = []
        first_save_note_idx = None
        save_note_data_parts = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                healed.append(tc)
                continue
            name = tc.get("name")
            args = tc.get("arguments")
            if name == "save_research_note" and isinstance(args, dict):
                tc = {**tc, "arguments": LoopEngine._heal_save_research_note_args(args)}
                data = tc["arguments"].get("gathered_data", "")
                if data is not None:
                    data_str = str(data).strip()
                    if data_str:
                        save_note_data_parts.append(data_str)
                if first_save_note_idx is None:
                    first_save_note_idx = len(healed)
                    healed.append(tc)
                continue
            if name == "finish_task" and isinstance(args, dict):
                if "final_report" in args:
                    report = args.pop("final_report") or report
            if name == "save_task_deliverable" and isinstance(args, dict):
                if "content" in args:
                    report = args.get("content") or report
            healed.append(tc)

        if first_save_note_idx is not None:
            combined_data = "\n\n".join(save_note_data_parts)
            healed[first_save_note_idx]["arguments"]["gathered_data"] = combined_data

        return healed, report

    def _allow_finish_in_schema(self, is_final_step: bool) -> bool:
        if not is_final_step:
            return False
        if self._dynamic_loop_active and self._milestone_tracker:
            return self._milestone_tracker.should_allow_finish(
                self.mode,
                is_final_step=True,
            )
        return True

    def _schema_for_step(
        self,
        current_objective: str,
        step_kind: str,
        *,
        is_final_step: bool = False,
    ) -> dict:
        from agent.policies.schema_policy import (
            TurnSchemaContext,
            TurnSchemaSpec,
            compile_turn_schema,
            resolve_schema_spec,
            trim_tools_for_schema,
        )

        profile = get_context_profile()
        if not self.base_tools or os.getenv("AQUILA_ROUTE_TOOLS", "1").strip().lower() in (
            "0",
            "false",
            "no",
            "off",
        ):
            return self.action_schema
        routed_cap = profile.routed_tool_cap
        if self._dynamic_loop_active and not self._dynamic_schema_minimal:
            routed_cap = min(routed_cap, 8)
        routed = self.memory.route_tools(
            current_objective, max_tools=routed_cap
        )
        step_policy = get_step_policy(
            self.mode,
            step_kind,
            persona_research_lore=self.persona_research_lore,
            learn_syllabus_web=self.learn_syllabus_web,
            offline_research=self.offline_research,
            writing_brief=self.writing_brief,
        )
        allowed = build_allowed_tool_names(
            mode=self.mode,
            step_kind=step_kind,
            routed=routed,
            all_tool_names=set(self.base_tools.keys()),
            objective=current_objective,
            user_request=getattr(self, "_user_request", ""),
            persona_research_lore=self.persona_research_lore,
            learn_syllabus_web=self.learn_syllabus_web,
            forbidden_tools=step_policy.forbidden_tools_on_step(),
            minimal_palette=self._dynamic_loop_active and self._dynamic_schema_minimal,
        )
        if self._dynamic_loop_active and not self._dynamic_palette_logged:
            if hasattr(self.console, "event"):
                self.console.event("palette_mode", dynamic=True, mode=self.mode)
            self._dynamic_palette_logged = True
        if mcp_allowed_for_mode(self.mode) and self._mcp_bridge:
            for name in self.base_tools:
                if name.startswith("mcp__"):
                    allowed.add(name)
        if self._micro_plan and step_kind == "micro":
            self._force_full_schema = False
        if (
            len(allowed) < 8
            and self._schema_widen_attempts < 2
            and not self._dynamic_loop_active
            and self.mode not in ("character_build", "learn_syllabus_build")
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
                learn_syllabus_web=self.learn_syllabus_web,
                forbidden_tools=step_policy.forbidden_tools_on_step(),
                minimal_palette=self._dynamic_loop_active and self._dynamic_schema_minimal,
            )
        if mcp_allowed_for_mode(self.mode) and self._mcp_bridge:
            for name in self.base_tools:
                if name.startswith("mcp__"):
                    allowed.add(name)

        allow_finish = self._allow_finish_in_schema(is_final_step)
        ctx = TurnSchemaContext(
            mode=self.mode,
            step_kind=step_kind,
            allowed_tools=frozenset(allowed),
            is_final_step=is_final_step,
            allow_finish_task=allow_finish,
            dynamic_loop_active=self._dynamic_loop_active,
            simplify=self._dynamic_loop_active,
            routed=tuple(routed),
        )
        spec = resolve_schema_spec(ctx)

        from agent.parser import resolve_model_output_profile

        out_profile = resolve_model_output_profile(
            getattr(self.client, "model_name", None)
        )
        max_tools = out_profile.max_tools_in_schema
        if self._dynamic_loop_active:
            try:
                from .loop_settings import dynamic_schema_max_tools

                max_tools = min(max_tools, dynamic_schema_max_tools())
            except ImportError:
                max_tools = min(max_tools, 14)

        subset, tool_names = trim_tools_for_schema(
            spec,
            self.base_tools,
            routed=routed,
            mode=self.mode,
            max_tools=max_tools,
        )
        if not subset:
            self._schema_tool_names = frozenset(self.base_tools.keys())
            return self.action_schema

        self._schema_tool_names = tool_names
        spec = TurnSchemaSpec(
            allowed_tools=tool_names,
            max_tools_per_turn=spec.max_tools_per_turn,
            require_final_report=spec.require_final_report,
            allow_finish_task=spec.allow_finish_task,
            simplify=spec.simplify,
            turn_kind=spec.turn_kind,
            excluded_tools=spec.excluded_tools,
            use_one_of=spec.use_one_of,
        )
        schema = compile_turn_schema(
            spec,
            subset,
            mode=self.mode,
            step_kind=step_kind,
        )
        if hasattr(self.console, "event"):
            self.console.event(
                "schema_turn",
                turn_kind=spec.turn_kind,
                tool_count=len(tool_names),
                excluded_tools=sorted(spec.excluded_tools),
                is_final_step=is_final_step,
            )
        return schema

    def _execute_tool_batch(
        self,
        tool_calls: list[dict],
        *,
        path_registry: PathVisitRegistry,
        outline_logged_flag: bool,
    ) -> dict:
        """Run a small batch of tools (e.g. stashed from reflect). Returns summary dict."""
        from .main import normalize_tool_calls_list

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
                from agent.policies import normalize_code_tool_path

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

    def _should_run_think_phase(
        self,
        parse_retries: int,
        *,
        skip_think_phase: bool = False,
        step_kind: str = "",
    ) -> bool:
        if skip_think_phase:
            return False
        try:
            from agent.policies.thinking_tiers import should_run_reflect_pass

            return should_run_reflect_pass(
                mode=self.mode,
                micro_plan=bool(self._micro_plan),
                parse_retries=parse_retries,
                last_act_needs_reflect=bool(
                    getattr(self, "_last_act_needs_reflect", False)
                ),
                model_name=getattr(self.client, "model_name", None),
            )
        except ImportError:
            return False

    def _format_tool_preview_for_think(self, *, step_kind: str = "") -> str:
        if not self._schema_tool_names:
            return ""
        from agent.policies import META_TOOLS, schema_hint_tool_names

        hint_allowed = set(self._schema_tool_names)
        if self._dynamic_loop_active:
            try:
                from agent.policies import DYNAMIC_CORE_PALETTE, MODE_REQUIRED

                core = DYNAMIC_CORE_PALETTE.get(self.mode, frozenset())
                req = MODE_REQUIRED.get(self.mode, frozenset())
                hint_allowed &= set(core) | set(req) | set(META_TOOLS)

            except ImportError:
                pass
        names = schema_hint_tool_names(
            hint_allowed,
            mode=self.mode,
            limit=12,
        )
        if not names:
            return ""
        noun = "capabilities" if self._capability_research_active() else "tools"
        return (
            f"\n\n**Next act turn {noun}** (you cannot call {noun} during this think pass; "
            f"the following will be available in JSON on the next message): "
            f"{', '.join(names)}"
        )

    @staticmethod
    def _summarize_think_for_history(thinking: str, content: str) -> str:
        from .main import _ThinkStreamFilter

        think = (thinking or "").strip()
        body = (content or "").strip()
        if think:
            cap = 4000
            if len(think) > cap:
                think = think[:cap] + "\n… [thinking truncated for history]"
            return think
        if body:
            return body
        tail = _ThinkStreamFilter.extract_trailing_answer(think)
        return tail or "(think turn — no summary captured)"

    def _run_think_phase(
        self,
        active_memory: list[dict],
        *,
        step_run: StepRunState,
        loop_tick: int,
        thinking_callback=None,
        profile,
        task_name: str,
        conversation_history: list[dict],
        timeout_compress_used: bool,
        ledger_text: str,
        ui_callback=None,
    ) -> tuple[str, str]:
        """
        Native-thinking reflect pass. Mutates conversation_history on success.
        Returns (status, ledger_append) where status is ok | error | compress_retry.
        """
        import time as _time

        from agent.parser import throughput_from_llm_turn

        if self.console:
            self.console.event(
                "think_turn", iteration=loop_tick + 1, step_kind=step_run.step_kind
            )

        est_tokens = estimate_messages_tokens(active_memory)
        use_stream = thinking_callback is not None
        temperature = 0.3
        _turn_start = _time.time()
        result_dict = self.client.chat(
            active_memory,
            temperature=temperature,
            format=None,
            stream=use_stream,
            estimated_prompt_tokens=est_tokens,
            surface="reflect",
            force_think_disabled=False,
        )
        _turn_duration_ms = int((_time.time() - _turn_start) * 1000)
        raw_response = ""
        thinking_trace = ""
        if isinstance(result_dict, dict):
            raw_response = result_dict.get("message", {}).get("content", "") or ""
            thinking_trace = str(result_dict.get("message", {}).get("thinking", "") or "")
        else:
            raw_response, thinking_trace = self._consume_think_stream(
                result_dict, thinking_callback=thinking_callback
            )

        if is_system_error_response(raw_response) and not thinking_trace.strip():
            if self.console:
                self.console.event(
                    "os_warning",
                    message=raw_response[:200],
                    est_tokens=est_tokens,
                    iteration=loop_tick + 1,
                    phase="reflect",
                )
            cap = profile.in_step_token_cap
            if (
                not timeout_compress_used
                and timeout_compress_retry_enabled(profile)
                and est_tokens > int(cap * 0.8)
            ):
                from agent.policies import compress_step_transcript

                summary = compress_step_transcript(
                    conversation_history, self.client, task_name
                )
                self.workspace_summary = (
                    (self.workspace_summary or "") + "\n" + summary
                )[-profile.workspace_summary_max_chars or 2000 :]
                conversation_history[:] = conversation_history[-4:]
                if self.console:
                    self.console.event(
                        "context_compress",
                        message="timeout compress retry (think)",
                        est_tokens=est_tokens,
                    )
                return "compress_retry", ""
            if ui_callback:
                ui_callback(f"{ledger_text}\n\n❌ OS (think/LLM): {raw_response[:300]}\n")
            return "error", ""

        think_summary = self._summarize_think_for_history(thinking_trace, raw_response)
        ep_display = step_run.episode_count + 1
        _tp_extra = throughput_from_llm_turn(
            raw_response or think_summary,
            _turn_duration_ms,
            thinking=thinking_trace,
            ollama_base_url=getattr(self.client, "base_url", "") or "",
        )
        if hasattr(self.console, "log_agent_turn"):
            self.console.log_agent_turn(
                step_run.plan_step_index,
                step_run.total_steps,
                step_run.step_kind,
                ep_display,
                loop_tick + 1,
                "reflect",
                think_summary,
                est_tokens=est_tokens,
                duration_ms=_turn_duration_ms,
                thinking_preview=thinking_trace,
                ollama_base_url=_tp_extra.get("ollama_base_url"),
                ollama_engine=_tp_extra.get("ollama_engine"),
                throughput_extra=_tp_extra,
            )
        elif self.console:
            self.console.log_iteration(
                loop_tick + 1,
                think_summary,
                phase="reflect",
                est_tokens=est_tokens,
            )

        header = f"--- {step_run.format_progress()} · Think {loop_tick + 1} ---"
        ledger_chunk = f"\n\n{header}\n"
        if thinking_trace.strip():
            preview = thinking_trace.strip()
            if len(preview) > 1200:
                preview = preview[:1200] + "…"
            ledger_chunk += (
                f"<details class='thinking-block'><summary>Thinking</summary>\n"
                f"{preview}\n</details>\n\n"
            )
        if raw_response.strip() and raw_response.strip() != think_summary:
            ledger_chunk += f"{raw_response.strip()}\n"
        elif think_summary:
            ledger_chunk += f"{think_summary[:800]}\n"

        conversation_history.append({
            "role": "assistant",
            "content": think_summary,
            "_counts_as_episode": False,
            "_think_phase": True,
        })
        return "ok", ledger_chunk

    @staticmethod
    def _consume_think_stream(generator, thinking_callback=None) -> tuple[str, str]:
        """Aggregate streamed think-phase chunks; optionally emit thinking tokens."""
        acc_content = ""
        acc_thinking = ""
        try:
            for chunk in generator:
                if not isinstance(chunk, dict):
                    continue
                msg = chunk.get("message") or {}
                acc_content += str(msg.get("content") or "")
                think_part = msg.get("thinking")
                if think_part:
                    acc_thinking += str(think_part)
                    if thinking_callback:
                        thinking_callback(str(think_part))
        except TypeError:
            return "", ""
        content = acc_content.strip()
        thinking = acc_thinking.strip()
        if not content and thinking:
            from .main import _ThinkStreamFilter

            content = _ThinkStreamFilter.extract_trailing_answer(thinking)
        return content, thinking

    @staticmethod
    def _consume_act_stream(generator) -> tuple[str, str]:
        """Aggregate streamed act chunks into content + thinking trace."""
        acc_content = ""
        acc_thinking = ""
        try:
            for chunk in generator:
                if not isinstance(chunk, dict):
                    continue
                msg = chunk.get("message") or {}
                acc_content += str(msg.get("content") or "")
                think_part = msg.get("thinking")
                if think_part:
                    acc_thinking += str(think_part)
        except TypeError:
            return "", ""
        content = acc_content.strip()
        thinking = acc_thinking.strip()
        if not content and thinking:
            from agent.parser import extract_json_text, try_parse_json

            blob = extract_json_text(thinking)
            if try_parse_json(blob):
                content = blob
            else:
                from .main import _ThinkStreamFilter

                content = _ThinkStreamFilter.extract_trailing_answer(thinking)
        return content, thinking

    @staticmethod
    def _recon_complete_in_history(conversation_history: list[dict]) -> bool:
        blob = LoopEngine._tool_output_blob(conversation_history, "")
        lower = blob.lower()
        return (
            "read_code_outline" in lower
            or "get_directory_tree" in lower
            or "cap.dev.recon@v1" in lower
            or "recon complete" in lower
            or "recon (" in lower
        )
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
            hint = (
                "Recon: call `cap.dev.recon@v1` (tree + outline). "
                "Optional `cap.dev.project_setup@v1` if no project buffer. "
                "Do not invent capability IDs."
            )
        elif self.mode == "code" and step_kind == "read":
            hint = (
                "Read: call `cap.dev.read_region@v1` or `cap.dev.recon@v1`. "
                "Do not invent capability IDs."
            )
        elif self.mode == "code" and step_kind in ("code", "work"):
            hint = (
                "Implement: `cap.dev.project_setup@v1` once if buffer empty, then "
                "`cap.dev.create_file@v1` (file_path + full content) for tests and source, "
                "`cap.dev.edit_apply@v1` for patches, `cap.dev.run_tests@v1` to verify. "
                "Tick checklist via `cap.plan.update_checklist@v1`. Step auto-advances "
                "when core checklist items are done or tests pass."
            )
        elif self.mode == "code" and step_kind == "tdd_red":
            if self._slot_fill_active:
                hint = (
                    "TDD red (slot-fill): send ONLY `arguments.content` — OS binds "
                    f"`{self._slot_fill_path or 'tests/test_habit.py'}`. "
                    "Write 3–5 short pytest tests (~40 lines max). No edge-case suites."
                )
            else:
                hint = (
                    "TDD red: call ONLY `cap.dev.create_file@v1` with `file_path` "
                    "(e.g. tests/test_habit.py) and full pytest code in `arguments.content`."
                )
        elif self.mode == "code" and step_kind == "tdd_green":
            if self._slot_fill_active:
                hint = (
                    "TDD green (slot-fill): send ONLY `arguments.content` — OS binds "
                    f"`{self._slot_fill_path or 'habit.py'}`. "
                    "Minimal CLI: add / done / list, habits.json storage (~40 lines)."
                )
            else:
                hint = (
                    "TDD green: create `habit.py` via `cap.dev.create_file@v1` if missing, "
                    "then `cap.dev.edit_apply@v1` or `cap.dev.run_tests@v1` until green."
                )
        elif self.mode == "code" and step_kind == "tdd_refactor":
            hint = (
                "TDD refactor: edit via `cap.dev.edit_apply@v1`, lint and re-run tests."
            )
        elif self.mode == "code" and step_kind == "verify":
            hint = (
                "Verify: call `cap.dev.run_tests@v1` / `cap.dev.run_linter@v1` "
                "(sync via `cap.dev.sync_project@v1` if needed)."
            )
        elif self.mode == "code" and step_kind == "finalize":
            hint = (
                "Finalize: create `README.md` with `cap.dev.create_file@v1` if missing, "
                "then call `cap.dev.sync_project@v1`."
            )
        elif self.mode == "character_build" and step_kind == "search":
            hint = (
                "Gather lore: call `cap.persona.gather_lore@v1` once with a focused topic. "
                "Do NOT call `write_initialization` or finalize capabilities on this step."
            )
        elif self.mode == "character_build" and step_kind == "read":
            hint = (
                "Ingest sources: call `cap.persona.ingest_sources@v1` once. "
                "Scratchpad notes are injected on later steps. "
                "Do NOT call `write_initialization` or finalize capabilities on this step."
            )
        elif self.mode == "character_build" and step_kind == "synthesize":
            hint = (
                "SCRATCHPAD below. Call ONLY `cap.persona.write_initialization@v1` "
                'with arguments.content = full initialization.md text (≥800 chars), '
                "including a Scene agency section. Do not invent capability IDs."
            )
        elif self.mode == "character_build" and step_kind == "finalize":
            hint = (
                "Finalize the persona: call `cap.persona.finalize@v1` with greeting and tagline "
                "(empty arguments ok for defaults)."
            )
        elif self.mode == "learn_syllabus_build" and step_kind == "search":
            hint = (
                "Web research: call `cap.learn.gather_topic_sources@v1` once with topic. "
                "Do not invent capability IDs outside the allowed list."
            )
        elif self.mode == "learn_syllabus_build" and step_kind == "read":
            hint = (
                "Course ingest: call `cap.learn.ingest_course_materials@v1` once. "
                "Do not invent capability IDs outside the allowed list."
            )
        elif self.mode == "learn_syllabus_build" and step_kind == "synthesize":
            hint = (
                "SCRATCHPAD below (already ingested). Call ONLY "
                "`cap.learn.write_syllabus@v1` with "
                'arguments: {"content": "<syllabus JSON string>"}. '
                "Requirements: ≥8 nodes, ≥5 with parent_id, specific titles, mastery_tier 0. "
                "Do not invent capability IDs outside the allowed list. "
                "Example: "
                '{"reasoning":"Writing syllabus.","capabilities":[{"id":'
                '"cap.learn.write_syllabus@v1","arguments":{"content":'
                '"{\\"version\\":1,\\"nodes\\":[...]}"}}]}'
            )
        elif self.mode == "learn_syllabus_build" and step_kind == "finalize":
            hint = "Call `cap.learn.finalize_course@v1` (empty arguments ok)."
        elif self.mode == "writing" and step_kind in ("write", "work"):
            brief_hint = ""
            if self.writing_brief:
                from agent.functions.writing_brief import WritingBrief

                brief = WritingBrief.from_plan_dict(self.writing_brief)
                if brief:
                    brief_hint = f" Brief: {brief.milestone_summary()}."
            hint = (
                "Draft: call `cap.writing.init_document@v1` if no buffer exists, then "
                "`cap.writing.draft_sections@v1` with grouped subsections. "
                "section_header = plain title (no #); content = body only "
                "(do NOT repeat the title as a leading # / ## heading). "
                f"{brief_hint} Use SCRATCHPAD sources when present. "
                "Optional `cap.writing.read_outline@v1`. Do not invent capability IDs."
            )
        elif self.mode == "writing" and step_kind == "read":
            hint = (
                "Ingest sources: call `cap.writing.ingest_sources@v1` once "
                "(attachments are in context). Then mark_objective_complete."
            )
        elif self.mode == "writing" and step_kind == "finalize":
            hint = (
                "Finalize: call `cap.writing.finalize_deliverable@v1` "
                "(empty arguments ok; compiles the draft). Do not invent capability IDs."
            )
        elif self.mode == "research" and step_kind in ("search", "read"):
            if self.offline_research:
                hint = (
                    "Offline research: call `cap.research.ingest_offline@v1` to extract facts "
                    "from attachments and journal — no web capabilities."
                )
            else:
                hint = (
                    "Gather sources: prefer `cap.research.gather_web_sources@v1` (or the plan "
                    "`capability_id`); append notes via research capabilities — not raw web tools."
                )
        elif self.mode == "research" and step_kind == "synthesize":
            hint = (
                "Synthesize findings: call `cap.research.synthesize_notes@v1` from scratchpad "
                "notes already in this brief."
            )
        elif self.mode == "research" and step_kind == "finalize":
            hint = (
                "Finalize deliverable: put the full report in top-level `final_report` and call "
                "`cap.research.finalize_deliverable@v1` in the same JSON turn."
            )
        elif self.mode == "research" and step_kind == "work":
            if self.offline_research:
                hint = (
                    "Offline research work: use `cap.research.ingest_offline@v1` then "
                    "`cap.research.synthesize_notes@v1` — no web capabilities."
                )
            else:
                hint = (
                    "Research work: interleave gather / append-note / synthesize capabilities; "
                    "advance when milestones are met."
                )
        elif self._dynamic_loop_active and step_kind in ("work", "micro"):
            if self.offline_research and self.mode == "research":
                hint = (
                    "Dynamic offline research loop: `cap.research.ingest_offline@v1` and "
                    "`cap.research.synthesize_notes@v1` — no web capabilities."
                )
            elif self.mode == "research":
                hint = (
                    "Dynamic research loop: interleave gather / append-note / synthesize "
                    "capabilities until milestones are met, then advance."
                )
            elif self.mode == "code":
                hint = (
                    "Dynamic code work: interleave `cap.dev.edit_apply@v1`, "
                    "`cap.dev.create_file@v1`, `cap.dev.recon@v1`, "
                    "`cap.dev.run_tests@v1`, and `cap.dev.write_docs@v1`. "
                    "Wide allowlist — not phase-locked. Call mark_objective_complete "
                    "when step milestones are met."
                )
            else:
                hint = (
                    "Dynamic work phase: interleave read, grep, edit, test, and notes. "
                    "Tools are not phase-locked. Call mark_objective_complete when step "
                    "milestones are met."
                )
        elif (
            self.mode == "code"
            and step_kind == "micro"
            and os.getenv("AQUILA_MICRO_PLAN_CODE_SINGLE", "").strip().lower()
            in ("1", "true", "yes", "on")
        ):
            hint = (
                "Harness smoke: `cap.dev.project_setup@v1` (init harness-smoke), "
                "`cap.dev.create_file@v1` with harness_smoke.py printing HARNESS_OK, "
                "then `cap.dev.sync_project@v1`. No exploration."
            )
        else:
            hint = get_step_kind_hint(step_kind, mode=self.mode)
        cwd = os.getcwd()
        parts = [
            f"WORKSPACE_ROOT: {cwd}",
            f"INSTANCE: {self.instance_id}",
            f"STEP_KIND: {step_kind}",
            f"OS HINT: {hint}",
        ]
        if self.mode == "code":
            if step_kind in ("explore", "read"):
                parts.append(RECON_PLAYBOOK_MARKDOWN)
            if (
                step_kind == "code"
                and conversation_history
                and self._recon_complete_in_history(conversation_history)
            ):
                parts.append(
                    "RECON COMPLETE: Documentation workflow — one file per turn via "
                    "`cap.dev.write_docs@v1`. "
                    "Turn A: ARCHITECTURE.md. Turn B: README.md (or append). "
                    "Do not re-run `cap.dev.recon@v1`."
                )
        if self.workspace_summary and not run_state_enabled():
            parts.append(
                f"--- WORKSPACE SUMMARY ---\n{self.workspace_summary[:8000]}\n--- END ---"
            )
        elif run_state_enabled():
            parts.append(
                "Progress context is in the RUN STATE block (injected separately)."
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
                        "SCOPE: Work ONLY inside CODE_PROJECT_ROOT. Call "
                        "`cap.dev.recon@v1` on the project root, then "
                        "`cap.dev.read_region@v1` — not parent workspace exploration.",
                    )
                else:
                    parts.insert(
                        1,
                        "CODE_PROJECT_ROOT: (none) — call `cap.dev.project_setup@v1` "
                        "before file edits.",
                    )
            except ImportError:
                pass
        if (
            notes
            and "No research notes found" not in notes
            and not (
                self.mode in ("character_build", "learn_syllabus_build")
                and step_kind == "read"
            )
        ):
            self._scratchpad_injected_this_step = True
            if self.mode == "writing" and step_kind in ("write", "work") and notes.strip():
                parts.insert(
                    1,
                    "SOURCE MATERIAL: Use facts from SCRATCHPAD below when drafting sections.",
                )
            if self.mode in ("character_build", "learn_syllabus_build") and step_kind == "synthesize":
                from tool_library.agent_tools import _scratchpad_byte_limit

                cap = _scratchpad_byte_limit() * 4
                if len(notes) > cap:
                    notes = (
                        notes[:cap]
                        + "\n... [step brief capped — synthesize from this excerpt; "
                        "call write_syllabus / write_initialization with full content]"
                    )
            parts.append(f"--- SCRATCHPAD (prior steps) ---\n{notes}\n--- END SCRATCHPAD ---")
        if self.mode == "research" and self.human_research_notes:
            from agent.research import format_journal_context

            parts.append(format_journal_context(self.human_research_notes).strip())
        if self.offline_research and self.mode == "research":
            parts.append(
                "OFFLINE RESEARCH: web capabilities are disabled. "
                "Use `cap.research.ingest_offline@v1` with attachment text, human journal, "
                "and saved research notes."
            )
        living = self._living_plan_step_context(task_name, step_kind)
        if living:
            parts.append(living)
        if self._capability_research_active():
            from agent.capabilities.adapters import (
                PLAN_CHECKLIST_CAP_IDS,
                allowed_capabilities_for_step,
                default_capability_for_step,
            )
            from agent.capabilities.schema_hints import format_capability_argument_hints
            from agent.parser.structured_schema import capability_schema_enrich_max

            allowed_caps = allowed_capabilities_for_step(
                step_kind,
                mode=self.mode,
                offline=self.offline_research,
                has_attachments=self._has_attachment_sources(),
                is_final_step=(step_kind == "finalize"),
                persona_research_lore=self.persona_research_lore,
                learn_syllabus_web=self.learn_syllabus_web,
            )
            action_caps = sorted(allowed_caps - PLAN_CHECKLIST_CAP_IDS)
            if len(action_caps) > capability_schema_enrich_max():
                default_cap = default_capability_for_step(
                    step_kind,
                    mode=self.mode,
                    offline=self.offline_research,
                    has_attachments=self._has_attachment_sources(),
                    persona_research_lore=self.persona_research_lore,
                    learn_syllabus_web=self.learn_syllabus_web,
                )
                hints = format_capability_argument_hints(
                    action_caps,
                    max_caps=6,
                    prioritize=default_cap,
                )
                if hints:
                    parts.append(f"**Capability argument shapes:**\n{hints}")
        return [{"role": "user", "content": "\n".join(parts)}]

    def _living_plan_step_context(self, task_name: str, step_kind: str) -> str:
        """Inject open checklist from implementation_plan when available."""
        kind = (step_kind or "").strip().lower()
        if kind in ("finalize", "explore", "search") and self.mode != "code":
            # Still inject for code explore/work; skip only pure finalize for brevity
            if kind == "finalize":
                return ""
        try:
            from agent.core.implementation_plan import (
                format_implementation_for_act,
                living_plan_modes,
                should_write_living_plan,
            )
            from agent.core.task_artifacts import read_plan_dict

            if (self.mode or "") not in living_plan_modes():
                return ""
            plan = read_plan_dict(task_name, self.mode)
            if not plan or not should_write_living_plan(plan, self.mode):
                return ""
            body = format_implementation_for_act(plan)
            if not body.strip():
                return ""
            nudge = (
                "\nAfter finishing a checklist item, call "
                "`cap.plan.update_checklist@v1` with item_ids (or texts) to mark it done."
            )
            if kind == "finalize":
                nudge = ""
            return f"{body}{nudge}"
        except Exception:
            return ""

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
        episode_count: int = 0,
    ) -> str:
        progress = step_run.format_progress() if step_run else (
            f"Step {current_idx + 1}/{total_steps} ({step_kind})"
        )
        if run_state_enabled() and episode_count > 0 and getattr(self, "_run_ctx", None):
            goal_line = f"**Goal (summary):** {self._run_ctx.goal_summary}\n\n"
        else:
            goal_line = f"**Ultimate Topic/Goal:** {user_request}\n\n"
        return (
            f"{goal_line}"
            f"**YOUR CURRENT OBJECTIVE ({progress}):**\n"
            f"> {current_objective}\n"
            f"**Step kind:** {step_kind}"
        )

    def _assemble_loop_messages(
        self,
        *,
        system_prompt: str,
        step_entry: list[dict],
        conversation_history: list[dict],
        user_message: dict,
        profile=None,
        include_full_goal: bool = False,
    ) -> list[dict]:
        if run_state_enabled() and getattr(self, "_run_ctx", None):
            return self._run_ctx.build_turn_messages(
                system_prompt=system_prompt,
                step_entry=step_entry,
                conversation_history=conversation_history,
                user_message=user_message,
                profile=profile or get_context_profile(),
                include_full_goal=include_full_goal,
                legacy_workspace_summary=self.workspace_summary or "",
            )
        return build_loop_messages(
            system_prompt=system_prompt,
            rolling_summary=self.workspace_summary,
            step_entry=step_entry,
            conversation_history=conversation_history,
            user_message=user_message,
            profile=profile or get_context_profile(),
        )

    def _checkpoint_run_state(
        self,
        *,
        cap_id: str,
        summary_text: str,
        harness_ctx=None,
        ok: bool | None = None,
        result=None,
    ) -> None:
        if not run_state_enabled() or not getattr(self, "_run_ctx", None):
            return
        if result is not None:
            meta = self._run_ctx.checkpoint_capability(
                cap_id=cap_id,
                result=result,
                summary_text=summary_text,
                harness_ctx=harness_ctx,
                client=self.client,
                milestone_tracker=self._milestone_tracker,
                profile=get_context_profile(),
            )
        else:
            meta = self._run_ctx.checkpoint_outcome(
                cap_id=cap_id,
                ok=bool(ok),
                summary_text=summary_text,
                harness_ctx=harness_ctx,
                client=self.client,
                milestone_tracker=self._milestone_tracker,
                profile=get_context_profile(),
            )
        if hasattr(self.console, "event"):
            self.console.event(
                "run_state_checkpoint",
                cap_id=cap_id,
                ok=ok if ok is not None else getattr(result, "ok", None),
                **meta,
            )

    def _record_capability_outcome(
        self,
        *,
        cap_id: str,
        ok: bool,
        summary_text: str,
        harness_ctx=None,
        result=None,
    ) -> None:
        self._last_capability_feedback = summary_text
        self._checkpoint_run_state(
            cap_id=cap_id,
            ok=ok,
            summary_text=summary_text,
            harness_ctx=harness_ctx,
            result=result,
        )

    def _habit_tracker_advance_block(self, *, step_kind: str = "") -> str | None:
        """Block work→finalize until habit-tracker deliverables exist in buffer."""
        kind = (step_kind or "").strip().lower()
        if kind not in ("work", "code", "finalize"):
            return None
        from agent.core.code_scaffolds import habit_tracker_work_complete, is_habit_tracker_goal

        goal = (getattr(self, "_user_request", "") or "").lower()
        if not is_habit_tracker_goal(goal):
            return None
        if habit_tracker_work_complete():
            return None
        return (
            "❌ OS BLOCK: Habit-tracker deliverables incomplete. Create "
            "`habit.py`, `tests/test_habit.py`, and `README.md` with "
            "`cap.dev.create_file@v1` before advancing to finalize."
        )

    def _create_file_content_block(self, args: dict) -> str | None:
        """OS block when create_file is missing or empty content."""
        file_path = str(args.get("file_path") or "").strip()
        if "content" not in args or args.get("content") is None:
            block = (
                "❌ OS BLOCK: `cap.dev.create_file@v1` requires "
                "`arguments.content` (full file body as a string) and "
                "`arguments.file_path`. You did not send `content`. "
                "Retry with both — put the complete test/source text in content."
            )
        elif not str(args.get("content") or "").strip():
            block = (
                "❌ OS BLOCK: `cap.dev.create_file@v1` requires non-empty "
                "`arguments.content` (full file body). You sent an empty string. "
                "Retry with complete test or source code in content."
            )
        elif self._micro_plan and self._slot_fill_active:
            line_count = len(str(args.get("content") or "").splitlines())
            if line_count > 50:
                block = (
                    f"❌ OS BLOCK: micro-plan slot-fill content is {line_count} lines "
                    "(max 50). Write a minimal file: 3–5 short pytest tests OR a "
                    "small habit.py CLI (~40 lines). No edge-case suites."
                )
            else:
                return None
        else:
            return None
        norm = file_path.replace("\\", "/")
        if norm.endswith("__init__.py"):
            block += (
                "\n\n💡 COACH: You do not need `tests/__init__.py` for pytest. "
                "Create `tests/test_habit.py` (or the goal's named test file) with "
                "full pytest content in `arguments.content`."
            )
        fp = file_path or "__missing__"
        attempt = self._create_file_block_counts.get(fp, 0) + 1
        self._create_file_block_counts[fp] = attempt
        coach = LoopCoach(
            mode=self.mode,
            capability_research=self._capability_research_active(),
        )
        block += coach.create_file_retry_hint(
            fp,
            attempt,
            goal=getattr(self, "_user_request", "") or "",
        )
        return block

    def _create_file_goal_path_block(self, args: dict) -> str | None:
        """Block wrong filenames when the user goal names specific deliverables."""
        file_path = str(args.get("file_path") or "").strip().replace("\\", "/")
        if not file_path:
            return None
        goal = (getattr(self, "_user_request", "") or "").lower()
        low = file_path.lower()
        if "habit.py" in goal:
            if low.endswith("habits.py") and not low.endswith("/habit.py"):
                return (
                    "❌ OS BLOCK: Goal requires `habit.py` (singular CLI module), "
                    "not `habits.py`. Retry `cap.dev.create_file@v1` with "
                    "`file_path` = `habit.py` and full CLI source in `arguments.content`."
                )
            if low.endswith("habits.json") and "content" in args:
                return (
                    "❌ OS BLOCK: Do not create `habits.json` directly — it is the "
                    "runtime data file. Create `habit.py` first; it should write "
                    "`habits.json` when run."
                )
        return None

    def _finalize_habit_tracker_block(self) -> str | None:
        """Block finalize sync when required habit-tracker files are still missing."""
        goal = (getattr(self, "_user_request", "") or "").lower()
        if "habit.py" not in goal or "readme" not in goal:
            return None
        from agent.tool_library import code_canvas_tools as canvas

        state = canvas._load_state()
        if not state:
            return None
        paths = []
        raw = state.get("files")
        if isinstance(raw, dict):
            paths = [str(p).replace("\\", "/") for p in raw.keys()]
        elif isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and entry.get("path"):
                    paths.append(str(entry["path"]).replace("\\", "/"))
        has_habit = any(p == "habit.py" or p.endswith("/habit.py") for p in paths)
        has_readme = any(p.lower().endswith("readme.md") for p in paths)
        missing: list[str] = []
        if not has_habit:
            missing.append("`habit.py`")
        if not has_readme:
            missing.append("`README.md`")
        if not missing:
            return None
        return (
            "❌ OS BLOCK (finalize): Missing "
            + ", ".join(missing)
            + ". Create them with `cap.dev.create_file@v1` before "
            "`cap.dev.sync_project@v1`."
        )

    def _bump_create_file_path_attempt(self, file_path: str) -> int:
        fp = (file_path or "").strip().replace("\\", "/") or "__missing__"
        attempt = self._create_file_path_attempts.get(fp, 0) + 1
        self._create_file_path_attempts[fp] = attempt
        return attempt

    def _run_tests_impl_required_block(self) -> str | None:
        """Block run_tests when tests exist but no implementation .py is in the buffer."""
        from agent.core.implementation_plan import is_code_impl_source_path, is_code_test_path
        from agent.tool_library import code_canvas_tools as canvas

        state = canvas._load_state()
        if not state:
            return None
        raw = state.get("files")
        paths: list[str] = []
        if isinstance(raw, dict):
            paths = [str(p) for p in raw.keys()]
        elif isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and entry.get("path"):
                    paths.append(str(entry["path"]))
        test_files = [p for p in paths if is_code_test_path(p)]
        impl_files = [p for p in paths if is_code_impl_source_path(p)]
        if test_files and not impl_files:
            goal = (getattr(self, "_user_request", "") or "").lower()
            impl_hint = "habit.py" if "habit.py" in goal else "the implementation module (.py)"
            return (
                "❌ OS BLOCK: Tests exist but no implementation `.py` file in the buffer. "
                f"Create `{impl_hint}` via `cap.dev.create_file@v1` with full CLI source "
                "in `arguments.content` before calling `cap.dev.run_tests@v1`."
            )
        return None

    def _create_file_exists_block(self, args: dict) -> str | None:
        """OS block when create_file targets a path already in the code buffer."""
        file_path = str(args.get("file_path") or "").strip()
        if not file_path:
            return None
        if "content" not in args or args.get("content") is None:
            return None
        if not str(args.get("content") or "").strip():
            return None
        from agent.tool_library import code_canvas_tools as canvas

        if not canvas.buffer_has_file(file_path):
            return None
        norm = file_path.replace("\\", "/")
        attempt = self._bump_create_file_path_attempt(norm)
        coach = LoopCoach(
            mode=self.mode,
            capability_research=self._capability_research_active(),
        )
        block = (
            f"❌ OS BLOCK: `cap.dev.create_file@v1` cannot create `{norm}` — "
            "the file already exists in the project buffer. "
            "Use `cap.dev.read_region@v1` to inspect it, "
            "`cap.dev.edit_apply@v1` to modify it, or `cap.dev.run_tests@v1` "
            "if tests are ready."
        )
        block += coach.create_file_exists_hint(
            norm,
            attempt,
            goal=getattr(self, "_user_request", "") or "",
        )
        if attempt >= 3:
            block = coach.create_file_path_repeat_block(norm, attempt)
        return block

    def _create_file_path_repeat_pre_execute_block(
        self,
        capability_calls: list[dict],
        *,
        loop_coach: LoopCoach,
    ) -> str | None:
        if not capability_calls:
            return None
        call = capability_calls[0]
        if not isinstance(call, dict):
            return None
        if call.get("id") != "cap.dev.create_file@v1":
            return None
        file_path = str((call.get("arguments") or {}).get("file_path") or "").strip()
        if not file_path:
            return None
        norm = file_path.replace("\\", "/")
        prior = self._create_file_path_attempts.get(norm, 0)
        if prior < 2:
            return None
        attempt = prior + 1
        return loop_coach.create_file_path_repeat_block(norm, attempt)

    @staticmethod
    def _create_file_path_signature(call: dict) -> str:
        args = dict(call.get("arguments") or {})
        fp = str(args.get("file_path") or "").strip().replace("\\", "/")
        return f"cap.dev.create_file@v1|{fp}"

    @staticmethod
    def _capability_call_signature(call: dict) -> str:
        return json.dumps(
            {
                "id": call.get("id"),
                "arguments": {
                    k: v
                    for k, v in dict(call.get("arguments") or {}).items()
                    if k != "topic"
                },
            },
            sort_keys=True,
        )

    def _capability_repeat_pre_execute_block(
        self,
        capability_calls: list[dict],
        recent_signatures: list[str],
        *,
        loop_coach: LoopCoach,
        is_final_step: bool,
    ) -> str | None:
        if not capability_calls:
            return None
        call = capability_calls[0]
        if not isinstance(call, dict):
            return None
        sig = self._capability_call_signature(call)
        if (
            len(recent_signatures) >= 2
            and recent_signatures[-1] == sig
            and recent_signatures[-2] == sig
        ):
            pending_ms: list[str] = []
            if self._milestone_tracker:
                pending_ms = [
                    lbl
                    for lbl, ok in self._milestone_tracker.state._checks(
                        self.mode, is_final_step=is_final_step
                    )
                    if not ok
                ]
            return loop_coach.repetition_break_hint(
                pending_ms,
                self._schema_tool_names or frozenset(),
                repeat_cap_id=str(call.get("id") or ""),
                repeat_file_path=str((call.get("arguments") or {}).get("file_path") or ""),
            )
        return None

    @staticmethod
    def _track_capability_signatures(
        capability_calls: list[dict],
        recent_signatures: list[str],
    ) -> None:
        for call in capability_calls:
            if isinstance(call, dict):
                recent_signatures.append(LoopEngine._capability_call_signature(call))

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

    def _log_forced_advance(self, reason: str, *, step_index: int) -> None:
        if hasattr(self.console, "event"):
            self.console.event(
                "forced_advance",
                reason=reason,
                step_index=step_index,
                dynamic_loop=self._dynamic_loop_active,
            )

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
        self._log_forced_advance("parse_failure_limit", step_index=current_idx)
        advance_json_state(task_file, "OS forced advance (parse failure limit)")
        self.workspace_summary = on_step_advance(
            conversation_history=conversation_history,
            instance_id=self.instance_id,
            task_name=task_name,
            advance_summary="OS forced advance (parse failure limit)",
            client=self.client,
            memory=self.memory,
            run_ctx=getattr(self, "_run_ctx", None),
        )
        return True

    @staticmethod
    def _try_smart_override(
        task_file: str,
        conversation_history: list[dict],
        grace_used: bool,
        tools_succeeded: set[str],
        *,
        mode: str = "",
        capability_act: bool = False,
    ) -> bool:
        """Inject save-and-advance hint before forcing advance. Returns True if injected."""
        if tools_succeeded or grace_used:
            mode_norm = (mode or "").strip().lower()
            if capability_act and mode_norm == "code":
                content = (
                    "Tool Outputs:\n⚠️ OS: Step budget exhausted. "
                    "Tick remaining checklist items via `cap.plan.update_checklist@v1` "
                    "or run `cap.dev.run_tests@v1` — step auto-advances when criteria are met."
                )
            elif capability_act and mode_norm == "research":
                content = (
                    "Tool Outputs:\n⚠️ OS: Step budget exhausted. "
                    "Save progress with `cap.research.append_note@v1` or synthesize notes."
                )
            else:
                content = (
                    "Tool Outputs:\n⚠️ OS: Step budget exhausted. "
                    "Call save_research_note with partial progress, then mark_objective_complete."
                )
            conversation_history.append({
                "role": "user",
                "content": content,
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
            if isinstance(content, str) and (
                "Tool 'run_pytest' result:" in content
                or "Capability 'cap.dev.run_tests@v1' result:" in content
            ):
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
                    "❌ OS BLOCK (tdd_red): Call `cap.dev.run_tests@v1` and confirm "
                    "failing tests (output should mention failed) before "
                    "mark_objective_complete."
                )
        if step_kind == "tdd_green":
            failed_m = re.search(r"(\d+) failed", blob)
            if failed_m and int(failed_m.group(1)) > 0:
                return (
                    "❌ OS BLOCK (tdd_green): `cap.dev.run_tests@v1` must show 0 failed "
                    "before mark_objective_complete."
                )
            if "✅ pytest" not in blob and "passed" not in lower:
                return (
                    "❌ OS BLOCK (tdd_green): Call `cap.dev.run_tests@v1` until tests "
                    "pass before mark_objective_complete."
                )
        return None
    @staticmethod
    def _tool_output_blob(conversation_history: list[dict], last_tool_output: str) -> str:
        parts = [last_tool_output or ""]
        for msg in conversation_history:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and (
                "Tool '" in content or "Capability '" in content
            ):
                parts.append(content)
        return "\n".join(parts)

    @staticmethod
    def _recon_tools_used(conversation_history: list[dict]) -> bool:
        blob = LoopEngine._tool_output_blob(conversation_history, "")
        lower = blob.lower()
        return (
            "get_directory_tree" in lower
            or "read_code_outline" in lower
            or "cap.dev.recon@v1" in lower
            or "recon complete" in lower
            or "recon (" in lower
        )
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
        if "cap.dev.recon@v1" in succeeded:
            return None

        blob = LoopEngine._tool_output_blob(conversation_history, last_tool_output)
        lower = blob.lower()
        has_recon_cap = (
            "cap.dev.recon@v1" in lower
            or "recon complete" in lower
            or "recon (" in lower
        )
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
        has_region = (
            "read_file_region" in lower
            or "read_file" in lower
            or "cap.dev.read_region@v1" in lower
        )
        has_doc = (
            "write_project_markdown" in lower
            or "cap.dev.write_docs@v1" in lower
        )
        if has_recon_cap:
            return None
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
            "`cap.dev.recon@v1` (tree + outline), then `cap.dev.read_region@v1` "
            "(or `cap.dev.write_docs@v1` for doc tasks) before mark_objective_complete."
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
        if self._micro_plan:
            try:
                from .loop_settings import run_digest_compress_for_micro_plan

                if not run_digest_compress_for_micro_plan():
                    return False
            except ImportError:
                return False
        from agent.policies import compress_step_transcript

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

    def _scratchpad_has_lore(self, task_name: str, min_chars: int = 200) -> bool:
        try:
            notes = self.memory.get_scratchpad_notes(task_name) or ""
        except Exception:
            return False
        text = notes.strip()
        if not text or "No research notes found" in text:
            return False
        return len(text) >= min_chars

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

        from .main import format_attachment_context
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

        result = save_research_note(body, task_name=task_name)
        if str(result).startswith("❌"):
            return result
        advance_line = (
            "Attachment lore saved — continue this step "
            "(synthesize notes, then finalize deliverable)."
            if skip_advance
            else "Skipping LLM ingest turn — advancing to synthesize step."
        )
        return (
            f"✅ OS: Pre-ingested {len(chunks)} attachment chunk(s) and user description "
            f"into scratchpad.\n{result}\n{advance_line}"
        )

    def _llm_circuit_breaker_message(self) -> str:
        try:
            from .loop_settings import llm_error_limit

            limit = llm_error_limit()
        except ImportError:
            limit = 3
        url = (
            getattr(self.client, "base_url", None)
            or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        )
        return (
            f"🛑 Ollama LLM unreachable after {limit} consecutive errors at {url}. "
            "Start Ollama (`ollama serve` or tray app) and verify OLLAMA_BASE_URL / "
            "instance profile matches the running server."
        )

    def _maybe_store_research_deliverable_draft(
        self,
        research_note: str,
        *,
        step_kind: str,
        is_final_step: bool,
        read_notes_this_step: bool,
    ) -> str:
        from agent.research import pick_best_deliverable_body

        body = pick_best_deliverable_body(research_note)
        if not body:
            return ""
        min_draft = 2500
        raw = os.getenv("AQUILA_RESEARCH_DRAFT_MIN_CHARS", str(min_draft)).strip()
        try:
            min_draft = max(500, int(raw))
        except ValueError:
            pass
        allow = (
            step_kind == "finalize"
            or is_final_step
            or (read_notes_this_step and len(body) >= min_draft)
        )
        if not allow:
            return ""
        self._research_deliverable_draft = body
        return (
            "\n⚠️ OS: Large synthesis note stored as deliverable draft. On the final step, "
            "put the report in top-level `final_report` (or call finish_task — the OS will "
            "recover this draft if final_report is empty)."
        )

    @staticmethod
    def _heal_save_research_note_args(args: dict) -> dict:
        """Map mistaken field names onto gathered_data before schema validation."""
        args = dict(args or {})
        gathered = str(args.get("gathered_data", "") or "").strip()
        if not gathered:
            for key in ("topic", "fact", "deliverable_type", "content", "note", "text"):
                val = args.get(key)
                if val is not None and str(val).strip():
                    gathered = str(val).strip()
                    break
        gathered = LoopEngine._strip_scratchpad_sentinel(gathered)
        if gathered:
            args["gathered_data"] = gathered
        for key in ("topic", "fact", "deliverable_type"):
            args.pop(key, None)
        return args

    @staticmethod
    def _strip_scratchpad_sentinel(text: str) -> str:
        raw = (text or "").strip()
        sentinel = "No research notes found for this task."
        while raw.startswith(sentinel):
            raw = raw[len(sentinel) :].strip()
        if raw.startswith("=== SCRATCHPAD NOTES"):
            return raw
        return raw

    @staticmethod
    def _strip_scratchpad_task_name_from_tool_calls(tool_calls: list) -> list:
        """Remove model-supplied task_name before schema validation (OS injects at execute)."""
        try:
            from .task_context import SCRATCHPAD_BOUND_TOOLS
        except ImportError:
            return tool_calls
        out: list = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                out.append(tc)
                continue
            name = tc.get("name")
            if name not in SCRATCHPAD_BOUND_TOOLS:
                out.append(tc)
                continue
            args = dict(tc.get("arguments") or {})
            ignored = args.pop("task_name", None)
            if ignored:
                try:
                    from .run_logger import get_active_run_logger
                    from .task_context import get_active_task_id

                    logger = get_active_run_logger()
                    if logger:
                        logger.event(
                            "task_name_ignored",
                            tool=name,
                            requested=str(ignored),
                            active=get_active_task_id(),
                        )
                except Exception:
                    pass
            out.append({**tc, "arguments": args})
        return out

    @staticmethod
    def _normalize_research_tool_args(
        tool_name: str, args: dict, task_name: str
    ) -> tuple[dict, str | None]:
        """Heal save_research_note fields; scratchpad task id is OS-bound."""
        if tool_name not in (
            "save_research_note",
            "read_all_research_notes",
            "summarize_sources",
        ):
            return args, None
        args = dict(args or {})
        args.pop("task_name", None)
        if tool_name == "save_research_note":
            args = LoopEngine._heal_save_research_note_args(args)
        note_text = None
        if tool_name == "save_research_note":
            note_text = str(args.get("gathered_data", "") or "")
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

    def _run_delegate_step(
        self,
        step: dict,
        *,
        task_name: str,
        ui_callback=None,
        cancel_check=None,
    ) -> str:
        from .mode_runner import run_mode, load_delegation_stack

        target_mode = str(
            step.get("target_mode") or step.get("mode") or "research"
        ).strip().lower()
        if target_mode not in DELEGATE_MODES:
            return f"❌ Invalid delegate target_mode: {target_mode!r}"
        objective = str(
            step.get("delegate_objective")
            or step.get("description")
            or "Complete delegated work"
        )
        context = str(step.get("context") or "")
        
        # --- NEW: Inject prior delegation results ---
        parent_id = self._parent_task_id or task_name
        prior_results = load_delegation_stack(parent_id)
        if prior_results:
            prior_lines = []
            for pr in prior_results:
                if pr.status == "completed" and pr.deliverable_path:
                    prior_lines.append(
                        f"- {pr.mode} delegation ({pr.delegation_id}): "
                        f"deliverable at {pr.deliverable_path}"
                    )
                elif pr.status == "completed":
                    prior_lines.append(
                        f"- {pr.mode} delegation ({pr.delegation_id}): "
                        f"completed. {pr.summary[:200]}"
                    )
            if prior_lines:
                context += (
                    "\n\n--- Prior Delegation Results ---\n"
                    + "\n".join(prior_lines)
                )
        # --- END NEW ---

        if ui_callback:
            ui_callback(f"🔗 Delegating to {target_mode} mode...")
        if not self._agent:
            return "❌ delegate failed: agent reference missing"
        result = run_mode(
            self._agent,
            mode=target_mode,
            objective=objective,
            parent_task_id=parent_id,
            context=context,
            ui_callback=ui_callback,
            cancel_check=cancel_check,
        )

        # --- NEW: Inject child deliverable to parent scratchpad ---
        injected_msg = ""
        if result.status == "completed" and result.deliverable_path:
            try:
                from pathlib import Path
                content = Path(result.deliverable_path).read_text(encoding="utf-8")
                wrapped = f"--- DELIVERABLE FROM {target_mode.upper()} DELEGATION ({result.delegation_id}) ---\n{content}"
                if self.memory:
                    self.memory.save_scratchpad_note(parent_id, wrapped)
                    injected_msg = f"\n✅ Deliverable content automatically saved to scratchpad for next modes."
            except Exception as e:
                injected_msg = f"\n⚠️ Could not inject deliverable to scratchpad: {e}"
        # --- END NEW ---

        return (
            f"✅ Delegation ({target_mode}) {result.status}.\n"
            f"{result.summary}\n"
            f"Child ledger: {result.ledger_path}"
            f"{injected_msg}"
        )

    def _run_delegate_from_tool(
        self,
        args: dict,
        *,
        task_name: str,
        cancel_check=None,
    ) -> str:
        step = {
            "target_mode": args.get("mode"),
            "delegate_objective": args.get("objective"),
            "context": args.get("context", ""),
            "description": args.get("objective"),
        }
        return self._run_delegate_step(
            step, task_name=task_name, cancel_check=cancel_check
        )

    def _execute_reads_parallel(self, tool_calls: list[dict]) -> dict[str, str]:
        """Execute read-only tools in parallel; returns {tool_signature: result}."""
        from .main import normalize_tool_calls_list

        reads = [
            tc
            for tc in normalize_tool_calls_list(tool_calls)
            if isinstance(tc, dict)
            and tc.get("name") in self._READ_ONLY_TOOLS
        ]
        if len(reads) < 2:
            return {}
        if os.getenv("AQUILA_READ_BATCH", "1").strip().lower() in (
            "0",
            "false",
            "no",
            "off",
        ):
            return {}
        out: dict[str, str] = {}

        def _run_one(tc: dict) -> tuple[str, str]:
            name = tc.get("name", "")
            self.console.log_tool_start(name, tc.get("arguments") or {})
            results = self.executor.execute([tc])
            sig = f"{name}:{json.dumps(tc.get('arguments') or {}, sort_keys=True)}"
            return sig, results[0] if results else "No output."

        with ThreadPoolExecutor(max_workers=min(4, len(reads))) as pool:
            futures = {pool.submit(_run_one, tc): tc for tc in reads}
            for fut in as_completed(futures):
                try:
                    sig, text = fut.result()
                    out[sig] = text
                except Exception as exc:
                    tc = futures[fut]
                    sig = f"{tc.get('name')}:{json.dumps(tc.get('arguments') or {}, sort_keys=True)}"
                    out[sig] = f"❌ Error - {exc}"
        return out

    CAPABILITY_ACT_MODES = frozenset({
        "research",
        "character_build",
        "learn_syllabus_build",
        "writing",
        # DEAD: "code" — code mode uses code_agent.run_tool_session, not LoopEngine
    })

    def _uses_capability_act(self) -> bool:
        """True when this mode's act turn uses capabilities[] (not tools[])."""
        return self.mode in self.CAPABILITY_ACT_MODES

    def _capability_research_active(self) -> bool:
        """Compatibility alias — prefer `_uses_capability_act` for new call sites."""
        return self._uses_capability_act()

    def _has_attachment_sources(self, text_chunks: list | None = None) -> bool:
        chunks = text_chunks if text_chunks is not None else getattr(
            self, "_run_text_chunks", None
        )
        if any(c and str(c).strip() for c in (chunks or [])):
            return True
        if getattr(self, "_attachment_paths", None):
            return True
        return bool((self.human_research_notes or "").strip())

    def _maybe_advance_satisfied_code_step(
        self,
        step_kind: str,
        state: dict,
        task_file: str,
    ) -> bool:
        """Auto-advance when the code canvas buffer already satisfies this step."""
        kind = (step_kind or "").strip().lower()
        try:
            from agent.tool_library import code_canvas_tools as canvas
            from agent.core.main import advance_json_state, read_json_state
        except ImportError:
            return False
        satisfied = False
        if kind == "tdd_red":
            satisfied = canvas.buffer_has_file("tests/test_habit.py")
        elif kind == "tdd_green":
            satisfied = canvas.buffer_has_file("habit.py")
        elif kind == "work":
            satisfied = canvas.buffer_has_file("README.md")
        if not satisfied:
            return False
        advance_json_state(task_file, f"OS: {kind} deliverable already in buffer.")
        fresh = read_json_state(task_file)
        state.clear()
        state.update(fresh)
        return True

    def _try_habit_tracker_scaffold_fast_path(
        self,
        *,
        task_file: str,
        task_name: str,
        state: dict,
        source_registry,
        cancel_check=None,
        attachment_text_chunks: list | None = None,
    ) -> str | None:
        """After scaffold dispatch: run tests + sync without LLM file-writing loops."""
        try:
            from agent.core.code_scaffolds import (
                habit_tracker_work_complete,
                is_habit_tracker_goal,
            )
            from agent.core.loop_settings import scaffold_dispatch_enabled
            from agent.core.main import advance_json_state, complete_ledger_state, read_json_state
        except ImportError:
            return None

        goal = getattr(self, "_user_request", "") or ""
        if not scaffold_dispatch_enabled() or not is_habit_tracker_goal(goal):
            return None
        if not habit_tracker_work_complete():
            return None

        steps = state.get("steps") or []
        verify_idx = next(
            (i for i, s in enumerate(steps) if (s.get("step_kind") or "") == "verify"),
            None,
        )
        finalize_idx = next(
            (i for i, s in enumerate(steps) if (s.get("step_kind") or "") == "finalize"),
            None,
        )
        target = verify_idx if verify_idx is not None else finalize_idx
        if target is None:
            return None

        idx = int(state.get("current_step_index") or 0)
        while idx < target:
            if idx < len(steps):
                steps[idx]["status"] = "completed"
                steps[idx]["result"] = "OS: scaffold fast path — files pre-written."
            idx += 1
        state["current_step_index"] = idx
        state["steps"] = steps
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

        parts: list[str] = [
            "\n\n⚡ OS: Scaffold fast path — skipping file-writing LLM turns."
        ]

        if verify_idx is not None:
            test_batch = self._execute_capability_batch(
                [{"id": "cap.dev.run_tests@v1", "arguments": {}}],
                task_name=task_name,
                step_kind="verify",
                step_index=verify_idx,
                source_registry=source_registry,
                cancel_check=cancel_check,
                attachment_text_chunks=attachment_text_chunks,
            )
            parts.append("\n" + str(test_batch.get("last_output") or ""))
            if not test_batch.get("last_cap_ok"):
                parts.append("\n❌ Scaffold fast path: tests failed.")
                return "".join(parts)
            advance_json_state(task_file, "Scaffold fast path: tests passed.")
            state = read_json_state(task_file)
            steps = state.get("steps") or steps

        idx = int(state.get("current_step_index") or 0)
        while idx < len(steps) and (steps[idx].get("step_kind") or "") != "finalize":
            steps[idx]["status"] = "completed"
            steps[idx]["result"] = "OS: scaffold fast path — skipped."
            idx += 1
        state["current_step_index"] = idx
        state["steps"] = steps
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

        if idx < len(steps) and (steps[idx].get("step_kind") or "") == "finalize":
            sync_batch = self._execute_capability_batch(
                [{"id": "cap.dev.sync_project@v1", "arguments": {}}],
                task_name=task_name,
                step_kind="finalize",
                step_index=idx,
                source_registry=source_registry,
                cancel_check=cancel_check,
                attachment_text_chunks=attachment_text_chunks,
            )
            parts.append("\n" + str(sync_batch.get("last_output") or ""))
            if not sync_batch.get("last_cap_ok"):
                parts.append("\n❌ Scaffold fast path: sync failed.")
                return "".join(parts)
            advance_json_state(task_file, "Scaffold fast path: synced to disk.")

        complete_ledger_state(task_file, "✅ Habit tracker scaffold fast path complete.")
        parts.append("\n✅ Scaffold fast path complete.")
        return "".join(parts)

    def _should_slot_fill(self, step: dict, step_kind: str) -> bool:
        cap_id = str(step.get("capability_id") or "").strip()
        if not cap_id:
            return False
        if step.get("slot_fill"):
            return True
        try:
            from .loop_settings import slot_fill_enabled

            if slot_fill_enabled():
                return True
        except ImportError:
            pass
        return bool(self._micro_plan and self.mode == "code")

    def _schema_for_capability_step(
        self,
        step_kind: str,
        *,
        is_final_step: bool = False,
        step: dict | None = None,
    ) -> dict:
        from agent.capabilities.adapters import allowed_capabilities_for_step
        from agent.parser.structured_schema import (
            build_capability_action_json_schema,
            build_capability_slot_fill_schema,
        )

        allowed = allowed_capabilities_for_step(
            step_kind,
            mode=self.mode,
            offline=self.offline_research,
            has_attachments=self._has_attachment_sources(),
            is_final_step=is_final_step,
            persona_research_lore=self.persona_research_lore,
            learn_syllabus_web=self.learn_syllabus_web,
        )
        self._schema_tool_names = allowed
        require_report = is_final_step or step_kind == "finalize"
        from agent.capabilities.adapters import PLAN_CHECKLIST_CAP_IDS

        bound = str((step or {}).get("capability_id") or self._bound_cap_id or "").strip()
        if self._slot_fill_active and bound:
            omit: list[str] = []
            if str(getattr(self, "_slot_fill_path", "") or "").strip():
                omit.append("file_path")
            return build_capability_slot_fill_schema(
                bound,
                require_final_report=require_report,
                omit_arg_keys=tuple(omit),
            )
        return build_capability_action_json_schema(
            allowed,
            require_final_report=require_report,
            max_capabilities_per_turn=1,
            action_cap_ids=allowed - PLAN_CHECKLIST_CAP_IDS,
        )

    def _build_capability_context(
        self,
        *,
        task_name: str,
        step_kind: str,
        step_index: int,
        source_registry,
        cancel_check=None,
        attachment_paths: list | None = None,
        attachment_text_chunks: list | None = None,
    ):
        from agent.capabilities.base import CapabilityContext

        chunks = [
            str(c).strip()
            for c in (attachment_text_chunks or [])
            if c and str(c).strip()
        ]
        return CapabilityContext(
            client=self.client,
            memory=self.memory,
            task_id=task_name,
            instance_id=self.instance_id,
            mode=self.mode,
            offline=self.offline_research,
            journal_text=self.human_research_notes,
            human_research_notes=self.human_research_notes,
            attachments=list(attachment_paths or getattr(self, "_attachment_paths", []) or []),
            attachment_text_chunks=chunks,
            user_request=getattr(self, "_user_request", ""),
            cancel_check=cancel_check,
            source_registry=source_registry,
            step_index=step_index,
            step_kind=step_kind,
            writing_brief=self.writing_brief,
        )

    def _normalize_capability_calls(self, capabilities: list) -> list[dict]:
        from agent.capabilities.heal_calls import heal_capability_calls

        bound = str(getattr(self, "_bound_cap_id", "") or "").strip()
        normalized: list[dict] = []
        for call in capabilities or []:
            if not isinstance(call, dict):
                continue
            item = dict(call)
            if self._slot_fill_active and bound:
                if not item.get("id"):
                    item["id"] = bound
                if "arguments" not in item:
                    item = {"id": bound, "arguments": item}
            normalized.append(item)
        return heal_capability_calls(normalized)[:1]

    def _execute_capability_batch(
        self,
        capability_calls: list[dict],
        *,
        task_name: str,
        step_kind: str,
        step_index: int,
        source_registry,
        cancel_check=None,
        attachment_paths: list | None = None,
        attachment_text_chunks: list | None = None,
        pending_final_report: str = "",
        caps_succeeded: set[str] | None = None,
    ) -> dict:
        from agent.capabilities import run_capability

        ctx = self._build_capability_context(
            task_name=task_name,
            step_kind=step_kind,
            step_index=step_index,
            source_registry=source_registry,
            cancel_check=cancel_check,
            attachment_paths=attachment_paths,
            attachment_text_chunks=attachment_text_chunks,
        )
        last_parts: list[str] = []
        executed = 0
        finish_ok = False
        last_cap_id = ""
        last_cap_ok = False
        last_cap_data: dict = {}
        from agent.policies import get_step_policy

        cap_policy = getattr(self, "_step_policy", None)
        if not hasattr(cap_policy, "validate_capability_call"):
            cap_policy = get_step_policy(
                self.mode,
                step_kind,
                persona_research_lore=self.persona_research_lore,
                learn_syllabus_web=self.learn_syllabus_web,
                offline_research=self.offline_research,
                writing_brief=self.writing_brief,
            )
        step_caps = caps_succeeded if caps_succeeded is not None else set()
        finalize_caps = frozenset({
            "cap.research.finalize_deliverable@v1",
            "cap.persona.finalize@v1",
            "cap.learn.finalize_course@v1",
            "cap.writing.finalize_deliverable@v1",
            "cap.writing.compile_document@v1",
        })
        for call in capability_calls:
            cap_id = call.get("id", "")
            args = dict(call.get("arguments") or {})
            if cap_id == "cap.dev.create_file@v1":
                if self._slot_fill_active and not str(args.get("file_path") or "").strip():
                    sp = str(getattr(self, "_slot_fill_path", "") or "").strip()
                    if sp:
                        args["file_path"] = sp
                from agent.core.code_scaffolds import heal_habit_tracker_create_file

                fp_key = str(args.get("file_path") or "__missing__")
                healed = heal_habit_tracker_create_file(
                    goal=getattr(self, "_user_request", "") or "",
                    args=args,
                    step_kind=step_kind,
                    block_attempt=self._create_file_block_counts.get(fp_key, 0),
                )
                if healed:
                    args.update(healed)
            elif cap_id == "cap.dev.write_files@v1":
                from agent.core.code_scaffolds import heal_habit_tracker_write_files

                healed = heal_habit_tracker_write_files(
                    goal=getattr(self, "_user_request", "") or "",
                    args=args,
                    step_kind=step_kind,
                    block_attempt=len(self._create_file_block_counts),
                )
                if healed:
                    args.update(healed)
            read_region_count = self._read_region_step_counts.get(step_index, 0)
            update_checklist_count = self._update_checklist_step_counts.get(step_index, 0)
            sync_project_count = self._sync_project_step_counts.get(step_index, 0)
            validate_fn = getattr(cap_policy, "validate_capability_call", None)
            if callable(validate_fn):
                block = validate_fn(
                    cap_id,
                    tools_succeeded=step_caps,
                    read_region_step_count=read_region_count,
                    update_checklist_step_count=update_checklist_count,
                    sync_project_step_count=sync_project_count,
                    file_path=str(args.get("file_path") or ""),
                )
                if block:
                    last_parts.append(block + "\n")
                    self._record_capability_outcome(
                        cap_id=cap_id,
                        ok=False,
                        summary_text=block,
                        harness_ctx=ctx,
                    )
                    self.console.log_tool_execution(f"cap:{cap_id}", args, block)
                    executed += 1
                    last_cap_id = cap_id
                    last_cap_ok = False
                    continue
            create_block = (
                self._create_file_content_block(args)
                if cap_id == "cap.dev.create_file@v1"
                else None
            )
            if create_block:
                last_parts.append(create_block + "\n")
                self._record_capability_outcome(
                    cap_id=cap_id,
                    ok=False,
                    summary_text=create_block,
                    harness_ctx=ctx,
                )
                self.console.log_tool_execution(f"cap:{cap_id}", args, create_block)
                executed += 1
                last_cap_id = cap_id
                last_cap_ok = False
                continue
            goal_path_block = (
                self._create_file_goal_path_block(args)
                if cap_id == "cap.dev.create_file@v1"
                else None
            )
            if goal_path_block:
                last_parts.append(goal_path_block + "\n")
                self._record_capability_outcome(
                    cap_id=cap_id,
                    ok=False,
                    summary_text=goal_path_block,
                    harness_ctx=ctx,
                )
                self.console.log_tool_execution(f"cap:{cap_id}", args, goal_path_block)
                executed += 1
                last_cap_id = cap_id
                last_cap_ok = False
                continue
            exists_block = (
                self._create_file_exists_block(args)
                if cap_id == "cap.dev.create_file@v1"
                else None
            )
            if exists_block:
                last_parts.append(exists_block + "\n")
                self._record_capability_outcome(
                    cap_id=cap_id,
                    ok=False,
                    summary_text=exists_block,
                    harness_ctx=ctx,
                )
                self.console.log_tool_execution(f"cap:{cap_id}", args, exists_block)
                executed += 1
                last_cap_id = cap_id
                last_cap_ok = False
                continue
            if cap_id == "cap.dev.sync_project@v1":
                finalize_block = self._finalize_habit_tracker_block()
                if finalize_block:
                    self._sync_project_step_counts[step_index] = sync_project_count + 1
                    coach = (
                        "\n\n💡 COACH: On finalize, call `cap.dev.create_file@v1` with "
                        "`file_path` = `README.md` and short usage docs in "
                        "`arguments.content`, then `cap.dev.sync_project@v1` once."
                    )
                    last_parts.append(finalize_block + coach + "\n")
                    self._record_capability_outcome(
                        cap_id=cap_id,
                        ok=False,
                        summary_text=finalize_block,
                        harness_ctx=ctx,
                    )
                    self.console.log_tool_execution(f"cap:{cap_id}", args, finalize_block)
                    executed += 1
                    last_cap_id = cap_id
                    last_cap_ok = False
                    continue
            if cap_id == "cap.dev.run_tests@v1":
                impl_block = self._run_tests_impl_required_block()
                if impl_block:
                    last_parts.append(impl_block + "\n")
                    self._record_capability_outcome(
                        cap_id=cap_id,
                        ok=False,
                        summary_text=impl_block,
                        harness_ctx=ctx,
                    )
                    self.console.log_tool_execution(f"cap:{cap_id}", args, impl_block)
                    executed += 1
                    last_cap_id = cap_id
                    last_cap_ok = False
                    continue
            if cap_id == "cap.dev.edit_apply@v1":
                from agent.tool_library import code_canvas_tools as canvas

                fp = str(args.get("file_path") or "").strip()
                if fp and not canvas.buffer_has_file(fp):
                    block = (
                        f"❌ OS BLOCK: `{fp}` is not in the project buffer. "
                        "Use `cap.dev.create_file@v1` with `file_path` and full "
                        "`arguments.content` to create it first."
                    )
                    last_parts.append(block + "\n")
                    self._record_capability_outcome(
                        cap_id=cap_id,
                        ok=False,
                        summary_text=block,
                        harness_ctx=ctx,
                    )
                    self.console.log_tool_execution(f"cap:{cap_id}", args, block)
                    executed += 1
                    last_cap_id = cap_id
                    last_cap_ok = False
                    continue
                missing = [
                    k
                    for k in ("file_path", "old_string", "new_string")
                    if not str(args.get(k) or "").strip()
                ]
                if missing:
                    block = (
                        "❌ OS BLOCK: `cap.dev.edit_apply@v1` requires "
                        f"{', '.join(missing)}. Retry with complete arguments."
                    )
                    if fp and not str(args.get("content") or "").strip():
                        block += (
                            "\n\n💡 COACH: For a new file, use `cap.dev.create_file@v1` "
                            f"with `file_path` = `{fp}` and the full file body in "
                            "`arguments.content` — not edit_apply."
                        )
                    last_parts.append(block + "\n")
                    self._record_capability_outcome(
                        cap_id=cap_id,
                        ok=False,
                        summary_text=block,
                        harness_ctx=ctx,
                    )
                    self.console.log_tool_execution(f"cap:{cap_id}", args, block)
                    executed += 1
                    last_cap_id = cap_id
                    last_cap_ok = False
                    continue
            if pending_final_report and cap_id == "cap.research.finalize_deliverable@v1":
                args.setdefault("report_body", pending_final_report)
            # Do not stuff the full user goal into create/edit/test caps — it
            # crowds out real args (content) and confuses small models.
            _skip_topic = frozenset({
                "cap.dev.create_file@v1",
                "cap.dev.edit_apply@v1",
                "cap.dev.run_tests@v1",
                "cap.dev.run_linter@v1",
                "cap.dev.sync_project@v1",
                "cap.dev.write_docs@v1",
                "cap.dev.recon@v1",
                "cap.dev.read_region@v1",
                "cap.dev.project_setup@v1",
                "cap.plan.update_checklist@v1",
                "cap.plan.read_implementation@v1",
            })
            if cap_id not in _skip_topic and not args.get("topic"):
                args.setdefault("topic", getattr(self, "_user_request", "") or task_name)
            if cap_id == "cap.learn.write_syllabus@v1":
                from agent.capabilities.learn.write_syllabus import coerce_syllabus_content

                coerced = coerce_syllabus_content(args)
                if coerced:
                    args = {"content": coerced}
            self.console.log_tool_start(f"cap:{cap_id}", args)
            result = run_capability(cap_id, ctx, args)
            executed += 1
            if cap_id == "cap.dev.read_region@v1":
                self._read_region_step_counts[step_index] = read_region_count + 1
            if cap_id == "cap.plan.update_checklist@v1":
                self._update_checklist_step_counts[step_index] = update_checklist_count + 1
            if cap_id == "cap.dev.sync_project@v1":
                self._sync_project_step_counts[step_index] = sync_project_count + 1
            last_cap_id = cap_id
            last_cap_ok = bool(result.ok)
            last_cap_data = dict(getattr(result, "data", None) or {})
            from agent.capabilities.base import format_capability_result_for_llm

            text = format_capability_result_for_llm(result)
            if (
                not result.ok
                and cap_id == "cap.learn.write_syllabus@v1"
                and "content" in (result.error_message or "").lower()
            ):
                text += (
                    "\n\n❌ OS HINT: Call `cap.learn.write_syllabus@v1` with "
                    'arguments.content set to the full syllabus JSON string '
                    '(or put nodes/title fields directly in arguments). '
                    "Do not invent capability IDs outside the allowed list."
                )
            if (
                not result.ok
                and cap_id == "cap.dev.create_file@v1"
                and "content" in (result.error_message or text or "").lower()
            ):
                text += (
                    "\n\n❌ OS HINT: Retry `cap.dev.create_file@v1` with "
                    "arguments.file_path AND arguments.content (full file text). "
                    "Do not call create_file with only a path."
                )
            if (
                not result.ok
                and cap_id == "cap.dev.create_file@v1"
                and "exists" in (result.error_message or text or "").lower()
            ):
                fp = str(args.get("file_path") or "").strip()
                attempt = self._bump_create_file_path_attempt(fp)
                coach = LoopCoach(
                    mode=self.mode,
                    capability_research=self._capability_research_active(),
                )
                text += coach.create_file_exists_hint(
                    fp,
                    attempt,
                    goal=getattr(self, "_user_request", "") or "",
                )
            if result.ok and cap_id == "cap.dev.project_setup@v1":
                text += (
                    "\n\n✅ OS: Project buffer ready. Do NOT call project_setup or "
                    "recon again. Next: `cap.dev.create_file@v1` for failing tests "
                    "(e.g. tests/test_habit.py), then implement with "
                    "`cap.dev.edit_apply@v1` / create_file for source."
                )
            if result.ok and cap_id == "cap.dev.recon@v1" and step_kind in (
                "work",
                "code",
                "tdd_red",
                "tdd_green",
                "tdd_refactor",
                "",
            ):
                text += (
                    "\n\n✅ OS: Recon done for this work step. Do NOT re-recon. "
                    "Next: create/edit files or run_tests."
                )
            last_parts.append(f"Capability '{cap_id}' result:\n{text}\n")
            self._record_capability_outcome(
                cap_id=cap_id,
                ok=bool(result.ok),
                summary_text=text,
                harness_ctx=ctx,
                result=result,
            )
            self.console.log_tool_execution(f"cap:{cap_id}", args, text)
            if result.ok:
                step_caps.add(cap_id)
            elif (
                cap_id == "cap.research.ingest_offline@v1"
                and _is_scratchpad_dedup_block(result)
            ):
                # Pre-ingest / prior save already has this content — treat as done.
                # Keep last_cap_ok False so work steps do not auto-advance past synthesize.
                step_caps.add(cap_id)
                last_parts.append(
                    "\n✅ OS: Scratchpad already contains this material "
                    "(dedup). Treat ingest as complete. "
                    "Next: `cap.research.synthesize_notes@v1`.\n"
                )
            if self._milestone_tracker:
                self._milestone_tracker.record_capability(
                    cap_id, result, mode=self.mode
                )
            if cap_id in finalize_caps and result.ok:
                finish_ok = True
        return {
            "executed": executed,
            "last_output": "\n".join(last_parts),
            "finish_ok": finish_ok,
            "last_cap_id": last_cap_id,
            "last_cap_ok": last_cap_ok,
            "last_cap_data": last_cap_data,
        }


def _is_scratchpad_dedup_block(result) -> bool:
    err = (getattr(result, "error_message", None) or getattr(result, "summary", None) or "")
    text = str(err).lower()
    return "similar to existing scratchpad" in text or "≥85%" in text or ">=85%" in text
