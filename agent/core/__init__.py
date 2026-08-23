from .main import (
    build_strict_schema,
    get_executable_tools,
    format_attachment_context,
    OllamaClient,
    client,
    apply_runtime_settings,
    assemble_agent_response,
    parse_agent_response,
    should_attach_json_prefill,
    messages_end_with_json_prefill,
    normalize_tool_calls_list,
    validate_tool_calls,
    validate_tool_arguments,
    ToolExecutor,
    initialize_json_ledger,
    read_json_state,
    advance_json_state,
    complete_ledger_state,
    save_task_deliverable,
    Agent,
    get_agent,
    get_global_agent,
    reset_agent_instances,
    _agent_instances,
    initiate_sleep_cycle,
    _ThinkStreamFilter,
    MAX_TOOLS_PER_TURN,
    JSON_REASONING_PREFILL,
    console,
)
from .loop_engine import (
    LoopEngine,
)
from .loop_coach import (
    LoopCoach,
)
from .loop_objectives import (
    MilestoneState,
    MilestoneTracker,
)
from .loop_settings import (
    dynamic_loop_enabled,
    auto_advance_milestones_enabled,
    task_episode_max,
    task_web_search_cap,
    dynamic_schema_max_tools,
    act_two_phase_enabled,
    act_structured_no_plain_enabled,
    plan_structured_no_plain_enabled,
    plan_num_predict,
    plan_review_enabled,
    plan_auto_approve_micro_enabled,
    walkthrough_enabled,
    llm_error_limit,
)
from .plan_validator import (
    mode_step_description,
    sanitize_step_description,
    infer_step_kind,
    get_step_kind_hint,
    validate_and_tune_plan,
    tune_plan_json,
    expand_character_build_plan,
    BUDGET_RUBRIC,
    expand_dynamic_research_plan,
    expand_research_plan,
    expand_offline_research_plan,
    expand_dynamic_offline_research_plan,
    is_degenerate_description,
    expand_learn_syllabus_plan,
)
from .fast_path import (
    fast_path_enabled,
    micro_plan_max_words,
    explore_brief_enabled,
    harness_force_micro_plan,
    should_micro_plan,
    build_micro_plan,
)
from .explore_agent import (
    ExplorationBrief,
    run_brief,
    _brief_from_findings,
)
from .mode_runner import (
    ModeResult,
    run_mode,
    load_delegation_stack,
    delegation_dir,
    make_delegation_task_name,
    resolve_nested_task_file,
)
from .generation_lock import (
    GenerationBusyError,
    LockInfo,
    is_generation_busy,
    try_acquire,
    release,
    generation_lock,
    busy_payload,
    read_lock_info,
)
from .episode_tracker import (
    StepRunState,
    TaskRunState,
    episode_count_from_history,
    should_inject_checkpoint_nudge,
)
from .capability_harness import (
    run_scenario,
    evaluate_run,
    build_run_report,
    HARNESS_SCENARIOS,
    list_scenarios,
    get_scenario,
    clear_harness_stale_state,
    _check_acceptance,
)
from .capability_scorecard import (
    CapabilityScorecard,
    analyze_jsonl,
    CAPABILITY_SCENARIOS,
    score_jsonl_for_scenario,
    write_scorecard_jsonl,
)
from .delegation_tools import (
    delegate_mode,
)
from .mcp_attachments import (
    load_attachments_for_mcp,
    parse_file_paths_arg,
)
from .mcp_bridge import (
    load_mcp_servers_from_settings,
    merge_tools_with_mcp,
    McpBridge,
    McpServerConfig,
    mcp_tool_id,
    parse_mcp_tool_id,
)
from .mcp_host import (
    create_aquila_mcp,
)
from .prompts import (
    MODES_ROSTER,
    get_character_prompt,
    get_persona_build_prompt,
    get_chat_prompt,
    get_autonomous_prompt,
    get_research_prompt,
    get_writing_prompt,
    get_code_prompt,
    get_light_research_chat_addon,
    get_light_coding_chat_addon,
    get_syllabus_build_prompt,
    get_learn_tutor_prompt,
    get_learn_archive_prompt,
    build_learn_archive_user_message,
)
from .run_logger import (
    RunLogger,
    get_active_run_logger,
    _truncate,
)
from .stdio_safe import (
    configure_stdio_utf8,
    console_safe,
    human_print,
    safe_stdout_write,
    mcp_stdio_host_active,
    stdout_supports_unicode,
)
from .task_context import (
    inject_scratchpad_task_id,
    omit_task_name_from_schema,
    get_active_task_id,
    active_task,
    resolve_task_id,
)
from .tool_result import (
    format_tool_result,
)
from .tools import (
    SURVIVAL_TOOLS,
    is_ignored_code_path,
    should_skip_dir,
    get_code_project_root,
    read_file,
    write_file,
    replace_in_file,
    list_directory,
    resolve_tool_path,
    normalize_workspace_path,
    is_safe_path,
    read_file_lines,
)


def __getattr__(name: str):
    if name == "AQUILA_ACTION_SCHEMA":
        from .main import build_strict_schema, get_executable_tools
        return build_strict_schema(get_executable_tools())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


