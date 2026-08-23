"""Finalize persona after initialization.md is written."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.tool_library.persona_tools import finalize_persona


class FinalizePersonaInput(BaseModel):
    greeting: str = Field(..., min_length=1)
    tagline: str = Field("")
    display_name: str = Field("")


def _run_finalize(ctx: CapabilityContext, inp: FinalizePersonaInput) -> CapabilityResult:
    result = finalize_persona(
        greeting=inp.greeting,
        tagline=inp.tagline,
        display_name=inp.display_name,
    )
    ok = str(result).startswith("✅")
    if ok:
        return CapabilityResult.success(result, tool_result=result)
    return CapabilityResult.failure("finalize_failed", result)


register_capability(
    CapabilitySpec(
        capability_id="cap.persona.finalize@v1",
        version="v1",
        title="Finalize persona",
        description="Save greeting/tagline and mark persona build complete.",
        input_model=FinalizePersonaInput,
        handler=_run_finalize,
        tier="B",
        modes=frozenset({"character_build"}),
    )
)
