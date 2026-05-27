"""Dual-format run logging: truncated human .log + structured .jsonl."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from rich.console import Console

from workspace_paths import agent_data_path
from rich.text import Text

_HUMAN_TOOL_CAP = 4000
_HUMAN_SCRAPE_PREVIEW = 300
_JSONL_PREVIEW = 500


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _truncate(text: str, cap: int) -> tuple[str, bool, int]:
    if not text:
        return "", False, 0
    n = len(text)
    if n <= cap:
        return text, False, n
    return text[:cap] + f"\n...[truncated {n - cap} bytes]", True, n


def _ascii_safe_markup(text: str) -> str:
    """Fallback when the terminal cannot encode Unicode (Windows cp1252)."""
    try:
        return Text.from_markup(str(text)).plain
    except Exception:
        raw = str(text)
        return raw.encode("ascii", errors="replace").decode("ascii")


class RunLogger:
    """Rich console + per-task human log + optional JSONL event stream."""

    def __init__(self):
        self.console = Console()
        self.current_task: str | None = None
        self.log_filename: str | None = None
        self.jsonl_filename: str | None = None
        self.instance_id: str = "default"
        self.mode: str = ""
        self._jsonl_enabled = _env_bool("AQUILA_LOG_JSON", True)
        self._full_tools = _env_bool("AQUILA_LOG_FULL_TOOLS", False)

    def set_task(
        self,
        task_name: str,
        *,
        instance_id: str = "default",
        mode: str = "",
    ) -> None:
        self.current_task = task_name
        self.instance_id = instance_id or "default"
        self.mode = mode or ""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = agent_data_path("Agent-Logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        base = logs_dir / f"{task_name}_{timestamp}"
        self.log_filename = str(base.with_suffix(".log"))
        self.jsonl_filename = str(base.with_suffix(".jsonl")) if self._jsonl_enabled else None
        friendly_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        banner = (
            f"\n\n{'=' * 60}\n"
            f"NEW EXECUTION SESSION: {friendly_time}\n"
            f"task={task_name} instance={self.instance_id} mode={self.mode}\n"
            f"{'=' * 60}\n"
        )
        if self.log_filename:
            with open(self.log_filename, "a", encoding="utf-8") as f:
                f.write(banner)
        self.event(
            "session_start",
            task=task_name,
            instance_id=self.instance_id,
            mode=self.mode,
        )

    def _emit_console(self, message: str, **kwargs) -> None:
        try:
            self.console.print(message, **kwargs)
        except UnicodeEncodeError:
            self.console.print(_ascii_safe_markup(message), **kwargs)

    def print(self, message: str, **kwargs) -> None:
        self._emit_console(message, **kwargs)
        if self.log_filename:
            try:
                clean_text = Text.from_markup(str(message)).plain
            except Exception:
                clean_text = str(message)
            with open(self.log_filename, "a", encoding="utf-8") as f:
                f.write(clean_text + "\n")

    def event(self, event_type: str, **fields: Any) -> None:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        body = fields.pop("body", None)
        truncated = False
        original_bytes = 0

        if body is not None:
            original_bytes = len(str(body))
            if self._full_tools:
                fields["body"] = body
            else:
                preview, truncated, _ = _truncate(str(body), _JSONL_PREVIEW)
                fields["body_preview"] = preview
                fields["body_sha8"] = hashlib.sha256(
                    str(body).encode("utf-8", errors="replace")
                ).hexdigest()[:8]

        record = {
            "ts": ts,
            "event": event_type,
            "task": self.current_task,
            "instance_id": self.instance_id,
            "mode": self.mode,
            **fields,
        }
        if truncated:
            record["truncated"] = True
            record["original_bytes"] = original_bytes

        if self.jsonl_filename:
            Path(self.jsonl_filename).parent.mkdir(parents=True, exist_ok=True)
            with open(self.jsonl_filename, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        self._console_summary(event_type, record)

    def _console_summary(self, event_type: str, record: dict) -> None:
        if event_type == "llm_response":
            dur = record.get("duration_ms")
            est = record.get("est_tokens")
            rt = record.get("read_timeout_s")
            parts = [f"[dim]llm_response"]
            if dur is not None:
                parts.append(f"{dur / 1000:.1f}s")
            if est is not None:
                parts.append(f"est={est}")
            if rt is not None:
                parts.append(f"timeout={rt}s")
            parts.append("[/dim]")
            self._emit_console(" ".join(parts))
        elif event_type == "tool_end":
            name = record.get("tool_name", "?")
            qual = record.get("page_quality")
            extra = f" quality={qual}" if qual else ""
            self._emit_console(f"[dim]tool_end {name}{extra}[/dim]")
        elif event_type in ("os_warning", "scrape_budget_exhausted", "context_compress"):
            msg = record.get("message", event_type)
            self._emit_console(f"[yellow]{msg}[/yellow]")

    def log_agent_turn(
        self,
        step_index: int,
        total_steps: int,
        step_kind: str,
        episode: int,
        loop_tick: int,
        turn_type: str,
        content: str = "",
        *,
        est_tokens: int | None = None,
        read_timeout_s: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        header = (
            f"--- Step {step_index + 1}/{total_steps} ({step_kind}) · "
            f"Episode {episode} · {turn_type} turn {loop_tick} ---"
        )
        human_body, trunc, orig = _truncate(content or "", _HUMAN_TOOL_CAP * 2)
        if self.log_filename and content:
            with open(self.log_filename, "a", encoding="utf-8") as f:
                f.write(f"\n{header}\n{human_body}\n")
        self.event(
            "llm_response",
            iteration=loop_tick,
            phase=turn_type,
            step_index=step_index,
            episode=episode,
            step_kind=step_kind,
            est_tokens=est_tokens,
            read_timeout_s=read_timeout_s,
            duration_ms=duration_ms,
            body=content,
            truncated_human=trunc,
            original_bytes=orig,
        )

    def log_iteration(
        self,
        iteration: int,
        content: str,
        *,
        phase: str = "",
        est_tokens: int | None = None,
        read_timeout_s: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        self.log_agent_turn(
            0,
            1,
            phase or "act",
            iteration,
            iteration,
            phase or "llm",
            content,
            est_tokens=est_tokens,
            read_timeout_s=read_timeout_s,
            duration_ms=duration_ms,
        )

    def log_tool_execution(self, tool_name: str, args: dict, result: str, **extra: Any) -> None:
        cap = _HUMAN_TOOL_CAP
        human_result, trunc, orig = _truncate(result or "", cap)
        if self.log_filename:
            with open(self.log_filename, "a", encoding="utf-8") as f:
                f.write(
                    f"\n[TOOL: {tool_name}]\nARGS: {args}\nRESULT:\n{human_result}\n"
                )
        preview, _, _ = _truncate(result or "", _HUMAN_SCRAPE_PREVIEW)
        self.event(
            "tool_end",
            tool_name=tool_name,
            arguments=args,
            body=result,
            result_preview=preview,
            truncated=trunc,
            original_bytes=orig,
            **extra,
        )

    def log_tool_start(self, tool_name: str, args: dict, **extra: Any) -> None:
        self.event("tool_start", tool_name=tool_name, arguments=args, **extra)
