"""Phase 1 code mode — direct filesystem tool loop."""
from __future__ import annotations

import inspect
import json
import os
import time
from typing import Any, Callable, Literal

from agent.core.code_session_metrics import CodeSessionMetrics, append_code_session_log
from agent.core.prompts import get_code_agent_prompt
from agent.policies.code_context import (
    build_project_context_block,
    maybe_auto_context_after_grep,
    tool_output_max_chars,
    truncate_text,
)
from agent.policies.code_tool_catalog import (
    build_code_agent_json_schema,
    get_active_code_agent_tools,
    get_code_tool_registry,
)
from agent.policies.context_manager import estimate_messages_tokens
from agent.policies.model_tiers import CodeSurface, check_code_model
from agent.storage.runtime_settings import active_ollama_config


def _max_turns() -> int:
    raw = os.getenv("AQUILA_CODE_MAX_TURNS", "16").strip()
    try:
        return max(4, min(32, int(raw)))
    except ValueError:
        return 16


def _project_context_block() -> tuple[str, dict]:
    block, meta = build_project_context_block()
    return block, meta


_CAP_TO_TOOL = {
    "cap.dev.create_file@v1": "write_file",
    "cap.dev.edit_apply@v1": "search_replace",
    "cap.dev.read_region@v1": "read_file",
    "cap.dev.recon@v1": "list_dir",
    "cap.dev.run_tests@v1": "run_command",
    "cap.dev.sync_project@v1": "",
}


def _normalize_tool_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    out = dict(args or {})
    if tool_name in ("write_file", "read_file", "search_replace", "list_dir"):
        if "path" not in out and out.get("file_path"):
            out["path"] = out.pop("file_path")
    if tool_name == "write_file" and "content" not in out and out.get("body"):
        out["content"] = out.pop("body")
    if tool_name == "read_file":
        if "start_line" not in out:
            sl = out.pop("start_line", None) or out.pop("start", None)
            if sl is not None:
                out["start_line"] = sl
        if "end_line" not in out:
            el = out.pop("end_line", None) or out.pop("end", None)
            if el is not None:
                out["end_line"] = el
    if tool_name == "run_command" and "command" not in out:
        if out.get("cmd"):
            out["command"] = out.pop("cmd")
        elif tool_name == "run_command" and not out.get("command"):
            out["command"] = "python -m pytest"
    return out


def _heal_tool_action(parsed: dict[str, Any]) -> dict[str, Any]:
    """Bridge legacy capability JSON and common arg aliases."""
    if not isinstance(parsed, dict):
        return {}
    tools = parsed.get("tools")
    if not tools and parsed.get("capabilities"):
        tools = []
        for cap in parsed.get("capabilities") or []:
            if not isinstance(cap, dict):
                continue
            raw_id = str(cap.get("id") or cap.get("name") or "").strip()
            mapped = _CAP_TO_TOOL.get(raw_id, raw_id.replace("cap.dev.", "").replace("@v1", ""))
            if mapped in ("create_file",):
                mapped = "write_file"
            if mapped in ("edit_apply",):
                mapped = "search_replace"
            if mapped in ("read_region",):
                mapped = "read_file"
            if mapped in ("recon",):
                mapped = "list_dir"
            if mapped in ("run_tests",):
                mapped = "run_command"
            if not mapped or mapped == "sync_project":
                continue
            args = dict(cap.get("arguments") or cap.get("args") or {})
            tools.append({"name": mapped, "arguments": _normalize_tool_arguments(mapped, args)})
        parsed = dict(parsed)
        parsed["tools"] = tools
    elif isinstance(tools, list):
        healed = []
        for call in tools:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or "").strip()
            args = _normalize_tool_arguments(name, dict(call.get("arguments") or call.get("args") or {}))
            healed.append({"name": name, "arguments": args})
        parsed = dict(parsed)
        parsed["tools"] = healed
    return parsed


def _parse_tool_turn(agent, raw: str, allowed: frozenset[str]) -> dict[str, Any]:
    from agent.core.main import parse_agent_response

    parsed = (
        parse_agent_response(
            raw,
            schema_kind="agent_action",
            tool_names=allowed,
            quiet=True,
        )
        or {}
    )
    return _heal_tool_action(parsed)


def _tool_path_key(tool_name: str, args: dict[str, Any]) -> str:
    path = str(args.get("path") or args.get("file_path") or "").strip().replace("\\", "/")
    return f"{tool_name}|{path}"


