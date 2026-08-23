"""Write Agent-Research deliverable and validate non-empty body."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability
from agent.core.main import normalize_report_markdown, save_task_deliverable


class FinalizeDeliverableInput(BaseModel):
    report_body: str = Field("", description="Markdown body; recovered from notes if empty")
    compile_if_missing: bool = True


def _run_finalize(ctx: CapabilityContext, inp: FinalizeDeliverableInput) -> CapabilityResult:
    body = normalize_report_markdown((inp.report_body or "").strip())

    if not body and inp.compile_if_missing:
        compile_result = run_capability(
            "cap.research.compile_report@v1",
            ctx,
            {},
        )
        if compile_result.ok:
            body = normalize_report_markdown(str(compile_result.data.get("body") or ""))

    registry = ctx.source_registry
    path = save_task_deliverable(
        ctx.task_id,
        "research",
        body,
        registry,
        memory=ctx.memory,
        instance_id=ctx.instance_id,
    )
    if not path:
        return CapabilityResult.failure(
            "empty_deliverable",
            "Could not write research deliverable — body empty or recovery failed.",
        )
    try:
        from pathlib import Path

        byte_count = Path(path).stat().st_size
    except OSError:
        byte_count = len(body.encode("utf-8"))
    source_count = len(registry.records) if registry is not None else 0
    offline_like = bool(
        ctx.offline
        or ctx.attachments
        or ctx.attachment_text_chunks
        or (ctx.journal_text or "").strip()
        or (ctx.human_research_notes or "").strip()
    )
    if source_count > 0:
        summary = (
            f"Report written with {source_count} web bibliography source(s) "
            f"({byte_count} bytes)."
        )
    elif offline_like:
        summary = (
            f"Report written ({byte_count} bytes) from offline/attachment notes "
            f"(no web bibliography entries — expected for offline research)."
        )
    else:
        summary = (
            f"Report written ({byte_count} bytes). "
            f"No web bibliography sources registered."
        )
    return CapabilityResult.success(
        summary,
        path=path,
        bytes=byte_count,
        web_bibliography_sources=source_count,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.finalize_deliverable@v1",
        version="v1",
        title="Finalize deliverable",
        description="Write Agent-Research/*.md with non-empty body.",
        input_model=FinalizeDeliverableInput,
        handler=_run_finalize,
        tier="B",
    )
)
