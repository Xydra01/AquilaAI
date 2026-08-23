"""
Parse and validate Ollama structured JSON with Pydantic (healer as last resort).
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FORMAT_STRICT = frozenset({"strict_schema", "json_schema"})
_FORMAT_LOOSE = frozenset({"json_object", "plain", None})


def extract_json_text(response_text: str) -> str:
    """Strip markdown fences and isolate outer JSON object."""
    text = (response_text or "").strip()
    bt = chr(96) * 3
    match = re.search(bt + r"(?:json)?\s*(\{.*?)" + bt, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def extract_first_complete_json(text: str) -> str:
    """Extract the first fully balanced JSON object {...} from text."""
    start_idx = text.find("{")
    if start_idx < 0:
        return text
    
    stack = []
    in_string = False
    escape = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if char == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if char == "{":
                stack.append(char)
            elif char == "}":
                if stack:
                    stack.pop()
                    if not stack:
                        return text[start_idx:i+1]
        
        if char == "\\":
            escape = not escape
        else:
            escape = False
            
    return text


def _fix_unescaped_newlines_in_strings(text: str) -> str:
    """Escape unescaped newlines that appear inside JSON string values."""
    result = []
    in_string = False
    escape = False
    for char in text:
        if char == '"' and not escape:
            in_string = not in_string
            result.append(char)
        elif char == '\n' and in_string:
            result.append('\\n')
        else:
            result.append(char)
            
        if char == "\\":
            escape = not escape
        else:
            escape = False
    return "".join(result)


def _escape_nested_quotes_in_json(text: str) -> str:
    """
    Escape unescaped double quotes and raw control characters (newlines/tabs)
    inside JSON string values.
    """
    pattern = r'("(?P<key>[a-zA-Z0-9_-]+)"\s*:\s*")(?P<val>.*?)"\s*(?=(?:,\s*"[a-zA-Z0-9_-]+"\s*:|\}|\s*\]))'

    def repl(match):
        prefix = match.group(1)
        val = match.group("val")
        escaped_val = ""
        escape = False
        for char in val:
            if char == '\\':
                escape = not escape
                escaped_val += char
            elif char == '"':
                if not escape:
                    escaped_val += '\\"'
                else:
                    escaped_val += char
                escape = False
            elif char == '\n':
                escaped_val += '\\n'
                escape = False
            elif char == '\t':
                escaped_val += '\\t'
                escape = False
            else:
                escaped_val += char
                escape = False
        return prefix + escaped_val + '"'

    return re.sub(pattern, repl, text, flags=re.DOTALL)


def try_parse_json(text: str) -> dict | None:
    try:
        parsed = json.loads(text, strict=False)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    repaired = text
    # Fix raw unescaped newlines inside string values first
    repaired = _fix_unescaped_newlines_in_strings(repaired)
    # Fix nested quotes and unescaped newlines/tabs inside string values
    repaired = _escape_nested_quotes_in_json(repaired)
    # Fix trailing comma before closing brace/bracket
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    
    if repaired != text:
        try:
            parsed = json.loads(repaired, strict=False)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
            
    # Try extracting first complete object if trailing garbage exists
    first_obj = extract_first_complete_json(repaired)
    if first_obj != repaired and first_obj.strip().endswith("}"):
        try:
            parsed = json.loads(first_obj, strict=False)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
            
    return None


def heal_json_text(clean_json: str) -> str:
    """Close open strings/brackets (legacy Aquila healer)."""
    # Strip only trailing whitespace, NOT valid closing brackets
    healed = clean_json.rstrip()
    # Remove a single trailing comma (common truncation artifact)
    if healed.endswith(","):
        healed = healed[:-1]
    
    stack: list[str] = []
    in_string = False
    escape = False

    for char in healed:
        if char == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if char in "{[":
                stack.append(char)
            elif char in "}]":
                if stack:
                    stack.pop()
        if char == "\\":
            escape = not escape
        else:
            escape = False

    if in_string:
        healed += '"'
    while stack:
        healed += "}" if stack.pop() == "{" else "]"
    return healed


def format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:6]:
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else str(exc)


def parse_structured_turn(
    response_text: str,
    model: type[T],
    *,
    format_mode: str | None = "strict_schema",
    allow_heal: bool | None = None,
) -> tuple[T | None, str, dict[str, Any]]:
    """
    Parse LLM output into a Pydantic model.

    Returns (instance, error_message, meta) where meta has keys:
    healed, format_mode, error_kind (json_decode|validation|empty|ok)
    """
    meta: dict[str, Any] = {
        "healed": False,
        "format_mode": format_mode or "strict_schema",
        "error_kind": "json_decode",
    }
    if allow_heal is None:
        allow_heal = (format_mode or "") not in _FORMAT_STRICT

    clean = extract_json_text(response_text)
    data = try_parse_json(clean)

    if data is None and allow_heal:
        healed_text = heal_json_text(clean)
        data = try_parse_json(healed_text)
        if data is not None:
            meta["healed"] = True

    if data is None:
        return None, "Response was not valid JSON.", meta

    if model.__name__ == "AgentAction":
        from .structured_schema import FlatAgentAction, build_arguments_model
        from agent.core import get_executable_tools

        try:
            flat_instance = FlatAgentAction.model_validate(data)
        except ValidationError as e:
            meta["error_kind"] = "validation"
            return None, f"Outer schema validation failed: {format_validation_error(e)}", meta

        registry = get_executable_tools()
        coerced_tools = []
        for i, tc in enumerate(flat_instance.tools):
            name = tc.name
            if name not in registry:
                coerced_tools.append(tc.model_dump())
                continue

            tool_fn = registry[name]["func"]
            args_model = build_arguments_model(name, tool_fn)
            try:
                validated_args = args_model.model_validate(tc.arguments)
                coerced_tools.append({
                    "name": name,
                    "arguments": validated_args.model_dump(mode="python")
                })
            except ValidationError as e:
                meta["error_kind"] = "validation"
                return None, f"Tool '{name}' arguments validation failed: {format_validation_error(e)}", meta

        data["tools"] = coerced_tools

    try:
        instance = model.model_validate(data)
        meta["error_kind"] = "ok"
        return instance, "", meta
    except ValidationError as e:
        meta["error_kind"] = "validation"
        return None, format_validation_error(e), meta


def agent_action_to_dict(instance: BaseModel) -> dict[str, Any]:
    """Serialize AgentAction model to legacy loop dict shape."""
    data = instance.model_dump(mode="python")
    tools = data.get("tools") or []
    out_tools: list[dict] = []
    for tc in tools:
        if isinstance(tc, dict):
            out_tools.append({
                "name": tc.get("name"),
                "arguments": tc.get("arguments") or {},
            })
        else:
            out_tools.append({
                "name": getattr(tc, "name", None),
                "arguments": getattr(tc, "arguments", {}),
            })
            if hasattr(out_tools[-1]["arguments"], "model_dump"):
                out_tools[-1]["arguments"] = out_tools[-1]["arguments"].model_dump(
                    mode="python"
                )
    return {
        "reasoning": data.get("reasoning", ""),
        "tools": out_tools,
        "final_report": data.get("final_report"),
    }


def log_structured_parse_event(
    console: Any,
    *,
    ok: bool,
    meta: dict[str, Any],
    error: str = "",
    tool_count: int = 0,
) -> None:
    try:
        from agent.core import get_active_run_logger

        logger = get_active_run_logger()
        if logger:
            logger.event(
                "structured_parse",
                ok=ok,
                healed=meta.get("healed", False),
                format_mode=meta.get("format_mode"),
                model_profile=meta.get("model_profile", ""),
                error_kind=meta.get("error_kind", ""),
                error=(error or "")[:300],
                tool_count=tool_count,
            )
    except Exception:
        pass
    if console and hasattr(console, "event") and not ok:
        console.event(
            "structured_parse",
            ok=ok,
            error_kind=meta.get("error_kind"),
            healed=meta.get("healed"),
        )
