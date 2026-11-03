"""Base types for Aquila capability modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from pydantic import BaseModel


@dataclass
class CapabilityContext:
    """Runtime context passed to every capability invocation."""

    client: Any = None
    memory: Any = None
    task_id: str = ""
    instance_id: str = ""
    mode: str = "research"
    offline: bool = False
    journal_text: str = ""
    human_research_notes: str = ""
    attachments: list[str] = field(default_factory=list)
    attachment_text_chunks: list[str] = field(default_factory=list)
    user_request: str = ""
    cancel_check: Callable[[], bool] | None = None
    source_registry: Any = None
    url_registry: Any = None
    step_index: int | None = None
    step_kind: str = ""
    writing_brief: dict | None = None


class CapabilityError(Exception):
    """Structured failure from a capability."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class CapabilityResult:
    """Outcome of a capability run."""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def success(cls, summary: str = "", **data: Any) -> CapabilityResult:
        return cls(ok=True, summary=summary, data=dict(data))

    @classmethod
    def failure(cls, code: str, message: str) -> CapabilityResult:
        return cls(
            ok=False,
            error_code=code,
            error_message=message,
            summary=message,
        )


def format_capability_result_for_llm(
    result: CapabilityResult,
    *,
    payload_cap: int = 12_000,
) -> str:
    """Build the text the act loop shows the model after a capability run.

    Summaries alone are not enough (e.g. recon stores the tree in
    ``data['tool_result']``). Include that payload so the model can act on it.
    """
    text = result.summary or (result.error_message or "No output.")
    data = dict(result.data or {})
    payload = data.pop("tool_result", None)
    if payload is not None:
        body = str(payload)
        summary_s = (result.summary or "").strip()
        if body.strip() and body.strip() != summary_s:
            if len(body) > payload_cap:
                omitted = len(body) - payload_cap
                body = body[:payload_cap] + f"\n...[truncated {omitted} bytes]"
            text = f"{text}\n\n{body}"
    extras: list[str] = []
    for key, value in sorted(data.items()):
        if isinstance(value, (bool, int, float)):
            extras.append(f"{key}={value}")
        elif isinstance(value, str) and len(value) <= 200:
            extras.append(f"{key}={value!r}")
        else:
            extras.append(key)
    if extras:
        text += f"\n(data: {', '.join(extras)})"
    return text


CapabilityHandler = Callable[[CapabilityContext, BaseModel], CapabilityResult]
