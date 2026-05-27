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


def try_parse_json(text: str) -> dict | None:
    try:
        parsed = json.loads(text, strict=False)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    try:
        safe_str = text.replace("\n", "\\n")
        safe_str = (
            safe_str.replace("true", "True")
            .replace("false", "False")
            .replace("null", "None")
        )
        parsed = ast.literal_eval(safe_str)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def heal_json_text(clean_json: str) -> str:
    """Close open strings/brackets (legacy Aquila healer)."""
    healed = re.sub(r"[\}\]\s]+$", "", clean_json)
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
        allow_heal = (format_mode or "") not in _FORMAT_STRICT and (
            format_mode in _FORMAT_LOOSE or format_mode is None
        )

    clean = extract_json_text(response_text)
    data = try_parse_json(clean)

    if data is None and allow_heal:
        healed_text = heal_json_text(clean)
        data = try_parse_json(healed_text)
        if data is not None:
            meta["healed"] = True

    if data is None:
        return None, "Response was not valid JSON.", meta

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
        from run_logger import get_active_run_logger

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
