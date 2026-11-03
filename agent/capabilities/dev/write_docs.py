"""Write or append project markdown documentation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class WriteDocsInput(BaseModel):
    action: Literal["write", "append"] = "write"
    file_path: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


def _run_write_docs(ctx: CapabilityContext, inp: WriteDocsInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    if inp.action == "append":
        return from_tool_text(canvas.append_project_markdown(inp.file_path, inp.content))
    return from_tool_text(canvas.write_project_markdown(inp.file_path, inp.content))


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.write_docs@v1",
        version="v1",
        title="Write project docs",
        description="Write or append markdown under the code project.",
        input_model=WriteDocsInput,
        handler=_run_write_docs,
        tier="B",
        modes=frozenset({"code"}),
    )
)
