"""Compile report markdown from notes + bibliography."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability
from agent.research import pick_best_deliverable_body
from agent.research import append_bibliography_to_report


class CompileReportInput(BaseModel):
    max_chars: int = Field(24000, ge=4000)
    prefer_existing_draft: bool = True


def _run_compile(ctx: CapabilityContext, inp: CompileReportInput) -> CapabilityResult:
    read_result = run_capability(
        "cap.research.read_notes@v1",
        ctx,
        {"max_chars": inp.max_chars, "tail": True},
    )
    if not read_result.ok:
        return read_result
    notes = str(read_result.data.get("text") or "")
    body = pick_best_deliverable_body(notes) if inp.prefer_existing_draft else ""
    if not body.strip():
        body = notes.strip()
    if not body or len(body) < 200:
        return CapabilityResult.failure("thin_report", "Insufficient note content for report.")

    registry = ctx.source_registry
    report = append_bibliography_to_report(body, registry, mode="research")
    return CapabilityResult.success(
        f"Compiled report ({len(report)} chars).",
        body=report,
        bytes=len(report.encode("utf-8")),
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.research.compile_report@v1",
        version="v1",
        title="Compile report",
        description="Build final markdown from notes + bibliography.",
        input_model=CompileReportInput,
        handler=_run_compile,
        tier="B",
    )
)
