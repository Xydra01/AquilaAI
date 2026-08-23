"""
Pydantic models and dynamic JSON Schema generation for Ollama structured output.
"""
from __future__ import annotations

import inspect
import json
from functools import lru_cache
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, create_model

SchemaKind = Literal["agent_action", "task_plan", "reflect", "explore_action"]


_arguments_model_cache: dict[str, type[BaseModel]] = {}
_tool_call_model_cache: dict[str, type[BaseModel]] = {}
_agent_action_model_cache: dict[frozenset[str], type[BaseModel]] = {}
_agent_action_schema_cache: dict[tuple[frozenset[str], bool], dict[str, Any]] = {}


def _safe_model_name(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)


def _annotation_to_json_type(annotation: Any) -> dict[str, Any]:
    """Map a parameter annotation to a JSON Schema fragment (Ollama strict subset)."""
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}

    origin = get_origin(annotation)
    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _annotation_to_json_type(args[0])
        return {"type": "string"}

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is float:
        return {"type": "number"}

    return {"type": "string"}


def param_to_field(param: inspect.Parameter) -> tuple[Any, Any]:
    """Build (annotation, Field) for create_model from inspect.Parameter."""
    ann = param.annotation
    if ann is inspect.Parameter.empty:
        ann = str

    if param.default is inspect.Parameter.empty:
        return ann, Field(...)
    return ann, Field(default=param.default)


def _parameter_expects_int(param: inspect.Parameter) -> bool:
    ann = param.annotation
    if ann is int:
        return True
    origin = get_origin(ann)
    if origin is Union:
        return int in get_args(ann)
    return False


def _parameter_is_optional(param: inspect.Parameter) -> bool:
    if param.default is not inspect.Parameter.empty:
        return True
    ann = param.annotation
    origin = get_origin(ann)
    if origin is Union:
        return type(None) in get_args(ann)
    return False


def _coerce_int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.lstrip("-").isdigit():
            return int(s)
    return None


def sanitize_tool_arguments(args: dict, func: Any, *, tool_name: str = "") -> dict:
    """
    Repair common LLM/tool-parse mistakes before Pydantic validation.

    Drops unparseable optional integers (e.g. truncated JSON fragments in max_chars).
  """
    if not isinstance(args, dict):
        return {}
    sig = inspect.signature(func)
    out = dict(args)
    for key, value in list(out.items()):
        if key not in sig.parameters:
            continue
        param = sig.parameters[key]
        if not _parameter_expects_int(param):
            continue
        coerced = _coerce_int_value(value)
        if coerced is not None:
            out[key] = coerced
            continue
        if _parameter_is_optional(param):
            out.pop(key, None)
    return out


def build_arguments_model(tool_name: str, func: Any) -> type[BaseModel]:
    """Dynamic Pydantic model for one tool's arguments from its signature."""
    if tool_name in _arguments_model_cache:
        return _arguments_model_cache[tool_name]

    sig = inspect.signature(func)
    fields: dict[str, tuple[Any, Any]] = {}
    for param_name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        try:
            from agent.core import omit_task_name_from_schema

            if omit_task_name_from_schema(tool_name, param_name):
                continue
        except ImportError:
            pass
        fields[param_name] = param_to_field(param)

    model_name = f"{_safe_model_name(tool_name)}Args"
    if not fields:
        model = create_model(model_name, __config__=ConfigDict(extra="ignore"))
    else:
        model = create_model(
            model_name,
            __config__=ConfigDict(extra="ignore"),
            **fields,
        )
    _arguments_model_cache[tool_name] = model
    return model


def build_tool_call_model(tool_name: str, func: Any) -> type[BaseModel]:
    """One discriminated tool call: fixed name + typed arguments model."""
    if tool_name in _tool_call_model_cache:
        return _tool_call_model_cache[tool_name]

    args_model = build_arguments_model(tool_name, func)
    model = create_model(
        f"ToolCall_{_safe_model_name(tool_name)}",
        name=(Literal[tool_name], ...),
        arguments=(args_model, Field(...)),
        __config__=ConfigDict(extra="ignore"),
    )
    _tool_call_model_cache[tool_name] = model
    return model


