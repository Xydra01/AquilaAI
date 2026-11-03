"""Read a file region from the code canvas / disk."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class ReadRegionInput(BaseModel):
    file_path: str = Field(..., min_length=1)
    start_line: int = Field(1, ge=1)
    end_line: int = Field(80, ge=1)


def _run_read_region(ctx: CapabilityContext, inp: ReadRegionInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    end = max(inp.end_line, inp.start_line)
    return from_tool_text(
        canvas.read_file_region(inp.file_path, inp.start_line, end)
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.read_region@v1",
        version="v1",
        title="Read file region",
        description="Read a line range from a buffer or project file.",
        input_model=ReadRegionInput,
        handler=_run_read_region,
        tier="B",
        modes=frozenset({"code"}),
    )
)
