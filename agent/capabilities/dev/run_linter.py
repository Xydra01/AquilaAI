"""Run linter on a project file."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class RunLinterInput(BaseModel):
    file_path: str = Field(..., min_length=1)


def _run_linter(ctx: CapabilityContext, inp: RunLinterInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    return from_tool_text(canvas.run_linter_tool(inp.file_path))


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.run_linter@v1",
        version="v1",
        title="Run linter",
        description="Lint a project file via the code canvas linter.",
        input_model=RunLinterInput,
        handler=_run_linter,
        tier="B",
        modes=frozenset({"code"}),
    )
)
