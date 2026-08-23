"""Compile per-turn JSON schemas from loop state (native constrained decoding)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tool_policy import prioritize_tools_for_schema


@dataclass(frozen=True)
class TurnSchemaContext:
    mode: str
    step_kind: str
    allowed_tools: frozenset[str]
    is_final_step: bool = False
    allow_finish_task: bool = False
    dynamic_loop_active: bool = False
    simplify: bool = False
    routed: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnSchemaSpec:
    allowed_tools: frozenset[str]
    max_tools_per_turn: int = 6
    require_final_report: bool = False
    allow_finish_task: bool = False
    simplify: bool = False
    turn_kind: str = "act"
    excluded_tools: frozenset[str] = field(default_factory=frozenset)
    use_one_of: bool = False


def resolve_schema_spec(ctx: TurnSchemaContext) -> TurnSchemaSpec:
    """Map loop state to a turn schema specification."""
    allowed = set(ctx.allowed_tools)
    excluded: set[str] = set()
    allow_finish = ctx.allow_finish_task and ctx.is_final_step

    if not allow_finish and "finish_task" in allowed:
        excluded.add("finish_task")
        allowed.discard("finish_task")

    max_per_turn = 6
    turn_kind = "act"
    use_one_of = not ctx.dynamic_loop_active and ctx.mode in (
        "research",
        "character_build",
    )

    if ctx.mode == "research" and ctx.step_kind == "search":
        max_per_turn = 1
        turn_kind = "research_search"
        search_palette = frozenset(
            {"web_search", "read_webpage", "save_research_note", "mark_objective_complete"}
        )
        narrowed = allowed & search_palette
        if narrowed:
            allowed = narrowed

    require_report = allow_finish and ctx.is_final_step and ctx.mode == "research"

    return TurnSchemaSpec(
        allowed_tools=frozenset(allowed),
        max_tools_per_turn=max_per_turn,
        require_final_report=require_report,
        allow_finish_task=allow_finish,
        simplify=ctx.simplify,
        turn_kind=turn_kind,
        excluded_tools=frozenset(excluded),
        use_one_of=use_one_of,
    )


def trim_tools_for_schema(
    spec: TurnSchemaSpec,
    registry: dict[str, Any],
    *,
    routed: list[str] | set[str],
    mode: str,
    max_tools: int,
) -> tuple[dict[str, Any], frozenset[str]]:
    """Trim allowed tools to registry keys and schema cap."""
    names = {k for k in spec.allowed_tools if k in registry}
    if not names:
        names = set(registry.keys())
    if len(names) > max_tools:
        names = prioritize_tools_for_schema(
            names,
            routed=set(routed),
            mode=mode,
            max_tools=max_tools,
        )
    subset = {k: registry[k] for k in names if k in registry}
    return subset, frozenset(subset.keys())


def compile_turn_schema(
    spec: TurnSchemaSpec,
    registry: dict[str, Any],
    *,
    mode: str = "",
    step_kind: str = "",
) -> dict[str, Any]:
    """Build Ollama JSON schema from a turn spec."""
    from agent.parser.structured_schema import (
        build_agent_action_json_schema,
        build_turn_type_schemas,
    )

    tool_names = frozenset(k for k in spec.allowed_tools if k in registry)
    if spec.use_one_of and mode and step_kind:
        branch = build_turn_type_schemas(
            tool_names,
            registry,
            mode=mode,
            step_kind=step_kind,
            is_finalize=spec.allow_finish_task,
            simplify=spec.simplify,
        )
        if branch:
            return branch

    return build_agent_action_json_schema(
        tool_names if tool_names else frozenset(registry.keys()),
        registry,
        simplify=spec.simplify,
        max_tools_per_turn=spec.max_tools_per_turn,
        require_final_report=spec.require_final_report,
    )
