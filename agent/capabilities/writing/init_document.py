"""Initialize the writing draft buffer."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.capabilities.writing._common import from_tool_text, title_from_context
from agent.tool_library.writing_tools import init_document


class InitDocumentInput(BaseModel):
    title: str = Field("", description="Document title.")
    synopsis: str = Field("", description="Short synopsis or outline intent.")


def _run_init(ctx: CapabilityContext, inp: InitDocumentInput) -> CapabilityResult:
    title = title_from_context(ctx, inp.title)
    synopsis = (inp.synopsis or ctx.user_request or "").strip()[:2000]
    return from_tool_text(init_document(title, synopsis))


register_capability(
    CapabilitySpec(
        capability_id="cap.writing.init_document@v1",
        version="v1",
        title="Initialize document",
        description="Create the living draft buffer (Agent-Drafts/active_draft_state.json).",
        input_model=InitDocumentInput,
        handler=_run_init,
        tier="B",
        modes=frozenset({"writing"}),
    )
)
