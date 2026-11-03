"""Repair common LLM mistakes in capability act JSON before execution."""
from __future__ import annotations

from typing import Any


def _looks_like_cap_id(value: Any) -> bool:
    s = str(value or "").strip()
    return s.startswith("cap.") and "@" in s


def _infer_dev_cap_from_args(args: dict[str, Any]) -> str | None:
    """Guess the intended cap.dev.* id from argument shape."""
    if not isinstance(args, dict):
        return None
    if args.get("file_path") and args.get("content") is not None:
        return "cap.dev.create_file@v1"
    if args.get("old_string") is not None or args.get("new_string") is not None:
        return "cap.dev.edit_apply@v1"
    has_recon_keys = any(
        k in args for k in ("path", "tree_path", "directory", "max_depth", "outline")
    )
    has_setup_keys = any(
        k in args for k in ("project_name", "language_primary", "source_path", "action")
    )
    if has_recon_keys and not has_setup_keys:
        return "cap.dev.recon@v1"
    if has_setup_keys and not has_recon_keys:
        return "cap.dev.project_setup@v1"
    return None


def heal_capability_call(item: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one capability call; fix nested ``id`` + arg-shape mixups.

    Models often emit::

        {"id": "cap.dev.run_tests@v1",
         "arguments": {"id": "cap.dev.create_file@v1", "file_path": "...", "content": "..."}}

    Prefer the nested capability id (and drop it from arguments). When still
    ambiguous, infer from argument keys (file_path+content → create_file, etc.).
    """
    if not isinstance(item, dict):
        return None
    args = dict(item.get("arguments") or item.get("params") or item.get("args") or {})
    for key in ("file_path", "content", "path"):
        if key not in args and item.get(key) is not None:
            args[key] = item[key]
    if "file_path" not in args and args.get("path"):
        args["file_path"] = args.pop("path")
    outer = str(item.get("id") or item.get("capability_id") or "").strip()

    nested_raw = args.pop("id", None)
    if nested_raw is None:
        nested_raw = args.pop("capability_id", None)
    nested = str(nested_raw).strip() if nested_raw is not None else ""

    # Junk boolean sometimes emitted beside create_file args
    args.pop("create_file", None)

    cap_id = outer
    if _looks_like_cap_id(nested):
        cap_id = nested
    elif not cap_id and _looks_like_cap_id(nested):
        cap_id = nested

    inferred = _infer_dev_cap_from_args(args)
    if inferred:
        # Prefer shape when outer/nested disagree with payload (e.g. run_tests + file content)
        if not cap_id:
            cap_id = inferred
        elif cap_id == "cap.dev.edit_apply@v1" and inferred == "cap.dev.create_file@v1":
            cap_id = inferred
        elif cap_id != inferred and (
            (inferred == "cap.dev.create_file@v1" and args.get("file_path"))
            or (inferred == "cap.dev.edit_apply@v1")
            or (
                inferred == "cap.dev.recon@v1"
                and cap_id == "cap.dev.project_setup@v1"
                and not args.get("project_name")
            )
        ):
            cap_id = inferred

    if not cap_id:
        return None
    return {"id": cap_id, "arguments": args}


def heal_capability_calls(capabilities: list | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(capabilities, list):
        return out
    for item in capabilities:
        healed = heal_capability_call(item) if isinstance(item, dict) else None
        if healed:
            out.append(healed)
    return out
