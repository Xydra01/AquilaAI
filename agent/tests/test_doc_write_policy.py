import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from doc_write_policy import (
    DOC_MIN_CHARS_ARCHITECTURE,
    WRITE_PROJECT_MARKDOWN_MAX_CHARS,
    compact_read_code_outline_result,
    filter_stashable_reflect_tools,
    looks_incomplete_markdown,
    reflect_tools_message,
    validate_append_project_markdown_args,
    validate_write_project_markdown_args,
)


def _architecture_doc_body(prefix: str = "# Title\n\nShort doc.\n") -> str:
    """Pad to meet ARCHITECTURE.md minimum length (validator strips trailing whitespace)."""
    text = prefix
    line = "Additional architecture section detail.\n"
    while len(text.strip()) < DOC_MIN_CHARS_ARCHITECTURE:
        text += line
    return text
from main import validate_tool_arguments


def test_validate_rejects_stub_architecture():
    ok, err = validate_write_project_markdown_args(
        {"file_path": "ARCHITECTURE.md", "content": "# Title\n\n## Project Structure\n\n```\n\n"}
    )
    assert ok is False
    assert "characters" in err or "fence" in err


def test_looks_incomplete_detects_short_readme():
    assert looks_incomplete_markdown("# Hi\n", file_path="README.md") is not None


def test_validate_append_cap():
    ok, err = validate_append_project_markdown_args(
        {"file_path": "ARCHITECTURE.md", "content": "x" * 5000}
    )
    assert ok is False


def test_validate_write_content_max():
    ok, err = validate_write_project_markdown_args(
        {"file_path": "ARCHITECTURE.md", "content": "x" * (WRITE_PROJECT_MARKDOWN_MAX_CHARS + 1)}
    )
    assert ok is False
    assert "8000" in err


def test_validate_tool_arguments_rejects_huge_write():
    ok, err = validate_tool_arguments([
        {
            "name": "write_project_markdown",
            "arguments": {
                "file_path": "ARCHITECTURE.md",
                "content": "a" * 20_000,
            },
        }
    ])
    assert ok is False
    assert "write_project_markdown" in err


def test_compact_outline_shortens_manifest():
    full = (
        "Tool read_code_outline returned: PROJECT: demo | root: .\n"
        + "\n".join(f"  - backend/f{i}.py (10 lines)" for i in range(80))
    )
    compact = compact_read_code_outline_result(full)
    assert len(compact) < len(full)
    assert "compact summary" in compact
    assert "Files in buffer: 80" in compact


def test_stash_reflect_write_under_cap():
    stash, rejected = filter_stashable_reflect_tools([
        {
            "name": "write_project_markdown",
            "arguments": {
                "file_path": "ARCHITECTURE.md",
                "content": _architecture_doc_body(),
            },
        }
    ])
    assert len(stash) == 1
    assert len(rejected) == 0


def test_stash_rejects_oversized_write():
    stash, rejected = filter_stashable_reflect_tools([
        {
            "name": "write_project_markdown",
            "arguments": {
                "file_path": "ARCHITECTURE.md",
                "content": "z" * 20_000,
            },
        }
    ])
    assert len(stash) == 0
    assert len(rejected) == 1


def test_reflect_message_mentions_act_turn():
    msg = reflect_tools_message(
        [{"name": "write_project_markdown", "arguments": {}}],
        stashed=[{"name": "write_project_markdown", "arguments": {"file_path": "A.md", "content": "hi"}}],
    )
    assert "ignored on reflect" in msg
    assert "8000" in msg
    assert "auto-run" in msg