def _block_tool_path_repeat(tool_name: str, path: str, prior_attempts: int) -> str | None:
    if tool_name not in ("write_file", "search_replace"):
        return None
    norm = (path or "").strip().replace("\\", "/")
    if not norm or prior_attempts < 2:
        return None
    if tool_name == "write_file":
        return (
            f"❌ OS BLOCK: `write_file` on `{norm}` repeated {prior_attempts + 1} times. "
            "The file already exists. Use `read_file` to inspect it, `search_replace` for a "
            "small edit, or set `final_report` if the task is already done."
        )
    return (
        f"❌ OS BLOCK: `{tool_name}` on `{norm}` repeated {prior_attempts + 1} times. "
        "Read the file with read_file, then use a unique search_replace."
    )


def _execute_tool(
    tool_name: str,
    args: dict[str, Any],
    registry: dict[str, dict],
) -> str:
    entry = registry.get(tool_name)
    if not entry:
        return f"❌ OS BLOCK: unknown tool `{tool_name}`."
    func = entry["func"]
    sig = inspect.signature(func)
    valid = {k: v for k, v in args.items() if k in sig.parameters}
    try:
        return str(func(**valid))
    except Exception as exc:
        return f"❌ OS Error: {exc}"


def _emit_tool_log(agent, tool_name: str, *, start: bool, preview: str = "") -> None:
    logger = getattr(agent, "run_logger", None)
    if logger is None:
        return
    try:
        if start:
            logger.event("tool_start", tool_name=tool_name)
        else:
            logger.event("tool_end", tool_name=tool_name, result_preview=preview[:500])
    except Exception:
        pass


