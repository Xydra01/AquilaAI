"""Ingest course materials into scratchpad."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability


class IngestCourseMaterialsInput(BaseModel):
    topic: str = Field("")
    content: str = Field("")


def _compose_body(ctx: CapabilityContext, inp: IngestCourseMaterialsInput) -> str:
    parts: list[str] = []
    if inp.content and inp.content.strip():
        parts.append(inp.content.strip())
    topic = (inp.topic or ctx.user_request or "").strip()
    if topic:
        parts.append(f"## Course topic\n{topic}")
    if ctx.journal_text and str(ctx.journal_text).strip():
        parts.append(f"## User notes\n{str(ctx.journal_text).strip()}")
    for i, chunk in enumerate(ctx.attachment_text_chunks or []):
        text = str(chunk).strip()
        if text:
            parts.append(f"## Material {i + 1}\n{text[:12000]}")
    if not parts and ctx.user_request:
        parts.append(str(ctx.user_request).strip())
    return "\n\n".join(parts).strip()


def _run_ingest(ctx: CapabilityContext, inp: IngestCourseMaterialsInput) -> CapabilityResult:
    body = _compose_body(ctx, inp)
    if not body:
        return CapabilityResult.failure(
            "empty",
            "No course materials to ingest.",
        )
    return run_capability(
        "cap.research.append_note@v1",
        ctx,
        {"content": body},
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.learn.ingest_course_materials@v1",
        version="v1",
        title="Ingest course materials",
        description="Save topic and attachments into the scratchpad for syllabus synthesis.",
        input_model=IngestCourseMaterialsInput,
        handler=_run_ingest,
        tier="A",
        modes=frozenset({"learn_syllabus_build"}),
    )
)
