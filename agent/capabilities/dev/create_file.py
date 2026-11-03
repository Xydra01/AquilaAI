"""Create a buffer file (tests or new modules)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class CreateFileInput(BaseModel):
    file_path: str = Field(..., min_length=1, description="Path relative to project root.")
    content: str = Field(
        ...,
        min_length=1,
        description="Full file body text (required — do not omit).",
    )


def _run_create_file(ctx: CapabilityContext, inp: CreateFileInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    text = canvas.create_buffer_file(inp.file_path, inp.content)
    result = from_tool_text(text)
    if result.ok:
        result.data["file_path"] = inp.file_path
    return result


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.create_file@v1",
        version="v1",
        title="Create buffer file",
        description=(
            "Create or overwrite a file in the code canvas buffer. "
            "Requires file_path and content (full file body)."
        ),
        input_model=CreateFileInput,
        handler=_run_create_file,
        tier="B",
        modes=frozenset({"code"}),
    )
)
