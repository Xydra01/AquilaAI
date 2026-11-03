"""Project setup: init / import / attach repo."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability


class ProjectSetupInput(BaseModel):
    action: Literal["init", "import", "attach"] = Field(
        "init",
        description="init_code_project | import_codebase | attach_existing_repo",
    )
    project_name: str = Field("", description="Display / slug name for the project.")
    root: str = Field("", description="Optional root path for init.")
    source_path: str = Field("", description="Source directory for import/attach.")
    language_primary: str = Field("python")
    workspace_mode: str = Field("sandbox", description="sandbox or in_place for import.")
    load_content: str = Field("false", description="Load file contents on import.")


def _run_project_setup(ctx: CapabilityContext, inp: ProjectSetupInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    action = (inp.action or "init").strip().lower()
    if action == "init":
        name = (inp.project_name or "").strip()
        # Never use the full user goal as the folder name (models omit project_name
        # and topic/user_request gets stuffed in — produces huge useless roots).
        if (
            not name
            or len(name) > 40
            or name.count(" ") > 4
            or name.lower().startswith("build ")
        ):
            name = (ctx.task_id or "project").strip()[:64] or "project"
        else:
            name = name[:64]
        return from_tool_text(
            canvas.init_code_project(name, root=inp.root, language_primary=inp.language_primary)
        )
    if action == "import":
        if not (inp.source_path or "").strip():
            return CapabilityResult.failure("missing_source", "source_path required for import.")
        return from_tool_text(
            canvas.import_codebase(
                inp.source_path,
                project_name=inp.project_name,
                workspace_mode=inp.workspace_mode,
                load_content=inp.load_content,
            )
        )
    if action == "attach":
        if not (inp.source_path or "").strip():
            return CapabilityResult.failure("missing_source", "source_path required for attach.")
        return from_tool_text(
            canvas.attach_existing_repo(inp.source_path, project_name=inp.project_name)
        )
    return CapabilityResult.failure("bad_action", f"Unknown action: {action}")


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.project_setup@v1",
        version="v1",
        title="Code project setup",
        description="Init, import, or attach a code project into the canvas buffer.",
        input_model=ProjectSetupInput,
        handler=_run_project_setup,
        tier="B",
        modes=frozenset({"code"}),
    )
)
