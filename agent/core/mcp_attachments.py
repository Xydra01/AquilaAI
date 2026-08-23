"""Load local files for MCP-hosted mode runs."""
from __future__ import annotations

import json
from pathlib import Path


_LOCAL_RESEARCH_HINT = (
    "LOCAL RESEARCH: Use read_file, read_file_region, search_files, and grep on repo paths. "
    "Do not use web_search unless the objective requires external URLs. "
    "Attached file content is in the <attached_files> block below."
)


def parse_file_paths_arg(file_paths: str) -> list[str]:
    raw = (file_paths or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(p).strip() for p in parsed if str(p).strip()]
        except json.JSONDecodeError:
            pass
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def resolve_paths(paths: list[str], *, repo_root: Path | None = None) -> list[str]:
    from agent.storage import agent_data_path

    root = repo_root or agent_data_path()
    resolved: list[str] = []
    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            path = root / p
        if path.is_file():
            resolved.append(str(path.resolve()))
    return resolved


def load_attachments_for_mcp(
    file_paths: str,
    *,
    prefer_local: bool = False,
    context: str = "",
) -> tuple[list[str], list, str]:
    """Return (text_chunks, image_payloads, augmented_context)."""
    from agent.coding import process_local_attachments

    paths = resolve_paths(parse_file_paths_arg(file_paths))
    text_chunks: list = []
    image_payloads: list = []
    if paths:
        text_chunks, image_payloads = process_local_attachments(paths)
    ctx = (context or "").strip()
    if prefer_local or paths:
        hint = _LOCAL_RESEARCH_HINT
        if paths:
            hint += f" Files attached: {', '.join(Path(p).name for p in paths)}."
        ctx = f"{hint}\n\n{ctx}" if ctx else hint
    return text_chunks, image_payloads, ctx
