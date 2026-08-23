"""Write syllabus.json from notes or provided JSON."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, model_validator

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability
from agent.tool_library.learn_tools import write_syllabus_file


def coerce_syllabus_content(arguments: dict[str, Any] | None) -> str | None:
    """Accept content string or syllabus-shaped dict args (nodes/title/…)."""
    args = dict(arguments or {})
    content = args.get("content")
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(args.get("nodes"), list):
        # Model put syllabus fields directly in arguments{}
        return json.dumps(args, ensure_ascii=False)
    for key in ("syllabus", "syllabus_json", "json", "body"):
        val = args.get(key)
        if isinstance(val, dict) and isinstance(val.get("nodes"), list):
            return json.dumps(val, ensure_ascii=False)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


class WriteSyllabusInput(BaseModel):
    content: str = Field(
        ...,
        min_length=2,
        description="Syllabus JSON string (nodes, mastery tiers).",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_content(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        coerced = coerce_syllabus_content(data)
        if coerced:
            return {"content": coerced}
        return data


def _run_write(ctx: CapabilityContext, inp: WriteSyllabusInput) -> CapabilityResult:
    result = write_syllabus_file(inp.content)
    ok = str(result).startswith("✅")
    if ok:
        return CapabilityResult.success(result, tool_result=result)
    return CapabilityResult.failure("write_failed", result)


register_capability(
    CapabilitySpec(
        capability_id="cap.learn.write_syllabus@v1",
        version="v1",
        title="Write syllabus",
        description=(
            "Validate and write syllabus.json. Pass arguments.content as a JSON string "
            "(or pass nodes/title fields directly). Do not invent other capability IDs."
        ),
        input_model=WriteSyllabusInput,
        handler=_run_write,
        tier="B",
        modes=frozenset({"learn_syllabus_build"}),
    )
)
