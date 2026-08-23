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


CapabilityHandler = Callable[[CapabilityContext, BaseModel], CapabilityResult]
