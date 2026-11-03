"""Batch-create multiple buffer files in one capability call."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from agent.capabilities.base import CapabilityContext, CapabilityResult
from agent.capabilities.dev._common import from_tool_text
from agent.capabilities.registry import CapabilitySpec, register_capability

MAX_FILES = 5
MAX_LINES_PER_FILE = 80


class FileEntry(BaseModel):
    file_path: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class WriteFilesInput(BaseModel):
    files: list[FileEntry] = Field(..., min_length=1, max_length=MAX_FILES)

    @field_validator("files")
    @classmethod
    def _non_empty_files(cls, value: list[FileEntry]) -> list[FileEntry]:
        if not value:
            raise ValueError("files must contain at least one entry")
        return value


def _run_write_files(ctx: CapabilityContext, inp: WriteFilesInput) -> CapabilityResult:
    from agent.tool_library import code_canvas_tools as canvas

    written: list[str] = []
    errors: list[str] = []
    for entry in inp.files:
        line_count = len((entry.content or "").splitlines())
        if line_count > MAX_LINES_PER_FILE:
            errors.append(
                f"{entry.file_path}: {line_count} lines (max {MAX_LINES_PER_FILE})"
            )
            continue
        text = canvas.create_buffer_file(entry.file_path, entry.content)
        result = from_tool_text(text)
        if result.ok:
            written.append(entry.file_path)
        else:
            errors.append(f"{entry.file_path}: {result.summary or result.error_message}")
    if errors and not written:
        return CapabilityResult.failure("write_files_failed", "; ".join(errors))
    summary = f"Wrote {len(written)} file(s): {', '.join(written)}"
    if errors:
        summary += f" ({len(errors)} failed)"
    return CapabilityResult.success(
        summary=summary,
        files=written,
        failed=errors,
    )


register_capability(
    CapabilitySpec(
        capability_id="cap.dev.write_files@v1",
        version="v1",
        title="Batch write buffer files",
        description=(
            "Create or overwrite multiple files in the code canvas buffer in one call. "
            "Each entry needs file_path and content (max 80 lines per file)."
        ),
        input_model=WriteFilesInput,
        handler=_run_write_files,
        tier="B",
        modes=frozenset({"code"}),
    )
)
