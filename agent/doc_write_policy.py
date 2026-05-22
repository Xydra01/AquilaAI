"""Guards for write_project_markdown and compact read_code_outline in the loop."""
from __future__ import annotations

import re

WRITE_PROJECT_MARKDOWN_MAX_CHARS = 8_000
WRITE_PROJECT_MARKDOWN_REJECT_CHARS = 12_288
# Per-call soft limit: strict JSON tool args often truncate above ~4k in one LLM turn.
WRITE_PROJECT_MARKDOWN_SOFT_CHARS = 4_000
APPEND_PROJECT_MARKDOWN_MAX_CHARS = 4_000
DOC_MIN_CHARS_ARCHITECTURE = 1_500
DOC_MIN_CHARS_README = 600

REFLECT_DISALLOWED_TOOLS = frozenset({
    "write_project_markdown",
    "write_file",
    "write_section",
    "compile_final_document",
})


def write_content_too_long(content: str, *, hard: bool = False) -> bool:
    limit = WRITE_PROJECT_MARKDOWN_REJECT_CHARS if hard else WRITE_PROJECT_MARKDOWN_MAX_CHARS
    return len((content or "")) > limit


def validate_append_project_markdown_args(args: dict) -> tuple[bool, str]:
    content = args.get("content", "")
    if not isinstance(content, str):
        return False, "content must be a string"
    if len((content or "")) > APPEND_PROJECT_MARKDOWN_MAX_CHARS:
        return (
            False,
            f"append content exceeds {APPEND_PROJECT_MARKDOWN_MAX_CHARS} characters per call.",
        )
    return True, ""


def validate_write_project_markdown_args(args: dict) -> tuple[bool, str]:
    """Return (ok, error_message). Rejects oversized content before tool execution."""
    content = args.get("content", "")
    if not isinstance(content, str):
        return False, "content must be a string"
    if write_content_too_long(content, hard=False):
        return (
            False,
            f"content exceeds {WRITE_PROJECT_MARKDOWN_MAX_CHARS} characters. "
            "Write a concise doc or split sections; structured headings, no repetition.",
        )
    incomplete = looks_incomplete_markdown(content, file_path=str(args.get("file_path", "")))
    if incomplete:
        return False, incomplete
    return True, ""


def looks_incomplete_markdown(content: str, *, file_path: str = "") -> str | None:
    """Detect truncated JSON tool output or unfinished structure sections."""
    text = (content or "").strip()
    lower = (file_path or "").lower()
    min_chars = DOC_MIN_CHARS_README if lower.endswith("readme.md") else DOC_MIN_CHARS_ARCHITECTURE
    if len(text) < min_chars:
        return (
            f"content is only {len(text)} characters (need at least {min_chars} for "
            f"{file_path or 'this file'}). Strict JSON often truncates large strings — "
            "write <=4000 chars per call or use append_project_markdown on the next turn."
        )
    if text.count("```") % 2 == 1:
        return "unclosed ``` fence — finish the block or omit the fence."
    if "## Project Structure" in text and "```" in text:
        tail = text.split("## Project Structure", 1)[-1]
        if "```" in tail and tail.count("```") < 2:
            return "Project Structure section has an unclosed tree fence."
    return None


def truncate_write_content(content: str) -> tuple[str, str | None]:
    """Safety net inside the tool: truncate to max with note."""
    text = (content or "").strip()
    if len(text) <= WRITE_PROJECT_MARKDOWN_MAX_CHARS:
        return text, None
    trimmed = text[: WRITE_PROJECT_MARKDOWN_MAX_CHARS].rstrip() + "\n\n[truncated by OS]"
    return (
        trimmed,
        f"Content truncated to {WRITE_PROJECT_MARKDOWN_MAX_CHARS} characters. "
        "Prefer shorter sections without repetition.",
    )


def compact_read_code_outline_result(full_result: str) -> str:
    """Shrink outline tool output stored in conversation history."""
    text = full_result or ""
    if "PROJECT:" not in text and "read_code_outline" not in text.lower():
        return text

    project_line = ""
    for line in text.splitlines():
        if line.strip().startswith("PROJECT:"):
            project_line = line.strip()
            break

    file_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and (
            ".py" in stripped
            or ".ts" in stripped
            or ".tsx" in stripped
            or ".js" in stripped
            or ".md" in stripped
        ):
            file_lines.append(stripped[:120])

    count = len(file_lines)
    sample = file_lines[:12]
    parts = [
        "Tool read_code_outline returned: [compact summary for context — full manifest was retrieved]",
    ]
    if project_line:
        parts.append(project_line)
    parts.append(f"Files in buffer: {count} (showing up to 12 paths)")
    parts.extend(sample)
    if count > len(sample):
        parts.append(f"... and {count - len(sample)} more files (use read_file_region for details)")
    return "\n".join(parts)


def filter_stashable_reflect_tools(tool_calls: list) -> tuple[list[dict], list[dict]]:
    """
    Split reflect tools into (stash_for_act, rejected).
    Only non-meta tools with valid write_project_markdown under size cap are stashed.
    """
    from main import normalize_tool_calls_list
    from tool_policy import META_TOOLS

    normalized = normalize_tool_calls_list(tool_calls)
    stash: list[dict] = []
    rejected: list[dict] = []

    for tc in normalized:
        if not isinstance(tc, dict):
            continue
        name = tc.get("name", "")
        if name in META_TOOLS:
            continue
        args = tc.get("arguments") or {}
        if name == "write_project_markdown":
            ok, err = validate_write_project_markdown_args(args)
            if not ok:
                rejected.append(tc)
                continue
            if not args.get("content", "").strip():
                rejected.append(tc)
                continue
        stash.append(tc)

    return stash, rejected


def reflect_tools_message(
    tool_calls: list,
    *,
    stashed: list[dict],
) -> str:
    lines = [
        "Tool Outputs:\n✅ Reflection recorded. Now output tool calls for your objective (act turn).",
    ]
    if not tool_calls:
        return "\n".join(lines)

    lines.append(
        "\n⚠️ OS: Tools ignored on reflect. Never put write_project_markdown or long "
        "document bodies in a reflect turn."
    )
    if any(tc.get("name") == "write_project_markdown" for tc in tool_calls if isinstance(tc, dict)):
        lines.append(
            f"Repeat write_project_markdown on the next act turn with content under "
            f"{WRITE_PROJECT_MARKDOWN_MAX_CHARS} characters."
        )
    elif tool_calls:
        lines.append("Repeat any needed tools on the next act turn.")

    if stashed:
        names = ", ".join(tc.get("name", "?") for tc in stashed)
        lines.append(f"OS will auto-run stashed tool(s) on the next act turn: {names}.")
    return "\n".join(lines)
