"""Apply an edit: replace_lines / patch / replace_symbol."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class EditApplyInput(BaseModel):
    action: Literal["replace_lines", "apply_unified_patch", "replace_symbol", "apply_patch"] = (
        "replace_lines"
    )
    file_path: str = Field(..., min_length=1)
    start_line: int = Field(1, ge=1)
    end_line: int = Field(1, ge=1)
    new_content: str = Field("", description="Replacement body for replace_lines.")
    patch_text: str = Field("", description="Unified diff for patch actions.")
    symbol_name: str = Field("", description="Symbol for replace_symbol.")
    new_code: str = Field("", description="New symbol body for replace_symbol.")


def _run_edit_apply(ctx: CapabilityContext, inp: EditApplyInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    action = (inp.action or "replace_lines").strip().lower()
    if action == "replace_lines":
        result = from_tool_text(
            canvas.replace_lines(
                inp.file_path,
                inp.start_line,
                max(inp.end_line, inp.start_line),
                inp.new_content,
            )
        )
    elif action in ("apply_unified_patch", "apply_patch"):
        if not (inp.patch_text or "").strip():
            return CapabilityResult.failure("missing_patch", "patch_text required.")
        result = from_tool_text(canvas.apply_unified_patch(inp.file_path, inp.patch_text))
    elif action == "replace_symbol":
        if not (inp.symbol_name or "").strip():
            return CapabilityResult.failure("missing_symbol", "symbol_name required.")
        result = from_tool_text(
            canvas.replace_symbol(inp.file_path, inp.symbol_name, inp.new_code)
        )
    else:
        return CapabilityResult.failure("bad_action", f"Unknown edit action: {action}")
    if result.ok:
        result.data["file_path"] = inp.file_path
    return result


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.edit_apply@v1",
        version="v1",
        title="Apply code edit",
        description="Replace lines, apply a unified patch, or replace a symbol in the buffer.",
        input_model=EditApplyInput,
        handler=_run_edit_apply,
        tier="B",
        modes=frozenset({"code"}),
    )
)