def build_agent_action_model(
    tool_names: frozenset[str],
    registry: dict[str, Any],
) -> type[BaseModel]:
    """Dynamic AgentAction model with discriminated union."""
    names_key = frozenset(tool_names)
    if names_key in _agent_action_model_cache:
        return _agent_action_model_cache[names_key]

    tool_models: list[type[BaseModel]] = []
    for name in sorted(names_key):
        if name not in registry:
            continue
        tool_models.append(build_tool_call_model(name, registry[name]["func"]))

    if not tool_models:
        tool_item_type: Any = dict
    elif len(tool_models) == 1:
        tool_item_type = tool_models[0]
    else:
        tool_item_type = Union[tuple(tool_models)]

    model = create_model(
        "AgentAction",
        reasoning=(
            str,
            Field(
                ...,
                description="Brief operational summary (1-3 sentences); no markdown.",
            ),
        ),
        tools=(
            list[tool_item_type],  # type: ignore[valid-type]
            Field(default_factory=list),
        ),
        final_report=(str | None, Field(default=None)),
        __config__=ConfigDict(extra="ignore"),
    )
    _agent_action_model_cache[names_key] = model
    return model


def _arguments_json_properties(tool_name: str, func: Any) -> tuple[dict, list[str]]:
    """JSON Schema properties + required list for tool arguments."""
    sig = inspect.signature(func)
    props: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        try:
            from agent.core import omit_task_name_from_schema

            if omit_task_name_from_schema(tool_name, param_name):
                continue
        except ImportError:
            pass
        prop = _annotation_to_json_type(
            param.annotation
            if param.annotation is not inspect.Parameter.empty
            else str
        )
        if tool_name in ("write_project_markdown", "append_project_markdown") and (
            param_name == "content"
        ):
            from agent.policies import (
                APPEND_PROJECT_MARKDOWN_MAX_CHARS,
                WRITE_PROJECT_MARKDOWN_MAX_CHARS,
                WRITE_PROJECT_MARKDOWN_SOFT_CHARS,
            )

            if tool_name == "append_project_markdown":
                prop["description"] = (
                    f"Markdown section to append; max {APPEND_PROJECT_MARKDOWN_MAX_CHARS} chars."
                )
            else:
                prop["description"] = (
                    f"Markdown body; prefer under {WRITE_PROJECT_MARKDOWN_SOFT_CHARS} characters "
                    f"per call (hard max {WRITE_PROJECT_MARKDOWN_MAX_CHARS}). "
                    "One file per turn; use append_project_markdown for extra sections."
                )
        elif tool_name == "write_section":
            if param_name == "section_header":
                prop["description"] = "Short markdown header for this section (e.g. '# 1. Executive Summary'). Do NOT put the body text here."
            elif param_name == "content":
                prop["description"] = "Detailed markdown body content for this section. Write as a single continuous line using \\n for newlines."
        elif tool_name == "init_document":
            if param_name == "title":
                prop["description"] = "Title of the document (e.g., 'sqlite_wal_windows.md')."
            elif param_name == "synopsis":
                prop["description"] = "Synopsis or summary outlining the purpose of the document."
        props[param_name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return props, required


def _tool_branch_json_schema(tool_name: str, func: Any) -> dict[str, Any]:
    props, required = _arguments_json_properties(tool_name, func)
    return {
        "type": "object",
        "properties": {
            "name": {"const": tool_name},
            "arguments": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        },
        "required": ["name", "arguments"],
    }


def build_agent_action_json_schema(
    tool_names: frozenset[str],
    registry: dict[str, Any],
    *,
    simplify: bool = False,
    max_tools_per_turn: int | None = None,
    require_final_report: bool = False,
) -> dict[str, Any]:
    """
    Ollama-compatible strict JSON Schema for agent turns.
    Keeps per-tool anyOf branches + name enum (tests and Heretic compatibility).
    """
    names_key = frozenset(tool_names)
    cache_key = (names_key, simplify, max_tools_per_turn, require_final_report)
    if cache_key in _agent_action_schema_cache:
        return _agent_action_schema_cache[cache_key]

    names = sorted(n for n in names_key if n in registry)
    branches = [
        _tool_branch_json_schema(n, registry[n]["func"]) for n in names
    ]

    reasoning_prop: dict[str, Any] = {"type": "string"}
    if not simplify:
        reasoning_prop["description"] = "Your internal thoughts. Do not use markdown."

    tools_prop: dict[str, Any] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": names,
                },
            },
            "anyOf": branches,
            "additionalProperties": False,
        },
    }
    if max_tools_per_turn is not None:
        tools_prop["maxItems"] = max(0, max_tools_per_turn)

    required = ["reasoning", "tools"]
    if require_final_report:
        required.append("final_report")

    schema = {
        "type": "object",
        "properties": {
            "reasoning": reasoning_prop,
            "final_report": {"type": "string"},
            "tools": tools_prop,
        },
        "required": required,
        "additionalProperties": False,
    }
    _agent_action_schema_cache[cache_key] = schema
    return schema