def run_tool_session(
    agent,
    *,
    user_request: str,
    task_name: str = "",
    ui_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    text_chunks: list | None = None,
    image_payloads: list | None = None,
    thinking_callback: Callable[[str], None] | None = None,
    surface: CodeSurface = "cli",
    strict_model: bool = False,
) -> str:
    """Run a code session: LLM ↔ filesystem tools until final_report or turn limit."""
    from agent.core.main import format_attachment_context

    model_check = check_code_model(surface=surface, strict=strict_model)
    if not model_check.ok:
        return model_check.message
    if model_check.warn and model_check.message and ui_callback:
        ui_callback(model_check.message + "\n")

    ollama_cfg = active_ollama_config()
    metrics = CodeSessionMetrics(
        model_id=model_check.model_id or str(ollama_cfg.get("model") or ""),
        engine=str(ollama_cfg.get("engine") or ""),
        task_name=task_name or "code",
    )
    started = time.monotonic()
    turn_count = 0

    allowed = get_active_code_agent_tools()
    registry = get_code_tool_registry()
    schema = build_code_agent_json_schema(allowed)

    project_block, snapshot_meta = _project_context_block()
    system = get_code_agent_prompt(allowed)
    system += f"\n\n--- PROJECT ---\n{project_block}\n--- END PROJECT ---"
    metrics.extra.update(snapshot_meta)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    attachment_block = format_attachment_context(text_chunks)
    user_text = (user_request or "").strip()
    if attachment_block:
        user_text = f"{user_text}{attachment_block}"

    if image_payloads:
        content_list: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for img_b64 in image_payloads:
            prefix = "data:image/jpeg;base64,"
            clean_b64 = img_b64.split(",", 1)[-1] if "," in img_b64 else img_b64
            content_list.append({
                "type": "image_url",
                "image_url": {"url": f"{prefix}{clean_b64}"},
            })
        messages.append({"role": "user", "content": content_list})
    else:
        messages.append({"role": "user", "content": user_text})

    ledger_parts: list[str] = [
        f"Code session: {task_name or 'code'}\n",
        f"Request: {user_request[:300]}\n",
    ]
    if model_check.warn and model_check.message:
        ledger_parts.append(model_check.message + "\n")
    if ui_callback:
        ui_callback("\n".join(ledger_parts))

    last_summary = ""
    completed = False
    tool_path_attempts: dict[str, int] = {}
    pending_auto_context = ""

    for turn in range(1, _max_turns() + 1):
        turn_count = turn
        if cancel_check and cancel_check():
            metrics.turns = turn_count
            metrics.wall_s = round(time.monotonic() - started, 2)
            metrics.completed = completed
            agent._last_code_session_metrics = metrics.to_dict()
            append_code_session_log(metrics, summary="cancelled")
            return "🛑 Code session cancelled."

        est = estimate_messages_tokens(messages)
        if pending_auto_context:
            messages.append({"role": "user", "content": pending_auto_context})
            pending_auto_context = ""

        result = agent.client.chat(
            messages,
            temperature=0.2,
            format=schema,
            stream=False,
            estimated_prompt_tokens=est,
            surface="act",
            force_think_disabled=True,
        )
        raw = ""
        thinking = ""
        if isinstance(result, dict):
            raw = str(result.get("message", {}).get("content", "") or "")
            thinking = str(result.get("message", {}).get("thinking", "") or "")
        else:
            raw = str(result or "")

        if thinking and thinking_callback:
            thinking_callback(thinking)
        if thinking:
            ledger_parts.append(f"\n💭 {thinking[:500]}\n")

        parsed = _parse_tool_turn(agent, raw, allowed)
        if not parsed:
            metrics.parse_failures += 1
            ledger_parts.append(f"\n⚠️ Turn {turn}: could not parse model response.\n")
            messages.append({"role": "assistant", "content": raw or "{}"})
            messages.append({
                "role": "user",
                "content": (
                    "Tool Outputs:\n❌ OS: Invalid JSON. Reply with reasoning + "
                    "one tool in `tools[]` (name + arguments), or final_report when done."
                ),
            })
            if ui_callback:
                ui_callback("\n".join(ledger_parts))
            continue

        reasoning = str(parsed.get("reasoning") or "").strip()
        final_report = str(parsed.get("final_report") or "").strip()
        tools = parsed.get("tools") or []
        if not isinstance(tools, list):
            tools = []

        messages.append({"role": "assistant", "content": json.dumps(parsed)})

        if reasoning:
            ledger_parts.append(f"\n**Turn {turn}** — {reasoning}\n")

        if not tools:
            if final_report:
                last_summary = final_report
                completed = True
                ledger_parts.append(f"\n✅ {final_report}\n")
                break
            ledger_parts.append(
                f"\n⚠️ Turn {turn}: no tools and no final_report. "
                "Call a tool to make progress, or set final_report when finished.\n"
            )
            messages.append({
                "role": "user",
                "content": (
                    "Tool Outputs:\n💡 Call a tool to make progress, or set "
                    "`final_report` when the task is complete."
                ),
            })
            if ui_callback:
                ui_callback("\n".join(ledger_parts))
            continue

        call = tools[0] if tools else {}
        if not isinstance(call, dict):
            continue
        tool_name = str(call.get("name") or "").strip()
        args = dict(call.get("arguments") or call.get("args") or {})
        args = _normalize_tool_arguments(tool_name, args)

        if tool_name not in allowed:
            tool_out = (
                f"❌ OS BLOCK: `{tool_name}` is not allowed. "
                f"Use: {', '.join(sorted(allowed))}"
            )
        else:
            path_key = _tool_path_key(tool_name, args)
            path = str(args.get("path") or args.get("file_path") or "").strip()
            prior = 0
            if path:
                prior = tool_path_attempts.get(path_key, 0)
                tool_path_attempts[path_key] = prior + 1
            block = _block_tool_path_repeat(tool_name, path, prior)
            if block:
                if prior >= 2:
                    metrics.repeat_blocks += 1
                tool_out = block
            else:
                _emit_tool_log(agent, tool_name, start=True)
                tool_out = _execute_tool(tool_name, args, registry)
                _emit_tool_log(agent, tool_name, start=False, preview=tool_out)
                if tool_name == "semantic_search":
                    try:
                        from agent.tool_library.coding_tools import pop_last_index_meta

                        index_meta = pop_last_index_meta()
                        if index_meta:
                            metrics.extra.update(index_meta)
                    except Exception:
                        pass
                auto_ctx = maybe_auto_context_after_grep(tool_name, tool_out)
                if auto_ctx:
                    pending_auto_context = auto_ctx

        if str(tool_out).strip().startswith("❌"):
            metrics.capability_errors += 1

        tool_out = truncate_text(str(tool_out), tool_output_max_chars())
        ledger_parts.append(f"\nTool `{tool_name}`:\n{tool_out}\n")
        messages.append({"role": "user", "content": f"Tool Outputs:\n{tool_out}"})

        if ui_callback:
            ui_callback("\n".join(ledger_parts))

    else:
        ledger_parts.append(
            f"\n🛑 Stopped after {_max_turns()} turns (limit). "
            "Set final_report or continue in a new message.\n"
        )
        if ui_callback:
            ui_callback("\n".join(ledger_parts))

    metrics.turns = turn_count
    metrics.wall_s = round(time.monotonic() - started, 2)
    metrics.completed = completed
    agent._last_code_session_metrics = metrics.to_dict()
    append_code_session_log(metrics, summary=last_summary)

    summary = last_summary or "Code session finished."
    out = "\n".join(ledger_parts).strip()
    if summary and summary not in out:
        out = f"{out}\n\n✅ {summary}"
    return out
