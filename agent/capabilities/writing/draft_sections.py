"""Append or overwrite a draft section."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability
from agent.capabilities.writing._common import from_tool_text, title_from_context
from agent.tool_library.writing_tools import write_section


class DraftSectionsInput(BaseModel):
    section_header: str = Field(
        ...,
        min_length=1,
        description=(
            "Plain section title only (e.g. '1. Executive Summary'). "
            "Do NOT include markdown # markers — compile adds ## automatically."
        ),
    )
    content: str = Field(
        ...,
        min_length=1,
        description=(
            "Markdown body for the section only. Do NOT start with the section title "
            "as a # / ## heading — that duplicates the compiled heading."
        ),
    )
    title: str = Field("", description="Used only if the draft buffer is missing.")
    synopsis: str = Field("", description="Used only if the draft buffer is missing.")
    include_outline: bool = Field(
        False,
        description="If true, prepend read_outline after a successful write.",
    )


def _run_draft(ctx: CapabilityContext, inp: DraftSectionsInput) -> CapabilityResult:
    from agent.tool_library import writing_tools
    from agent.functions.writing_brief import WritingBrief

    brief = WritingBrief.from_plan_dict(getattr(ctx, "writing_brief", None))
    synopsis = inp.synopsis or ctx.user_request or ""
    if brief:
        synopsis = f"{synopsis}\n\nWriting brief: {brief.milestone_summary()}"

    if not writing_tools.ACTIVE_DRAFT_FILE.exists():
        init_result = run_capability(
            "cap.writing.init_document@v1",
            ctx,
            {
                "title": title_from_context(ctx, inp.title),
                "synopsis": synopsis,
            },
        )
        if not init_result.ok:
            return init_result
    result = from_tool_text(write_section(inp.section_header, inp.content))
    if result.ok and inp.include_outline:
        outline = run_capability("cap.writing.read_outline@v1", ctx, {})
        if outline.ok:
            result.summary = f"{result.summary}\n{outline.summary}"
    return result


register_capability(
    CapabilitySpec(
        capability_id="cap.writing.draft_sections@v1",
        version="v1",
        title="Draft sections",
        description=(
            "Write or overwrite one grouped section. Initializes the document if needed. "
            "section_header is a plain title; content is body only (no duplicate # title). "
            "Group related sub-headers in a single call."
        ),
        input_model=DraftSectionsInput,
        handler=_run_draft,
        tier="B",
        modes=frozenset({"writing"}),
    )
)