def build_turn_type_schemas(
    tool_names: frozenset[str],
    registry: dict[str, Any],
    *,
    mode: str,
    step_kind: str,
    is_finalize: bool = False,
    simplify: bool = False,
) -> dict[str, Any] | None:
    """Optional oneOf wrapper for rigid mode phases (research / character_build)."""
    mode_norm = (mode or "").strip().lower()
    kind = (step_kind or "").strip().lower()
    if mode_norm not in ("research", "character_build"):
        return None

    if is_finalize or kind == "finalize":
        finish_names = frozenset(n for n in tool_names if n in ("finish_task", "mark_objective_complete"))
        if "finish_task" in tool_names:
            finish_names = frozenset(n for n in tool_names if n == "finish_task")
        if not finish_names:
            return None
        return build_agent_action_json_schema(
            finish_names,
            registry,
            simplify=simplify,
            require_final_report=mode_norm == "research",
        )

    if kind in ("search", "read", "explore"):
        read_names = frozenset(
            n for n in tool_names
            if n in registry
            and n not in ("finish_task", "mark_objective_complete")
        )
        if not read_names:
            return None
        max_items = 1 if kind == "search" and mode_norm == "research" else None
        return build_agent_action_json_schema(
            read_names,
            registry,
            simplify=simplify,
            max_tools_per_turn=max_items,
        )

    return None


def build_strict_schema_from_registry(
    available_tools: dict[str, Any],
    *,
    simplify: bool = False,
) -> dict[str, Any]:
    """Drop-in replacement for legacy build_strict_schema (dict output)."""
    return build_agent_action_json_schema(
        frozenset(available_tools.keys()),
        available_tools,
        simplify=simplify,
    )


class FlatToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class FlatAgentAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reasoning: str = Field(
        ...,
        description="Brief operational summary (1-3 sentences); no markdown.",
    )
    tools: list[FlatToolCall] = Field(default_factory=list)
    final_report: str | None = None



class MilestoneModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    label: str = ""
    success_criteria: str = ""
    status: str = "pending"


class PlanStepModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = "pending"
    description: str = ""
    step_kind: str = "read"
    max_iterations: int = 4
    target_mode: str | None = None
    delegate_objective: str | None = None


class TaskPlanModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = "in_progress"
    current_step_index: int = 0
    steps: list[PlanStepModel] = Field(default_factory=list)
    user_goal: str = ""
    approach_summary: str = ""
    milestones: list[MilestoneModel] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    plan_version: int = 1
    approval_status: str = "draft"
    micro_plan: bool = False


class WalkthroughModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    what_we_did: list[str] = Field(default_factory=list)
    why_those_choices: str = ""
    how_to_verify: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)


class ReflectTurnModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str = Field(..., description="Brief reflection; no tools this turn.")


class CapabilityCallModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Capability ID, e.g. cap.research.gather_web_sources@v1")
    arguments: dict[str, Any] = Field(default_factory=dict)


class CapabilityActionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reasoning: str = Field(
        ...,
        description="Brief operational summary (1-3 sentences); no markdown.",
    )
    capabilities: list[CapabilityCallModel] = Field(default_factory=list)
    final_report: str | None = None


_capability_action_schema_cache: dict[tuple[frozenset[str], bool, int, bool], dict[str, Any]] = {}
_capability_action_model_cache: dict[frozenset[str], type[BaseModel]] = {}


def build_capability_action_json_schema(
    capability_ids: frozenset[str] | set[str] | list[str],
    *,
    simplify: bool = False,
    max_capabilities_per_turn: int = 1,
    require_final_report: bool = False,
) -> dict[str, Any]:
    """Ollama-compatible JSON Schema for capability act turns (3.5 contract).

    Flat ``id`` enum + freeform ``arguments`` — per-capability Pydantic models
    validate args inside ``run_capability``. Do not embed per-cap input trees
    (anyOf/const) in the Ollama format schema.
    """
    ids = frozenset(str(x).strip() for x in capability_ids if str(x).strip())
    cache_key = (ids, require_final_report, max(1, max_capabilities_per_turn), simplify)
    if cache_key in _capability_action_schema_cache:
        return _capability_action_schema_cache[cache_key]

    names = sorted(ids)
    id_prop: dict[str, Any] = {"type": "string"}
    if names:
        id_prop["enum"] = names
    if not simplify:
        id_prop["description"] = "Capability ID from the allowed list."

    reasoning_prop: dict[str, Any] = {"type": "string"}
    if not simplify:
        reasoning_prop["description"] = "Brief operational summary; no markdown."

    args_prop: dict[str, Any] = {
        "type": "object",
        "additionalProperties": True,
    }
    if not simplify:
        args_prop["description"] = "Capability arguments (validated in Python)."

    caps_prop: dict[str, Any] = {
        "type": "array",
        "maxItems": max(1, max_capabilities_per_turn),
        "items": {
            "type": "object",
            "properties": {
                "id": id_prop,
                "arguments": args_prop,
            },
            "required": ["id", "arguments"],
            "additionalProperties": False,
        },
    }

    required = ["reasoning", "capabilities"]
    if require_final_report:
        required.append("final_report")

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "reasoning": reasoning_prop,
            "final_report": {"type": "string"},
            "capabilities": caps_prop,
        },
        "required": required,
        "additionalProperties": False,
    }
    _capability_action_schema_cache[cache_key] = schema
    return schema


def get_capability_action_model(
    capability_ids: frozenset[str] | None = None,
) -> type[BaseModel]:
    """Flat capability action model; per-capability argument validation at execution."""
    _ = capability_ids
    return CapabilityActionModel


def capability_action_to_dict(instance: BaseModel) -> dict[str, Any]:
    data = instance.model_dump(mode="python", exclude_none=True)
    caps = data.get("capabilities") or []
    normalized: list[dict] = []
    for item in caps:
        if isinstance(item, dict):
            cap_id = item.get("id") or item.get("capability_id")
            args = item.get("arguments") or {}
            if cap_id:
                normalized.append({"id": cap_id, "arguments": args})
    data["capabilities"] = normalized
    return data


def get_task_plan_schema(*, simplify: bool = False) -> dict[str, Any]:
    schema = TaskPlanModel.model_json_schema(mode="serialization")
    return _prepare_ollama_schema(schema, simplify=simplify)


