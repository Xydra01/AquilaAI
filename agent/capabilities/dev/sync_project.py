"""Sync code canvas buffer to disk."""
from __future__ import annotations

from pydantic import BaseModel

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class SyncProjectInput(BaseModel):
    pass


def _run_sync(ctx: CapabilityContext, inp: SyncProjectInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    return from_tool_text(canvas.sync_project_to_disk())


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.sync_project@v1",
        version="v1",
        title="Sync project to disk",
        description="Write buffer files under the project root and lint them.",
        input_model=SyncProjectInput,
        handler=_run_sync,
        tier="B",
        modes=frozenset({"code"}),
    )
)
