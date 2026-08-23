"""Research note capabilities."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.tool_library.agent_tools import read_all_research_notes, save_research_note


class AppendNoteInput(BaseModel):
    content: str = Field(..., min_length=1)
    task_name: str | None = None


class ReadNotesInput(BaseModel):
    max_chars: int | None = Field(None, ge=1000)
    tail: bool = True
    task_name: str | None = None


def _resolve_task(ctx: CapabilityContext, task_name: str | None) -> str:
    if task_name and task_name.strip():
        return task_name.strip()
    return ctx.task_id or ""


def _run_append_note(ctx: CapabilityContext, inp: AppendNoteInput) -> CapabilityResult:
    task = _resolve_task(ctx, inp.task_name)
    result = save_research_note(inp.content, task_name=task or None)
    ok = not str(result).startswith("❌")
    if ok:
        return CapabilityResult.success(result, tool_result=result)
    return CapabilityResult.failure("dedup_or_save", result)


def _run_read_notes(ctx: CapabilityContext, inp: ReadNotesInput) -> CapabilityResult:
    task = _resolve_task(ctx, inp.task_name)
    text = read_all_research_notes(
        max_chars=inp.max_chars,
        tail=inp.tail,
        task_name=task or None,
    )
    char_count = len(text or "")
    return CapabilityResult.success(
        f"Loaded {char_count} chars of notes.",
        text=text,
        char_count=char_count,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.append_note@v1",
        version="v1",
        title="Append research note",
        description="Save scratchpad note with dedup and chunking.",
        input_model=AppendNoteInput,
        handler=_run_append_note,
        tier="A",
    )
)

register_capability(
    CapabilitySpec(
        capability_id="cap.research.read_notes@v1",
        version="v1",
        title="Read research notes",
        description="Load notes with byte/char cap.",
        input_model=ReadNotesInput,
        handler=_run_read_notes,
        tier="A",
    )
)
