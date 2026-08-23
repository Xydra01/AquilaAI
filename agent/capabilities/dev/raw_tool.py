"""Debug escape hatch: invoke a single raw tool by name."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability


class RawToolInput(BaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)


def _run_raw_tool(ctx: CapabilityContext, inp: RawToolInput) -> CapabilityResult:
    from agent.core.main import get_executable_tools
    from agent.core import ToolExecutor

    registry = get_executable_tools()
    name = inp.tool_name.strip()
    if name not in registry:
        return CapabilityResult.failure("unknown_tool", f"Tool not found: {name}")
    executor = ToolExecutor()
    result = executor.execute([{"name": name, "arguments": inp.arguments or {}}])
    text = result[0] if result else "No output."
    ok = not str(text).startswith("❌")
    if ok:
        return CapabilityResult.success(f"Ran {name}.", tool_result=text)
    return CapabilityResult.failure("tool_error", str(text))


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.raw_tool@v1",
        version="v1",
        title="Raw tool (debug)",
        description="Escape hatch: single tool by name (debug only).",
        input_model=RawToolInput,
        handler=_run_raw_tool,
        tier="D",
        modes=frozenset({"research", "code", "task"}),
    )
)
