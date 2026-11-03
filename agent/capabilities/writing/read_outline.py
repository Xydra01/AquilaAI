"""Read the current draft outline."""
from __future__ import annotations

from pydantic import BaseModel

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.capabilities.writing._common import from_tool_text
from agent.tool_library.writing_tools import read_outline


class ReadOutlineInput(BaseModel):
    pass


def _run_read(ctx: CapabilityContext, inp: ReadOutlineInput) -> CapabilityResult:
    text = read_outline()
    if str(text).startswith("❌"):
        return from_tool_text(text)
    return CapabilityResult.success(text, tool_result=text, outline=text)


register_capability(
    CapabilitySpec(
        capability_id="cap.writing.read_outline@v1",
        version="v1",
        title="Read outline",
        description="Read current document section headers from the draft buffer.",
        input_model=ReadOutlineInput,
        handler=_run_read,
        tier="B",
        modes=frozenset({"writing"}),
    )
)
