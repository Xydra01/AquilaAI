"""Finalize course after syllabus is written."""
from __future__ import annotations

from pydantic import BaseModel

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.tool_library.learn_tools import finalize_course


class FinalizeCourseInput(BaseModel):
    pass


def _run_finalize(ctx: CapabilityContext, inp: FinalizeCourseInput) -> CapabilityResult:
    result = finalize_course()
    ok = str(result).startswith("✅")
    if ok:
        return CapabilityResult.success(result, tool_result=result)
    return CapabilityResult.failure("finalize_failed", result)


register_capability(
    CapabilitySpec(
        capability_id="cap.learn.finalize_course@v1",
        version="v1",
        title="Finalize course",
        description="Mark syllabus and course active after build.",
        input_model=FinalizeCourseInput,
        handler=_run_finalize,
        tier="B",
        modes=frozenset({"learn_syllabus_build"}),
    )
)
