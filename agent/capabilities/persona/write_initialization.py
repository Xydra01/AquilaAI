"""Write initialization.md from scratchpad notes."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability
from agent.tool_library.persona_tools import write_persona_file


class WriteInitializationInput(BaseModel):
    content: str = Field(
        "",
        description="Full initialization.md body. If empty, uses scratchpad notes.",
    )
    file_path: str = Field("initialization.md")


def _run_write(ctx: CapabilityContext, inp: WriteInitializationInput) -> CapabilityResult:
    content = (inp.content or "").strip()
    if not content:
        notes = run_capability("cap.research.read_notes@v1", ctx, {})
        if not notes.ok:
            return notes
        content = str((notes.data or {}).get("text") or "").strip()
    if not content:
        return CapabilityResult.failure(
            "empty",
            "No content for initialization.md — provide content or ingest notes first.",
        )
    result = write_persona_file(inp.file_path or "initialization.md", content)
    ok = str(result).startswith("✅")
    if ok:
        return CapabilityResult.success(result, tool_result=result)
    return CapabilityResult.failure("write_failed", result)


register_capability(
    CapabilitySpec(
        capability_id="cap.persona.write_initialization@v1",
        version="v1",
        title="Write persona initialization",
        description="Read notes if needed and write initialization.md via write_persona_file.",
        input_model=WriteInitializationInput,
        handler=_run_write,
        tier="B",
        modes=frozenset({"character_build"}),
    )
)
