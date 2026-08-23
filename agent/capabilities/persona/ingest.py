"""Ingest user/attachment sources into persona scratchpad."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability


class IngestSourcesInput(BaseModel):
    topic: str = Field("", description="Persona / topic label")
    content: str = Field(
        "",
        description="Optional explicit ingest text; otherwise uses attachments/journal/request",
    )


def _compose_ingest_body(ctx: CapabilityContext, inp: IngestSourcesInput) -> str:
    parts: list[str] = []
    if inp.content and inp.content.strip():
        parts.append(inp.content.strip())
    topic = (inp.topic or ctx.user_request or "").strip()
    if topic:
        parts.append(f"## Persona request\n{topic}")
    if ctx.journal_text and str(ctx.journal_text).strip():
        parts.append(f"## User notes\n{str(ctx.journal_text).strip()}")
    for i, chunk in enumerate(ctx.attachment_text_chunks or []):
        text = str(chunk).strip()
        if text:
            parts.append(f"## Attachment {i + 1}\n{text[:12000]}")
    if not parts and ctx.user_request:
        parts.append(str(ctx.user_request).strip())
    return "\n\n".join(parts).strip()


def _run_ingest(ctx: CapabilityContext, inp: IngestSourcesInput) -> CapabilityResult:
    body = _compose_ingest_body(ctx, inp)
    if not body:
        return CapabilityResult.failure(
            "empty",
            "No persona source material to ingest (request, notes, or attachments).",
        )
    return run_capability(
        "cap.research.append_note@v1",
        ctx,
        {"content": body},
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.persona.ingest_sources@v1",
        version="v1",
        title="Ingest persona sources",
        description="Save user description and attachments into the research scratchpad.",
        input_model=IngestSourcesInput,
        handler=_run_ingest,
        tier="A",
        modes=frozenset({"character_build"}),
    )
)
