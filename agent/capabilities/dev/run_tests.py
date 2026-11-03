"""Run pytest on the active code project."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class RunTestsInput(BaseModel):
    target: str = Field("", description="Optional pytest target path(s).")


def _run_tests(ctx: CapabilityContext, inp: RunTestsInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    result = canvas.run_pytest(inp.target or "")
    text = str(result or "")
    low = text.lower()
    tests_green = ("passed" in low or "0 failed" in low) and "failed" not in low.split("passed")[0][-40:]
    if "failed" in low and "0 failed" not in low:
        tests_green = False
    cap = from_tool_text(text)
    if cap.ok:
        cap.data["tests_green"] = tests_green
    return cap


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.run_tests@v1",
        version="v1",
        title="Run pytest",
        description="Sync dirty buffers if needed and run pytest on project targets.",
        input_model=RunTestsInput,
        handler=_run_tests,
        tier="B",
        modes=frozenset({"code"}),
    )
)
