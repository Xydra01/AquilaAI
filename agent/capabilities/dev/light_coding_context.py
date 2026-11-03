"""Light coding context for Chat Mode."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability


class LightCodingContextInput(BaseModel):
    repo_root: str = Field(..., min_length=1)
    user_input: str = Field("")
    force_refresh: bool = False


def _run_light_coding(ctx: CapabilityContext, inp: LightCodingContextInput) -> CapabilityResult:
    from agent.coding.light_coding import build_light_coding_context

    try:
        block, stats = build_light_coding_context(
            inp.repo_root,
            inp.user_input or ctx.user_request or "",
            force_refresh=inp.force_refresh,
        )
    except Exception as exc:
        return CapabilityResult.failure("light_coding_failed", str(exc))
    return CapabilityResult.success(
        f"Light coding context ({len(block or '')} chars).",
        context=block or "",
        stats=stats or {},
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.light_coding_context@v1",
        version="v1",
        title="Light coding context",
        description="Chat-mode budgeted repo context block for light coding.",
        input_model=LightCodingContextInput,
        handler=_run_light_coding,
        tier="B",
        modes=frozenset({"code", "chat", "task"}),
    )
)
