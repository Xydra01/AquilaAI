"""Compile if needed and mark the writing deliverable complete."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.registry import CapabilitySpec, register_capability, run_capability
from agent.capabilities.writing._common import slug_filename, title_from_context
from agent.tool_library.writing_tools import ACTIVE_DRAFT_FILE, DRAFT_DIR


class FinalizeWritingInput(BaseModel):
    file_name: str = Field("", description="Output basename without .md if compile is needed.")
    compile_if_missing: bool = True


def _run_finalize(ctx: CapabilityContext, inp: FinalizeWritingInput) -> CapabilityResult:
    name = (inp.file_name or "").strip() or slug_filename(title_from_context(ctx))
    compiled = None
    if inp.compile_if_missing and ACTIVE_DRAFT_FILE.exists():
        compiled = run_capability(
            "cap.writing.compile_document@v1",
            ctx,
            {"file_name": name},
        )
        if not compiled.ok:
            return compiled
    path = DRAFT_DIR / f"{name}.md"
    if compiled and compiled.ok:
        return CapabilityResult.success(
            compiled.summary or f"Writing deliverable compiled to {path}.",
            path=str(path),
            tool_result=compiled.data.get("tool_result", compiled.summary),
        )
    if path.is_file():
        return CapabilityResult.success(
            f"Writing deliverable already on disk: {path}",
            path=str(path),
        )
    return CapabilityResult.failure(
        "empty_deliverable",
        "No active draft and no compiled markdown — draft sections first, then finalize.",
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.writing.finalize_deliverable@v1",
        version="v1",
        title="Finalize writing deliverable",
        description="Compile the draft if needed and complete the writing task.",
        input_model=FinalizeWritingInput,
        handler=_run_finalize,
        tier="B",
        modes=frozenset({"writing"}),
    )
)
