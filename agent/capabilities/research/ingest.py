"""Offline ingest: attachments + journal → notes."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.research.research_journal import format_journal_context
from agent.tool_library.agent_tools import save_research_note


class IngestOfflineInput(BaseModel):
    topic: str = Field("", description="Research topic for note headers")
    include_journal: bool = True
    include_attachments: bool = True


def _run_ingest_offline(ctx: CapabilityContext, inp: IngestOfflineInput) -> CapabilityResult:
    parts: list[str] = []
    topic = (inp.topic or ctx.user_request or "Research topic").strip()[:200]

    if inp.include_journal:
        journal = (ctx.journal_text or ctx.human_research_notes or "").strip()
        if journal:
            parts.append(format_journal_context(journal).strip())

    if inp.include_attachments:
        if ctx.attachments:
            from agent.coding import process_local_attachments

            text_chunks, _images = process_local_attachments(ctx.attachments)
            for i, chunk in enumerate(text_chunks, start=1):
                label = getattr(chunk, "label", None) or f"attachment_{i}"
                body = getattr(chunk, "text", str(chunk))
                parts.append(f"--- Attachment: {label} ---\n{body}")
        elif ctx.attachment_text_chunks:
            for i, chunk in enumerate(ctx.attachment_text_chunks, start=1):
                body = str(chunk).strip()
                if body:
                    parts.append(f"--- Attachment chunk {i} ---\n{body}")

    if not parts:
        return CapabilityResult.failure(
            "no_offline_sources",
            "No journal text or attachments available to ingest.",
        )

    combined = f"# Offline sources for: {topic}\n\n" + "\n\n".join(parts)
    result = save_research_note(combined, task_name=ctx.task_id or None)
    if str(result).startswith("❌"):
        return CapabilityResult.failure("save_failed", result)
    return CapabilityResult.success(
        f"Ingested {len(parts)} offline source block(s).",
        tool_result=result,
        blocks=len(parts),
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.ingest_offline@v1",
        version="v1",
        title="Ingest offline sources",
        description="Attachments + human journal → initial notes.",
        input_model=IngestOfflineInput,
        handler=_run_ingest_offline,
        tier="B",
    )
)
