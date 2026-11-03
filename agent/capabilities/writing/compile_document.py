"""Compile the draft buffer to a markdown file."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.capabilities.writing._common import from_tool_text, slug_filename, title_from_context
from agent.tool_library.writing_tools import compile_final_document


class CompileDocumentInput(BaseModel):
    file_name: str = Field("", description="Output basename without .md.")


def _run_compile(ctx: CapabilityContext, inp: CompileDocumentInput) -> CapabilityResult:
    name = (inp.file_name or "").strip() or slug_filename(title_from_context(ctx))
    return from_tool_text(compile_final_document(name))


register_capability(
    CapabilitySpec(
        capability_id="cap.writing.compile_document@v1",
        version="v1",
        title="Compile document",
        description="Flush the draft buffer to Agent-Drafts/{file_name}.md.",
        input_model=CompileDocumentInput,
        handler=_run_compile,
        tier="B",
        modes=frozenset({"writing"}),
    )
)
