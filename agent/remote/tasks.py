"""Job-style task runner for the Remote Companion.

Wraps ``Agent.run_unified_task`` (Research, persona builds, syllabus builds)
which streams a cumulative ledger via ``ui_callback`` and writes a plan JSON +
deliverable rather than token chunks. Frames pumped to the WebSocket:

- ``{"type": "ledger", "text"}`` — throttled cumulative ledger snapshots,
- ``{"type": "plan", "state"}``  — the plan JSON at ``resolve_ledger_path``,
- ``{"type": "done", "message"}`` — the final deliverable string,
- ``{"type": "busy", "message"}`` — another generation already running,
- ``{"type": "error", "error"}``  — failure detail.

Only one generation runs at a time (shared ``OllamaClient``); we reuse the chat
lock from :mod:`session` as the busy guard.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, AsyncIterator, Optional

from . import session

_SENTINEL = object()

# Modes the runner accepts. Research is the headline use; builds are reused by
# the Character/Learn workspaces.
TASK_MODES = {"research", "character_build", "learn_syllabus_build", "task", "autonomous"}


def _read_plan(mode: str, task_name: str) -> Optional[dict]:
    try:
        from agent.gui import resolve_ledger_path

        path = resolve_ledger_path(mode, task_name)
        if path and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


async def stream_task(
    *,
    instance_id: Optional[str],
    task_name: str,
    prompt: str,
    mode: str = "research",
    text_chunks: Optional[list] = None,
    image_payloads: Optional[list] = None,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
    cancel_event: Optional[threading.Event] = None,
) -> AsyncIterator[dict]:
    """Yield task frames for one ``run_unified_task`` execution."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    cancel_event = cancel_event or threading.Event()

    mode = (mode or "research").lower()
    if mode not in TASK_MODES:
        mode = "research"

    # Busy guard: one generation at a time across chat + tasks.
    if session._chat_lock.locked():
        yield {"type": "busy", "message": "Another generation is already running."}
        return

    last_emit = {"t": 0.0}

    def ui_callback(text: str) -> None:
        now = time.monotonic()
        # Throttle cumulative snapshots so we don't flood the socket.
        if now - last_emit["t"] < 0.3:
            return
        last_emit["t"] = now
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "ledger", "text": text})

    def thinking_callback(think_text: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait, {"type": "thinking", "delta": think_text}
        )

    def producer() -> None:
        import main as brain

        try:
            session._apply_instance_model(instance_id)
            agent = brain.get_agent(instance_id)
            result = agent.run_unified_task(
                task_name,
                prompt,
                mode,
                ui_callback=ui_callback,
                cancel_check=lambda: cancel_event.is_set(),
                text_chunks=text_chunks,
                image_payloads=image_payloads,
                persona_research_lore=persona_research_lore,
                learn_syllabus_web=learn_syllabus_web,
                generation_source="remote",
                thinking_callback=thinking_callback,
            )
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "done", "message": str(result or "")}
            )
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "error": str(exc)}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    async with session._chat_lock:
        fut = loop.run_in_executor(None, producer)
        try:
            while True:
                frame = await queue.get()
                if frame is _SENTINEL:
                    break
                if frame.get("type") == "ledger":
                    yield frame
                    plan = _read_plan(mode, task_name)
                    if plan is not None:
                        yield {"type": "plan", "state": plan}
                elif frame.get("type") == "done":
                    # Emit one last plan snapshot, then the terminal done frame.
                    plan = _read_plan(mode, task_name)
                    if plan is not None:
                        yield {"type": "plan", "state": plan}
                    yield frame
                else:
                    yield frame
        finally:
            await fut