def get_reflect_schema(*, simplify: bool = False) -> dict[str, Any]:
    schema = ReflectTurnModel.model_json_schema(mode="serialization")
    return _prepare_ollama_schema(schema, simplify=simplify)


def get_explore_action_schema(
    available_tools: dict[str, Any],
    *,
    simplify: bool = False,
) -> dict[str, Any]:
    """Explore subagent uses the same agent-action shape as the main loop."""
    return build_agent_action_json_schema(
        frozenset(available_tools.keys()),
        available_tools,
        simplify=simplify,
    )


def _prepare_ollama_schema(schema: dict[str, Any], *, simplify: bool) -> dict[str, Any]:
    """Strip $defs for inline strict mode; optionally drop descriptions."""
    out = _inline_defs(schema)
    out = _enforce_additional_properties_false(out)
    if simplify:
        out = _strip_descriptions(out)
    if out.get("type") != "object":
        out = {"type": "object", **out}
    return out


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.pop("$defs", None) or schema.pop("definitions", None)
    if not defs:
        return schema

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                key = ref.split("/")[-1]
                if key in defs:
                    return resolve(dict(defs[key]))
                return node
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


def _enforce_additional_properties_false(node: Any) -> Any:
    if isinstance(node, dict):
        if node.get("type") == "object" and "additionalProperties" not in node:
            node = {**node, "additionalProperties": False}
        return {k: _enforce_additional_properties_false(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_enforce_additional_properties_false(x) for x in node]
    return node


def _strip_descriptions(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: _strip_descriptions(v)
            for k, v in node.items()
            if k != "description"
        }
    if isinstance(node, list):
        return [_strip_descriptions(x) for x in node]
    return node


def shrink_schema_for_retry(schema: dict[str, Any]) -> dict[str, Any]:
    """Smaller schema for Ollama HTTP 400 / strict rejections."""
    return _strip_descriptions(_enforce_additional_properties_false(dict(schema)))


def schema_byte_size(schema: dict[str, Any]) -> int:
    return len(json.dumps(schema, separators=(",", ":")).encode("utf-8"))


def get_agent_action_schema(
    tool_names: frozenset[str] | set[str],
    registry: dict[str, Any] | None = None,
    *,
    simplify: bool = False,
) -> dict[str, Any]:
    names = frozenset(tool_names)
    if registry is None:
        from agent.core import get_executable_tools

        registry = get_executable_tools()
    return build_agent_action_json_schema(names, registry, simplify=simplify)


def get_agent_action_model(
    tool_names: frozenset[str] | set[str],
    registry: dict[str, Any] | None = None,
) -> type[BaseModel]:
    names = frozenset(tool_names)
    if registry is None:
        from agent.core import get_executable_tools

        registry = get_executable_tools()
    return build_agent_action_model(names, registry)


def validate_tool_arguments_pydantic(
    tool_calls: list[dict],
    registry: dict[str, Any] | None = None,
) -> tuple[bool, str, list[dict]]:
    """
    Validate and coerce each tool's arguments via Pydantic.
    Returns (ok, error_message, normalized_tool_calls).
    """
    if registry is None:
        from agent.core import get_executable_tools

        registry = get_executable_tools()

    normalized: list[dict] = []
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            return False, f"tools[{i}] must be an object", tool_calls
        name = tc.get("name")
        if not name or name not in registry:
            normalized.append(tc)
            continue
        args = tc.get("arguments")
        if not isinstance(args, dict):
            return False, f"tools[{i}].arguments must be an object", tool_calls
        try:
            func = registry[name]["func"]
            args = sanitize_tool_arguments(args, func, tool_name=name)
            args_model = build_arguments_model(name, func)
            validated = args_model.model_validate(args)
            normalized.append({
                "name": name,
                "arguments": validated.model_dump(mode="python", exclude_none=True),
            })
        except Exception as e:
            return False, f"tools[{i}] ({name}) argument validation: {e}", tool_calls
    return True, "", normalized
