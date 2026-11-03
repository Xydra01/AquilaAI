"""Ingest user attachments into scratchpad for source-based writing."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability


class IngestWritingSourcesInput(BaseModel):
    topic: str = Field("", description="Document topic or title hint.")
    content: str = Field(
        "",
        description="Optional explicit source text; otherwise uses attachments and request.",
    )


def _compose_body(ctx: CapabilityContext, inp: IngestWritingSourcesInput) -> str:
    parts: list[str] = []
    if inp.content and inp.content.strip():
        parts.append(inp.content.strip())
    topic = (inp.topic or ctx.user_request or "").strip()
    if topic:
        parts.append(f"## Writing brief\n{topic}")
    for i, chunk in enumerate(ctx.attachment_text_chunks or []):
        text = str(chunk).strip()
        if text:
            parts.append(f"## Source attachment {i + 1}\n{text[:12000]}")
    if not parts and ctx.user_request:
        parts.append(str(ctx.user_request).strip())
    return "\n\n".join(parts).strip()


def _run_ingest(ctx: CapabilityContext, inp: IngestWritingSourcesInput) -> CapabilityResult:
    body = _compose_body(ctx, inp)
    if not body:
        return CapabilityResult.failure(
            "empty",
            "No source material to ingest (request, content, or attachments).",
        )
    return run_capability(
        "cap.research.append_note@v1",
        ctx,
        {"content": body},
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.writing.ingest_sources@v1",
        version="v1",
        title="Ingest writing sources",
        description="Save user brief and file attachments into scratchpad for drafting.",
        input_model=IngestWritingSourcesInput,
        handler=_run_ingest,
        tier="A",
        modes=frozenset({"writing"}),
    )
)
