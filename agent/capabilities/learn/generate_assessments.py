"""Generate assessments for syllabus nodes during build."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.tool_library.learn_tools import generate_assessment


class GenerateAssessmentsInput(BaseModel):
    node_id: str = Field(..., min_length=1)
    target_tier: int = Field(1, ge=1, le=5)
    questions_json: str = Field(..., min_length=2)
    passing_score: float = Field(70.0, ge=0.0, le=100.0)


def _run_generate(ctx: CapabilityContext, inp: GenerateAssessmentsInput) -> CapabilityResult:
    result = generate_assessment(
        node_id=inp.node_id,
        target_tier=inp.target_tier,
        questions_json=inp.questions_json,
        passing_score=inp.passing_score,
    )
    ok = str(result).startswith("✅")
    if ok:
        return CapabilityResult.success(result, tool_result=result)
    return CapabilityResult.failure("generate_failed", result)


register_capability(
    CapabilitySpec(
        capability_id="cap.learn.generate_assessments@v1",
        version="v1",
        title="Generate assessments",
        description="Create assessment JSON for a syllabus node during build.",
        input_model=GenerateAssessmentsInput,
        handler=_run_generate,
        tier="A",
        modes=frozenset({"learn_syllabus_build"}),
    )
)
