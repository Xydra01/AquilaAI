"""Active task ID for scratchpad-bound tools (OS-injected, not model-supplied)."""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Final, Iterator

_active_task_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "aquila_active_task_id", default=None
)

# Tools whose scratchpad / deliverable rows are always keyed to the running task.
SCRATCHPAD_BOUND_TOOLS: Final[frozenset[str]] = frozenset({
    "save_research_note",
    "read_all_research_notes",
    "summarize_sources",
    "checkpoint_step",
    "save_task_deliverable",
})


class TaskContextError(RuntimeError):
    """Scratchpad tool called outside a task loop without a resolvable task id."""


def set_active_task_id(task_id: str | None) -> contextvars.Token:
    """Bind the current loop's task id (ledger / plan filename stem)."""
    return _active_task_id.set((task_id or "").strip() or None)


def reset_active_task_id(token: contextvars.Token) -> None:
    _active_task_id.reset(token)


def get_active_task_id() -> str | None:
    return _active_task_id.get()


def resolve_task_id(model_task_name: str | None = None) -> str:
    """
    Return the task id for scratchpad I/O.

    The active loop task always wins over any model-supplied task_name.
    """
    active = get_active_task_id()
    if active:
        return active
    if model_task_name and str(model_task_name).strip():
        return str(model_task_name).strip()
    raise TaskContextError(
        "No active task_id — scratchpad tools require a running Aquila task loop."
    )


def inject_scratchpad_task_id(tool_name: str, arguments: dict) -> dict:
    """
    Force scratchpad-bound tools to use the active task id.

    Model-provided task_name values are ignored when an active task is set.
    """
    if tool_name not in SCRATCHPAD_BOUND_TOOLS:
        return arguments
    args = dict(arguments or {})
    active = get_active_task_id()
    if not active:
        return args
    requested = args.get("task_name")
    if requested and str(requested).strip() != active:
        args["_task_name_ignored"] = str(requested)
    args["task_name"] = active
    return args


def omit_task_name_from_schema(tool_name: str, param_name: str) -> bool:
    """Hide task_name from strict JSON schema — OS injects it at execution."""
    return tool_name in SCRATCHPAD_BOUND_TOOLS and param_name == "task_name"


@contextmanager
def active_task(task_id: str) -> Iterator[None]:
    """Bind scratchpad tools to task_id for the duration of a block."""
    token = set_active_task_id(task_id)
    try:
        yield
    finally:
        reset_active_task_id(token)
