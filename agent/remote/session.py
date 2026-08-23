"""Bridge between the async FastAPI server and Aquila's blocking chat brain.

All agents share a single module-level ``OllamaClient`` whose ``model_name`` is
mutated per instance (see ``Agent.__init__``). That makes concurrent generations
with different models unsafe, so v1 serializes every chat turn with one global
lock. The blocking chunk generator from ``client.chat(...)`` is pumped from a
worker thread into an ``asyncio.Queue`` so we can ``await`` chunks and forward
them over a WebSocket without blocking the event loop.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

# One generation at a time across all connected devices (shared OllamaClient).
_chat_lock = asyncio.Lock()
_SENTINEL = object()


def _apply_instance_model(instance_id: Optional[str]) -> None:
    from agent.storage import apply_instance_for_run

    apply_instance_for_run(instance_id)


def _normalize_stream(result: Any) -> Any:
    """``run_chat`` may return a generator, a single dict, or a list of dicts."""
    if isinstance(result, dict):
        return [result]
    return result


def _effective_instance_id(instance_id: Optional[str]) -> str:
    if instance_id:
        return instance_id
    try:
        from agent.storage import get_active_instance_id

        return get_active_instance_id()
    except Exception:
        return ""


CHAT_MODES = {"chat", "character", "learn_tutor", "learn_archive"}


def _call_with_optional_stop(fn, *args, stop_check=None, **kwargs):
    """Call chat function with stop_check when supported; fallback for older fakes/tests."""
    if stop_check is None:
        return fn(*args, **kwargs)
    try:
        return fn(*args, stop_check=stop_check, **kwargs)
    except TypeError:
        return fn(*args, **kwargs)


def _dispatch_chat(
    agent: Any,
    *,
    mode: str,
    iid: str,
    message: str,
    history: list[dict[str, Any]],
    thread_id: Optional[str],
    light_research: bool,
    light_coding: bool,
    light_coding_repo: Optional[str],
    light_coding_block: Optional[str],
    bounded_tools: bool,
    image_payloads: Optional[list],
    text_chunks: Optional[list],
    persona_id: Optional[str],
    course_id: Optional[str],
    node_id: Optional[str],
    archive_id: Optional[str],
    status_cb=None,
    stop_check=None,
):
    """Return ``(stream, server_history, save_fn)`` for the requested mode.

    For chat the client owns history (``server_history`` is None). For
    character/learn the server is history-authoritative: it loads prior turns,
    feeds them to the brain, and ``save_fn(assistant_text)`` persists the turn.
    """
    if mode == "character":
        import persona_registry as pr

        persona = pr.get_persona(iid, persona_id or "")
        if persona is None:
            raise ValueError("persona not found")
        prior = pr.load_chat_history(iid, persona_id or "")
        stream = agent.run_character_chat(
            persona,
            user_input=message,
            chat_history=prior,
            image_payloads=image_payloads,
            text_chunks=text_chunks,
            stream=True,
        )

        def save(assistant_text: str) -> None:
            updated = list(prior)
            updated.append({"role": "user", "content": message})
            updated.append({"role": "assistant", "content": assistant_text})
            pr.save_chat_history(iid, persona_id or "", updated)

        return stream, save

    if mode == "learn_tutor":
        import learn_registry as lr
        from tool_library.learn_tools import set_learn_runtime

        set_learn_runtime(iid, course_id=course_id or "")
        prior = lr.load_tutor_history(iid, course_id or "")
        stream = agent.run_learn_tutor_chat(
            course_id or "",
            user_input=message,
            chat_history=prior,
            node_id=node_id or "root",
            text_chunks=text_chunks,
            stream=True,
        )

        def save(assistant_text: str) -> None:
            updated = list(prior)
            updated.append({"role": "user", "content": message})
            updated.append({"role": "assistant", "content": assistant_text})
            lr.save_tutor_history(iid, course_id or "", updated)

        return stream, save

    if mode == "learn_archive":
        import learn_registry as lr
        from tool_library.learn_tools import set_learn_runtime

        set_learn_runtime(iid, archive_id=archive_id or "")
        archive = lr.get_archive(iid, archive_id or "")
        title = getattr(archive, "title", None) or "Archive"
        prior = lr.load_archive_chat_history(iid, archive_id or "")
        stream = agent.run_learn_archive_chat(
            archive_id or "",
            title,
            user_input=message,
            chat_history=prior,
            text_chunks=text_chunks,
            stream=True,
        )

        def save(assistant_text: str) -> None:
            updated = list(prior)
            updated.append({"role": "user", "content": message})
            updated.append({"role": "assistant", "content": assistant_text})
            lr.save_archive_chat_history(iid, archive_id or "", updated)

        return stream, save

    # Default plain chat — client owns history unless thread_id is provided.
    effective_history = history
    if thread_id:
        from agent.storage import load_thread_history

        effective_history = load_thread_history(iid, thread_id)
    if light_research and light_coding:
        stream = _call_with_optional_stop(
            agent.run_light_hybrid_chat,
            message,
            effective_history,
            image_payloads=image_payloads,
            text_chunks=text_chunks,
            stream=True,
            repo_root=light_coding_repo,
            code_block=light_coding_block or None,
            status_cb=status_cb,
            stop_check=stop_check,
        )
    elif light_research:
        stream = _call_with_optional_stop(
            agent.run_light_research_chat,
            message,
            effective_history,
            image_payloads=image_payloads,
            text_chunks=text_chunks,
            stream=True,
            status_cb=status_cb,
            stop_check=stop_check,
        )
    elif bounded_tools:
        stream = _call_with_optional_stop(
            agent.run_bounded_tools_chat,
            message,
            effective_history,
            image_payloads=image_payloads,
            text_chunks=text_chunks,
            stream=True,
            status_cb=status_cb,
            stop_check=stop_check,
        )
    elif light_coding:
        stream = _call_with_optional_stop(
            agent.run_light_coding_chat,
            message,
            effective_history,
            image_payloads=image_payloads,
            text_chunks=text_chunks,
            stream=True,
            repo_root=light_coding_repo,
            code_block=light_coding_block or None,
            stop_check=stop_check,
        )
    else:
        stream = _call_with_optional_stop(
            agent.run_chat,
            message,
            effective_history,
            image_payloads=image_payloads,
            text_chunks=text_chunks,
            stream=True,
            stop_check=stop_check,
        )

    def save(assistant_text: str) -> None:
        from agent.storage import count_user_turns, save_thread_history

        full = list(effective_history)
        full.append({"role": "user", "content": message})
        full.append({"role": "assistant", "content": assistant_text})
        if thread_id:
            save_thread_history(iid, thread_id, full)
        turn_count = count_user_turns(full)
        if turn_count > 0 and turn_count % 10 == 0:
            snippet = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in full[-20:])
            try:
                from agent.storage import load_chat_memory, save_chat_memory
                current_mem = load_chat_memory(iid)
                new_mem = agent.update_chat_memory(snippet, current_mem)
                save_chat_memory(iid, new_mem)
            except Exception:
                pass

    return stream, save


async def stream_chat_chunks(
    *,
    instance_id: Optional[str],
    message: str,
    history: list[dict[str, Any]],
    thread_id: Optional[str] = None,
    light_research: bool = False,
    light_coding: bool = False,
    light_coding_repo: Optional[str] = None,
    light_coding_block: Optional[str] = None,
    bounded_tools: bool = False,
    image_payloads: Optional[list] = None,
    text_chunks: Optional[list] = None,
    mode: str = "chat",
    persona_id: Optional[str] = None,
    course_id: Optional[str] = None,
    node_id: Optional[str] = None,
    archive_id: Optional[str] = None,
    stop_event: Optional["threading.Event"] = None,
) -> AsyncIterator[dict]:
    """Yield ``{"message": {...}}`` chunks for one chat turn.

    Mirrors ``gui._consume_chat_stream``'s chunk contract: each chunk may carry
    ``content``, ``thinking`` and/or ``thinking_source`` keys under ``message``.
    For character/learn modes the server loads/saves history itself.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    mode = (mode or "chat").lower()
    if mode not in CHAT_MODES:
        mode = "chat"

    def producer() -> None:
        import main as brain

        accumulated: list[str] = []
        save_fn = None
        def _status_cb(text: str) -> None:
            if not text:
                return
            loop.call_soon_threadsafe(
                queue.put_nowait, {"message": {"status": str(text)[:300]}}
            )
        def _stop_check() -> bool:
            return bool(stop_event and stop_event.is_set())
        try:
            _apply_instance_model(instance_id)
            iid = _effective_instance_id(instance_id)
            agent = brain.get_agent(instance_id)
            stream, save_fn = _dispatch_chat(
                agent,
                mode=mode,
                iid=iid,
                message=message,
                history=history,
                thread_id=thread_id,
                light_research=light_research,
                light_coding=light_coding,
                light_coding_repo=light_coding_repo,
                light_coding_block=light_coding_block,
                bounded_tools=bounded_tools,
                image_payloads=image_payloads,
                text_chunks=text_chunks,
                persona_id=persona_id,
                course_id=course_id,
                node_id=node_id,
                archive_id=archive_id,
                status_cb=_status_cb,
                stop_check=_stop_check,
            )
            for chunk in _normalize_stream(stream):
                if _stop_check():
                    break
                msg = (chunk or {}).get("message", {}) or {}
                content = msg.get("content")
                if content:
                    accumulated.append(content)
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:  # surface errors to the client instead of hanging
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"message": {"content": f"\n[remote error] {exc}"}},
            )
        else:
            if save_fn is not None:
                final = "".join(accumulated).strip()
                if final:
                    try:
                        save_fn(final)
                    except Exception:
                        pass
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    async with _chat_lock:
        fut = loop.run_in_executor(None, producer)
        try:
            while True:
                chunk = await queue.get()
                if chunk is _SENTINEL:
                    break
                yield chunk
        finally:
            await fut


def derive_task_name(prompt: str) -> str:
    """Build a filesystem-safe task name from a prompt (for ledger/plan files)."""
    import re
    import time

    base = re.sub(r"[^a-zA-Z0-9]+", "_", (prompt or "").strip().lower()).strip("_")
    base = base[:48] or "task"
    return f"{base}_{int(time.time())}"


def list_instance_infos() -> list[dict[str, Any]]:
    """Return serializable instance summaries for the client picker."""
    from agent.storage import list_instances

    out: list[dict[str, Any]] = []
    for inst in list_instances():
        out.append(
            {
                "id": inst.id,
                "display_name": inst.display_name,
                "specialty": getattr(inst, "specialty", "") or "",
                "default_mode": getattr(inst, "default_mode", "chat") or "chat",
                "ollama_model": getattr(inst, "ollama_model", None),
            }
        )
    return out
