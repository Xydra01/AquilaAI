"""Recon: directory tree + code outline (+ optional grep)."""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class ReconInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    include_tree: bool = Field(True, description="Call get_directory_tree when available.")
    include_outline: bool = Field(True, description="Call read_code_outline.")
    grep_pattern: str = Field("", description="Optional pattern for grep_repo.")
    tree_path: str = Field(
        ".",
        description="Path for directory tree.",
        validation_alias=AliasChoices("tree_path", "path"),
    )
    max_depth: int = Field(3, ge=1, le=10, description="Max directory tree depth.")


def _run_recon(ctx: CapabilityContext, inp: ReconInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    tree_path = inp.tree_path or "."
    try:
        from agent.policies.recon_policy import normalize_code_tool_path

        tree_path, _note = normalize_code_tool_path(tree_path)
    except Exception:
        pass

    parts: list[str] = []
    if inp.include_tree:
        try:
            from agent.core.tools import get_directory_tree

            tree = get_directory_tree(tree_path, max_depth=int(inp.max_depth or 3))
            parts.append(str(tree))
        except Exception as exc:
            parts.append(f"⚠️ Tree skipped: {exc}")
    if inp.include_outline:
        outline = canvas.read_code_outline()
        parts.append(str(outline))
        if str(outline).startswith("❌"):
            return CapabilityResult.failure("recon_failed", "\n\n".join(parts))
    if (inp.grep_pattern or "").strip():
        try:
            from agent.tool_library.grep_tools import grep_repo

            parts.append(str(grep_repo(inp.grep_pattern.strip())))
        except Exception as exc:
            parts.append(f"⚠️ Grep skipped: {exc}")
    summary = "Recon complete."
    if parts:
        summary = f"Recon ({len(parts)} part(s))."
    return CapabilityResult.success(summary, tool_result="\n\n".join(parts))


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.recon@v1",
        version="v1",
        title="Code recon",
        description="Directory tree + code outline (optional grep) for explore/read steps.",
        input_model=ReconInput,
        handler=_run_recon,
        tier="B",
        modes=frozenset({"code"}),
    )
)
