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


def build_arguments_model(tool_name: str, func: Any) -> type[BaseModel]:
    """Dynamic Pydantic model for one tool's arguments from its signature."""
    sig = inspect.signature(func)
    fields: dict[str, tuple[Any, Any]] = {}
    for param_name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        fields[param_name] = param_to_field(param)

    model_name = f"{_safe_model_name(tool_name)}Args"
    if not fields:
        return create_model(model_name, __config__=ConfigDict(extra="forbid"))
    return create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def build_tool_call_model(tool_name: str, func: Any) -> type[BaseModel]:
    """One discriminated tool call: fixed name + typed arguments model."""
    args_model = build_arguments_model(tool_name, func)
    return create_model(
        f"ToolCall_{_safe_model_name(tool_name)}",
        name=(Literal[tool_name], ...),
        arguments=(args_model, Field(...)),
        __config__=ConfigDict(extra="forbid"),
    )


def build_agent_action_model(
    tool_names: frozenset[str],
    registry: dict[str, Any],
) -> type[BaseModel]:
    """Dynamic AgentAction model with discriminated tool union."""
    tool_models: list[type[BaseModel]] = []
    for name in sorted(tool_names):
        if name not in registry:
            continue
        tool_models.append(build_tool_call_model(name, registry[name]["func"]))

    if not tool_models:
        tool_item_type: Any = dict
    elif len(tool_models) == 1:
        tool_item_type = tool_models[0]
    else:
        tool_item_type = Union[tuple(tool_models)]

    return create_model(
        "AgentAction",
        reasoning=(str, Field(..., description="Internal thoughts; no markdown.")),
        tools=(
            list[tool_item_type],  # type: ignore[valid-type]
            Field(default_factory=list),
        ),
        final_report=(str | None, Field(default=None)),
        __config__=ConfigDict(extra="forbid"),
    )


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
        prop = _annotation_to_json_type(
            param.annotation
            if param.annotation is not inspect.Parameter.empty
            else str
        )
        if tool_name in ("write_project_markdown", "append_project_markdown") and (
            param_name == "content"
        ):
            from doc_write_policy import (
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
                "additionalProperties": False,
            },
        },
        "required": ["name", "arguments"],
        "additionalProperties": False,
    }


def build_agent_action_json_schema(
    tool_names: frozenset[str],
    registry: dict[str, Any],
    *,
    simplify: bool = False,
) -> dict[str, Any]:
    """
    Ollama-compatible strict JSON Schema for agent turns.
    Keeps per-tool anyOf branches + name enum (tests and Heretic compatibility).
    """
    names = sorted(n for n in tool_names if n in registry)
    branches = [
        _tool_branch_json_schema(n, registry[n]["func"]) for n in names
    ]

    reasoning_prop: dict[str, Any] = {"type": "string"}
    if not simplify:
        reasoning_prop["description"] = "Your internal thoughts. Do not use markdown."

    return {
        "type": "object",
        "properties": {
            "reasoning": reasoning_prop,
            "final_report": {"type": "string"},
            "tools": {
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
            },
        },
        "required": ["reasoning", "tools"],
        "additionalProperties": False,
    }


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


class PlanStepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "pending"
    description: str = ""
    step_kind: str = "read"
    max_iterations: int = 4


class TaskPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "in_progress"
    current_step_index: int = 0
    steps: list[PlanStepModel] = Field(default_factory=list)


class ReflectTurnModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: str = Field(..., description="Brief reflection; no tools this turn.")


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
        from main import get_executable_tools

        registry = get_executable_tools()
    return build_agent_action_json_schema(names, registry, simplify=simplify)


def get_agent_action_model(
    tool_names: frozenset[str] | set[str],
    registry: dict[str, Any] | None = None,
) -> type[BaseModel]:
    names = frozenset(tool_names)
    if registry is None:
        from main import get_executable_tools

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
        from main import get_executable_tools

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
            args_model = build_arguments_model(name, registry[name]["func"])
            validated = args_model.model_validate(args)
            normalized.append({
                "name": name,
                "arguments": validated.model_dump(mode="python"),
            })
        except Exception as e:
            return False, f"tools[{i}] ({name}) argument validation: {e}", tool_calls
    return True, "", normalized
