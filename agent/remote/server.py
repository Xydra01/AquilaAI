"""FastAPI app for the Aquila Remote Companion.

Serves the installable PWA in ``webapp/`` and exposes a small JSON + WebSocket
API that reuses Aquila's existing brain. Run it with::

    cd agent
    python -m uvicorn remote.server:app --host 0.0.0.0 --port 8800

or via ``scripts/aquila-remote-serve.sh``.
"""
from __future__ import annotations

import contextlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import asyncio
import threading

from . import auth, learn, personas, server_control, session, tasks, uploads
from .schemas import (
    ArchiveCreateRequest,
    CourseCreateRequest,
    ChatEditRequest,
    ChatThreadRequest,
    ChatForkRequest,
    ModelActionRequest,
    ModelActionResponse,
    McpServersResponse,
    McpServersUpdate,
    McpServerView,
    McpTestResponse,
    EnvSectionView,
    EnvUpdateRequest,
    OllamaActiveRequest,
    OllamaModelsResponse,
    PairRequest,
    PairResponse,
    PersonaCreateRequest,
    PreferencesRequest,
    RuntimeSettingsUpdate,
    RuntimeSettingsView,
    SearchStatusResponse,
    ServerActionRequest,
    ServerActionResponse,
    UploadResponse,
)

# webapp/ lives at the repo root, two levels up from agent/remote/.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_WEBAPP_DIR = _REPO_ROOT / "webapp"


@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    auth.ensure_host_identity()
    yield


app = FastAPI(title="Aquila Remote Companion", version="1.0", lifespan=_lifespan)


def require_device(authorization: Optional[str] = Header(default=None)) -> dict:
    """FastAPI dependency: validate the Bearer device token."""
    token = auth.extract_bearer(authorization)
    device = auth.verify_token(token)
    if device is None:
        raise HTTPException(status_code=401, detail="invalid or missing device token")
    return device


def _suggest_followups(answer: str) -> list[str]:
    text = (answer or "").strip()
    if not text:
        return []
    first = ""
    for ln in text.splitlines():
        if ln.strip():
            first = ln.strip("-* \t")
            break
    first = " ".join(first.split())[:70]
    if not first:
        return []
    return [
        f"Can you expand on: {first}?",
        "Can you summarize this briefly?",
        "What are the next actions?",
    ]


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "service": "aquila-remote", "host_id": auth.get_host_id()}


@app.post("/api/pair", response_model=PairResponse)
async def pair(req: PairRequest) -> PairResponse:
    result = auth.pair_device(req.host_id, req.pairing_code, req.device_name)
    if result is None:
        raise HTTPException(status_code=401, detail="pairing failed (bad Host ID or code)")
    return PairResponse(
        token=result["token"],
        host_id=result["host_id"],
        device_name=result["name"],
    )


@app.get("/api/devices")
async def devices(_: dict = Depends(require_device)) -> JSONResponse:
    return JSONResponse({"devices": auth.list_devices()})


@app.delete("/api/devices/{token_id}")
async def revoke_device(token_id: str, _: dict = Depends(require_device)) -> JSONResponse:
    ok = auth.revoke_token(token_id)
    if not ok:
        raise HTTPException(status_code=404, detail="device not found")
    return JSONResponse({"ok": True})


@app.get("/api/instances")
async def instances(_: dict = Depends(require_device)) -> JSONResponse:
    return JSONResponse({"instances": session.list_instance_infos()})


@app.post("/api/chat/threads/{thread_id}/regenerate")
async def chat_regenerate_thread(
    thread_id: str, req: ChatThreadRequest, _: dict = Depends(require_device)
) -> JSONResponse:
    from agent.storage import regenerate_last_turn

    instance_id = (req.instance_id or "default").strip() or "default"
    history, prompt = regenerate_last_turn(instance_id, thread_id)
    return JSONResponse({"ok": True, "thread_id": thread_id, "prompt": prompt, "history": history})


@app.post("/api/chat/threads/{thread_id}/edit-last")
async def chat_edit_last_turn(
    thread_id: str, req: ChatEditRequest, _: dict = Depends(require_device)
) -> JSONResponse:
    from agent.storage import edit_last_user_turn

    instance_id = (req.instance_id or "default").strip() or "default"
    history = edit_last_user_turn(instance_id, thread_id, req.text)
    return JSONResponse({"ok": True, "thread_id": thread_id, "history": history})


@app.post("/api/chat/threads/fork")
async def chat_fork_thread(req: ChatForkRequest, _: dict = Depends(require_device)) -> JSONResponse:
    from agent.storage import fork_thread

    instance_id = (req.instance_id or "default").strip() or "default"
    t = fork_thread(
        instance_id,
        req.source_thread_id,
        upto_index=req.upto_index,
        title_hint=req.title_hint or "Forked chat",
    )
    return JSONResponse({"ok": True, "thread_id": t.id, "title": t.title})


@app.post("/api/uploads", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...), _: dict = Depends(require_device)
) -> UploadResponse:
    """Parse uploaded attachments and return a short-lived ``upload_token``."""
    named_bytes: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        named_bytes.append((f.filename or "file", content))
    if not named_bytes:
        raise HTTPException(status_code=400, detail="no files uploaded")
    result = uploads.store_files(named_bytes)
    return UploadResponse(**result)


@app.get("/api/server/status")
async def server_status(_: dict = Depends(require_device)) -> JSONResponse:
    return JSONResponse({"engines": server_control.engine_status()})


@app.post("/api/server/start", response_model=ServerActionResponse)
async def server_start(
    req: ServerActionRequest, _: dict = Depends(require_device)
) -> ServerActionResponse:
    result = server_control.start_engine(req.engine, stop_other=req.stop_other)
    return ServerActionResponse(**_action_fields(result))


@app.get("/api/server/logs")
async def server_logs(
    engine: str, lines: int = 200, _: dict = Depends(require_device)
) -> JSONResponse:
    if engine not in server_control.ENGINES:
        raise HTTPException(status_code=400, detail="unknown engine")
    return JSONResponse({"engine": engine, "text": server_control.tail_log(engine, lines)})


@app.post("/api/server/stop", response_model=ServerActionResponse)
async def server_stop(
    req: ServerActionRequest, _: dict = Depends(require_device)
) -> ServerActionResponse:
    result = server_control.stop_engine(req.engine)
    return ServerActionResponse(**_action_fields(result))


@app.post("/api/model/warmup", response_model=ModelActionResponse)
async def model_warmup(
    req: ModelActionRequest, _: dict = Depends(require_device)
) -> ModelActionResponse:
    base_url = _engine_base_url(req)
    result = server_control.warmup_model(base_url=base_url)
    return ModelActionResponse(ok=result["ok"], message=result["message"])


@app.post("/api/model/eject", response_model=ModelActionResponse)
async def model_eject(
    req: ModelActionRequest, _: dict = Depends(require_device)
) -> ModelActionResponse:
    base_url = _engine_base_url(req)
    result = server_control.eject_model(base_url=base_url, all_loaded=req.all_loaded)
    return ModelActionResponse(ok=result["ok"], message=result["message"])


@app.get("/api/runtime/settings", response_model=RuntimeSettingsView)
async def get_runtime_settings(_: dict = Depends(require_device)) -> RuntimeSettingsView:
    from agent.storage import load_runtime_settings

    s = load_runtime_settings()
    return RuntimeSettingsView(
        ollama_engine=s.ollama_engine,
        ollama_base_url=s.ollama_base_url,
        ollama_model=s.ollama_model,
        ollama_num_ctx=s.ollama_num_ctx,
        searxng_base_url=s.searxng_base_url,
        searxng_engines=s.searxng_engines,
    )


@app.put("/api/runtime/settings", response_model=RuntimeSettingsView)
async def put_runtime_settings(
    req: RuntimeSettingsUpdate, _: dict = Depends(require_device)
) -> RuntimeSettingsView:
    import main as brain
    from agent.storage import load_runtime_settings, save_runtime_settings, set_engine

    s = load_runtime_settings()
    if req.ollama_engine:
        set_engine(s, req.ollama_engine)
    if req.ollama_base_url:
        s.ollama_base_url = req.ollama_base_url.strip()
    if req.ollama_model:
        s.ollama_model = req.ollama_model.strip()
    if req.ollama_num_ctx is not None:
        s.ollama_num_ctx = req.ollama_num_ctx if req.ollama_num_ctx > 0 else None
    if req.searxng_base_url:
        s.searxng_base_url = req.searxng_base_url.strip()
    if req.searxng_engines:
        s.searxng_engines = req.searxng_engines.strip()
    save_runtime_settings(s)
    brain.apply_runtime_settings(brain.client)
    return await get_runtime_settings(_)


@app.get("/api/runtime/env_sections", response_model=list[EnvSectionView])
async def get_env_sections(_: dict = Depends(require_device)) -> list[EnvSectionView]:
    from agent.storage import catalog_sections_for_gui, load_preferences, load_catalog

    merged = load_preferences()
    result = []
    for sec in catalog_sections_for_gui(include_advanced=True):
        if sec.id in ("ollama_connection", "searxng_connection"):
            continue
        vars_view = []
        for setting in sec.settings:
            vars_view.append({
                "key": setting.key,
                "default_value": setting.default,
                "current_value": merged.get(setting.key, setting.default),
                "description": setting.description or setting.label,
                "inferred_type": setting.type,
            })
        result.append({"title": sec.title, "variables": vars_view})
    # Include export-only connection sections for remote parity
    for sec in load_catalog():
        if sec.id not in ("ollama_connection", "searxng_connection"):
            continue
        vars_view = []
        for setting in sec.settings:
            vars_view.append({
                "key": setting.key,
                "default_value": setting.default,
                "current_value": merged.get(setting.key, setting.default),
                "description": setting.description or setting.label,
                "inferred_type": setting.type,
            })
        result.append({"title": sec.title, "variables": vars_view})
    return result


@app.post("/api/runtime/env")
async def post_env(
    req: EnvUpdateRequest, _: dict = Depends(require_device)
):
    import main as brain
    from agent.storage import save_preferences

    save_preferences(req.updates, export_env=True)
    brain.apply_runtime_settings(brain.client)
    return {"ok": True}


@app.get("/api/ollama/models", response_model=OllamaModelsResponse)
async def ollama_models(
    engine: str = "stock", _: dict = Depends(require_device)
) -> OllamaModelsResponse:
    import main as brain

    engine = (engine or "stock").strip().lower()
    if engine not in server_control.ENGINES:
        raise HTTPException(status_code=400, detail="unknown engine")
    base = server_control.ENGINES[engine]["base_url"]
    models = brain.client.list_models(base_url=base, name_filter="aquila")
    return OllamaModelsResponse(engine=engine, models=models)


@app.post("/api/ollama/active", response_model=RuntimeSettingsView)
async def ollama_active(
    req: OllamaActiveRequest, _: dict = Depends(require_device)
) -> RuntimeSettingsView:
    import main as brain
    from agent.storage import (
        load_runtime_settings,
        prefer_model_for_engine,
        save_runtime_settings,
        set_engine,
    )

    s = load_runtime_settings()
    set_engine(s, req.engine)
    models = brain.client.list_models(
        base_url=s.ollama_base_url, name_filter="aquila"
    )
    model = (req.model or "").strip() or prefer_model_for_engine(models, req.engine)
    if model:
        from agent.storage import resolve_model_tag

        resolved = resolve_model_tag(model, models)
        s.ollama_model = resolved or model
    save_runtime_settings(s)
    brain.apply_runtime_settings(brain.client)
    return await get_runtime_settings(_)


@app.get("/api/search/status", response_model=SearchStatusResponse)
async def search_status(_: dict = Depends(require_device)) -> SearchStatusResponse:
    from agent.research import docker_status, probe_health

    ok, message = probe_health()
    return SearchStatusResponse(ok=ok, message=message, docker=docker_status())


@app.post("/api/search/start", response_model=SearchStatusResponse)
async def search_start(_: dict = Depends(require_device)) -> SearchStatusResponse:
    from agent.research import docker_status, start_search

    ok, message = start_search()
    return SearchStatusResponse(ok=ok, message=message, docker=docker_status())


@app.post("/api/search/stop", response_model=SearchStatusResponse)
async def search_stop(_: dict = Depends(require_device)) -> SearchStatusResponse:
    from agent.research import docker_status, stop_search

    ok, message = stop_search()
    return SearchStatusResponse(ok=ok, message=message, docker=docker_status())


@app.get("/api/mcp/servers", response_model=McpServersResponse)
async def get_mcp_servers(_: dict = Depends(require_device)) -> McpServersResponse:
    import main as brain
    from agent.storage import load_app_mcp_servers

    servers = load_app_mcp_servers()
    agent = brain.get_global_agent()
    health = agent.mcp_bridge.server_health() if agent.mcp_bridge else {}
    return McpServersResponse(
        servers=[McpServerView(**s) for s in servers],
        health=health,
    )


@app.put("/api/mcp/servers", response_model=McpServersResponse)
async def put_mcp_servers(
    req: McpServersUpdate, _: dict = Depends(require_device)
) -> McpServersResponse:
    import main as brain
    from agent.storage import save_app_mcp_servers

    payload = [s.model_dump() for s in req.servers]
    save_app_mcp_servers(payload)
    brain.get_global_agent().refresh_mcp_tools()
    return await get_mcp_servers(_)


@app.post("/api/mcp/test/{server_name}", response_model=McpTestResponse)
async def test_mcp_server(
    server_name: str, _: dict = Depends(require_device)
) -> McpTestResponse:
    import main as brain

    agent = brain.get_global_agent()
    result = agent.mcp_bridge.test_server(server_name)
    return McpTestResponse(
        ok=bool(result.get("ok") or result.get("healthy")),
        name=server_name,
        status=str(result.get("status", "")),
        tool_count=int(result.get("tool_count") or 0),
        error=str(result.get("error") or ""),
    )


def _action_fields(result: dict) -> dict:
    return {
        "ok": bool(result.get("ok")),
        "message": str(result.get("message", "")),
        "engine": result.get("engine"),
        "pid": result.get("pid"),
        "needs_confirm": bool(result.get("needs_confirm", False)),
    }


def _engine_base_url(req: ModelActionRequest) -> Optional[str]:
    """Model actions may target a specific engine via the 'model' field shortcut."""
    engine = (req.model or "").strip().lower()
    if engine in server_control.ENGINES:
        return server_control.ENGINES[engine]["base_url"]
    return None


@app.websocket("/api/chat")
async def chat_ws(websocket: WebSocket) -> None:
    """Stream a chat turn.

    Protocol: client sends one JSON request
    ``{instance_id, mode, message, light_research, history?, thread_id?}``; server streams
    ``{"type": "thinking"|"token"|"thinking_source"|"done"|"error", ...}`` frames.
    """
    token = websocket.query_params.get("token") or auth.extract_bearer(
        websocket.headers.get("authorization")
    )
    if auth.verify_token(token) is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            await _run_chat_turn(websocket, payload)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - report and close gracefully
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:
            pass


async def _run_chat_turn(websocket: WebSocket, payload: dict) -> None:
    message = (payload or {}).get("message", "")
    if not isinstance(message, str) or not message.strip():
        await websocket.send_json({"type": "error", "error": "empty message"})
        return

    instance_id = (payload or {}).get("instance_id")
    light_research = bool((payload or {}).get("light_research", False))
    light_coding = bool((payload or {}).get("light_coding", False))
    bounded_tools = bool((payload or {}).get("bounded_tools", False))
    history = (payload or {}).get("history") or []
    if not isinstance(history, list):
        history = []
    mode = (payload or {}).get("mode", "chat")
    thread_id = (payload or {}).get("thread_id")
    upload_tokens = (payload or {}).get("upload_tokens") or []
    text_chunks, image_payloads = uploads.resolve_tokens(upload_tokens)
    if mode == "chat":
        from agent.core.chat_context import parse_at_context
        from agent.coding import process_local_attachments

        cleaned, at_files, _at_urls = parse_at_context(message)
        message = cleaned
        if at_files:
            at_chunks, at_images = process_local_attachments(at_files)
            text_chunks = list(text_chunks or []) + list(at_chunks or [])
            image_payloads = list(image_payloads or []) + list(at_images or [])
    cancel_event = threading.Event()

    async def _watch_cancel() -> None:
        try:
            while True:
                msg = await websocket.receive_json()
                if isinstance(msg, dict) and msg.get("action") == "cancel":
                    cancel_event.set()
                    return
        except (WebSocketDisconnect, Exception):
            return

    cancel_task = asyncio.create_task(_watch_cancel())

    full_text = ""
    try:
        async for chunk in session.stream_chat_chunks(
            instance_id=instance_id,
            message=message,
            history=history,
            thread_id=thread_id,
            light_research=light_research,
            light_coding=light_coding,
            light_coding_repo=(payload or {}).get("light_coding_repo"),
            light_coding_block=(payload or {}).get("light_coding_block"),
            bounded_tools=bounded_tools,
            text_chunks=text_chunks or None,
            image_payloads=image_payloads or None,
            mode=mode,
            persona_id=(payload or {}).get("persona_id"),
            course_id=(payload or {}).get("course_id"),
            node_id=(payload or {}).get("node_id"),
            archive_id=(payload or {}).get("archive_id"),
            stop_event=cancel_event,
        ):
            if cancel_event.is_set():
                break
            msg = (chunk or {}).get("message", {}) or {}
            status = msg.get("status") or ""
            if status:
                await websocket.send_json({"type": "status", "text": str(status)})
            if msg.get("thinking_source") == "content":
                await websocket.send_json({"type": "thinking_source", "source": "content"})
            think_tok = msg.get("thinking") or ""
            if think_tok:
                await websocket.send_json({"type": "thinking", "delta": think_tok})
            token = msg.get("content") or ""
            if token:
                full_text += token
                await websocket.send_json({"type": "token", "delta": token})
    except WebSocketDisconnect:
        cancel_event.set()
        return
    finally:
        cancel_task.cancel()
        with contextlib.suppress(BaseException):
            await cancel_task

    await websocket.send_json(
        {
            "type": "done",
            "content": full_text,
            "cancelled": cancel_event.is_set(),
            "followups": _suggest_followups(full_text),
        }
    )


@app.websocket("/api/task")
async def task_ws(websocket: WebSocket) -> None:
    """Run a job-style task (research / build) and stream ledger + plan frames.

    Protocol: client sends ``{instance_id, task_name, prompt, mode,
    upload_tokens?, persona_research_lore?, learn_syllabus_web?}`` once; later
    ``{action:"stop"}`` (or a socket close) cancels. Server streams
    ``{type:"ledger"|"plan"|"done"|"busy"|"error"}`` frames.
    """
    token = websocket.query_params.get("token") or auth.extract_bearer(
        websocket.headers.get("authorization")
    )
    if auth.verify_token(token) is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    cancel_event = threading.Event()

    try:
        payload = await websocket.receive_json()
    except (WebSocketDisconnect, Exception):
        return

    prompt = (payload or {}).get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        await websocket.send_json({"type": "error", "error": "empty prompt"})
        await websocket.close()
        return

    task_name = (payload or {}).get("task_name") or session.derive_task_name(prompt)
    mode = (payload or {}).get("mode", "research")
    upload_tokens = (payload or {}).get("upload_tokens") or []
    text_chunks, image_payloads = uploads.resolve_tokens(upload_tokens)

    async def _watch_for_stop() -> None:
        try:
            while True:
                msg = await websocket.receive_json()
                if (msg or {}).get("action") == "stop":
                    cancel_event.set()
                    return
        except Exception:
            cancel_event.set()

    watcher = asyncio.ensure_future(_watch_for_stop())
    try:
        async for frame in tasks.stream_task(
            instance_id=(payload or {}).get("instance_id"),
            task_name=task_name,
            prompt=prompt,
            mode=mode,
            text_chunks=text_chunks or None,
            image_payloads=image_payloads or None,
            persona_research_lore=bool((payload or {}).get("persona_research_lore", False)),
            learn_syllabus_web=bool((payload or {}).get("learn_syllabus_web", False)),
            cancel_event=cancel_event,
        ):
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        cancel_event.set()
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:
            pass
    finally:
        watcher.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


# Deliverables are restricted to these data subfolders.
_DELIVERABLE_DIRS = ("Agent-Research", "Agent-Creations", "Agent-Drafts", "Agent-Code", "Agent-Tasks", "Agent-Plans")


def _safe_deliverable_path(raw: str):
    """Resolve ``raw`` only if it lives inside a whitelisted data folder."""
    from pathlib import Path

    from agent.storage import agent_data_path

    if not raw:
        return None
    candidate = Path(raw)
    try:
        candidate = candidate.resolve()
    except Exception:
        return None
    for folder in _DELIVERABLE_DIRS:
        root = agent_data_path(folder).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if not candidate.is_file():
            return None
        if folder == "Agent-Code" or candidate.suffix.lower() in (".md", ".txt", ".json", ".py", ".js", ".html", ".css", ".sh"):
            return candidate
    return None


@app.get("/api/deliverable")
async def get_deliverable(path: str, _: dict = Depends(require_device)) -> JSONResponse:
    resolved = _safe_deliverable_path(path)
    if resolved is None:
        raise HTTPException(status_code=404, detail="deliverable not found or restricted")
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=500, detail="could not read file")
    return JSONResponse(
        {"name": resolved.name, "path": str(resolved), "text": text}
    )


@app.get("/api/research/deliverables")
async def list_research_deliverables(_: dict = Depends(require_device)) -> JSONResponse:
    from agent.storage import agent_data_path

    root = agent_data_path("Agent-Research")
    items = []
    if root.is_dir():
        for p in sorted(root.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
            stat = p.stat()
            items.append({"name": p.name, "path": str(p), "modified_at": stat.st_mtime, "size": stat.st_size})
    return JSONResponse({"deliverables": items})


@app.get("/api/code/repos")
async def list_code_repos(_: dict = Depends(require_device)) -> JSONResponse:
    from agent.storage import agent_data_path

    root = agent_data_path("Agent-Code")
    repos = []
    if root.is_dir():
        for p in sorted(root.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if p.is_dir() and not p.name.startswith("."):
                repos.append({"name": p.name, "modified_at": p.stat().st_mtime})
    return JSONResponse({"repos": repos})


@app.get("/api/code/repos/{repo_name}/files")
async def list_code_repo_files(repo_name: str, _: dict = Depends(require_device)) -> JSONResponse:
    from agent.storage import agent_data_path

    root = agent_data_path("Agent-Code") / repo_name
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="repo not found")
    
    files = []
    for p in root.rglob("*"):
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
            files.append({
                "rel_path": str(p.relative_to(root).as_posix()),
                "abs_path": str(p),
                "size": p.stat().st_size
            })
    return JSONResponse({"files": sorted(files, key=lambda f: f["rel_path"])})


def _iid(instance_id: Optional[str]) -> str:
    return session._effective_instance_id(instance_id)


# --- Character workspace ---------------------------------------------------

@app.get("/api/character/personas")
async def character_list(
    instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"personas": personas.list_personas(_iid(instance_id))})


@app.post("/api/character/personas")
async def character_create(
    req: PersonaCreateRequest, _: dict = Depends(require_device)
) -> JSONResponse:
    name = (req.display_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="display_name required")
    result = personas.create_persona_for_build(
        _iid(req.instance_id), name, req.description or "", req.research_lore
    )
    return JSONResponse(result)


@app.delete("/api/character/personas/{persona_id}")
async def character_delete(
    persona_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    ok = personas.delete_persona(_iid(instance_id), persona_id)
    if not ok:
        raise HTTPException(status_code=404, detail="persona not found")
    return JSONResponse({"ok": True})


@app.get("/api/character/personas/{persona_id}/history")
async def character_history(
    persona_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"history": personas.load_history(_iid(instance_id), persona_id)})


@app.get("/api/character/personas/{persona_id}/preferences")
async def character_get_prefs(
    persona_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"text": personas.load_preferences(_iid(instance_id), persona_id)})


@app.put("/api/character/personas/{persona_id}/preferences")
async def character_put_prefs(
    persona_id: str, req: PreferencesRequest, _: dict = Depends(require_device)
) -> JSONResponse:
    personas.save_preferences(_iid(req.instance_id), persona_id, req.text or "")
    return JSONResponse({"ok": True})


# --- Learn workspace: courses ---------------------------------------------

@app.get("/api/learn/courses")
async def learn_list_courses(
    instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"courses": learn.list_courses(_iid(instance_id))})


@app.post("/api/learn/courses")
async def learn_create_course(
    req: CourseCreateRequest, _: dict = Depends(require_device)
) -> JSONResponse:
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    result = learn.create_course_for_build(
        _iid(req.instance_id), title, req.topic or "", req.intake or "files", req.web
    )
    return JSONResponse(result)


@app.delete("/api/learn/courses/{course_id}")
async def learn_delete_course(
    course_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    learn.delete_course(_iid(instance_id), course_id)
    return JSONResponse({"ok": True})


@app.get("/api/learn/courses/{course_id}/syllabus")
async def learn_syllabus(
    course_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"syllabus": learn.get_syllabus(_iid(instance_id), course_id)})


@app.get("/api/learn/courses/{course_id}/tutor-history")
async def learn_tutor_history(
    course_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"history": learn.tutor_history(_iid(instance_id), course_id)})


@app.get("/api/learn/courses/{course_id}/assessments")
async def learn_assessments(
    course_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"assessments": learn.list_assessments(_iid(instance_id), course_id)})


@app.post("/api/learn/courses/{course_id}/assessments/submit")
async def learn_submit_assessment(
    course_id: str, body: dict, _: dict = Depends(require_device)
) -> JSONResponse:
    node_id = (body or {}).get("node_id")
    assessment_id = (body or {}).get("assessment_id")
    score = float((body or {}).get("score", 0))
    if not node_id or not assessment_id:
        raise HTTPException(status_code=400, detail="node_id and assessment_id required")
    result = learn.submit_assessment(
        _iid((body or {}).get("instance_id")), course_id, node_id, assessment_id, score
    )
    return JSONResponse(result)


@app.post("/api/learn/courses/{course_id}/sources")
async def learn_course_sources(
    course_id: str,
    files: list[UploadFile] = File(...),
    instance_id: Optional[str] = None,
    _: dict = Depends(require_device),
) -> JSONResponse:
    named = [(f.filename or "file", await f.read()) for f in files]
    if not named:
        raise HTTPException(status_code=400, detail="no files uploaded")
    message = learn.add_course_sources(_iid(instance_id), course_id, named)
    return JSONResponse({"ok": True, "message": message})


# --- Learn workspace: archives --------------------------------------------

@app.get("/api/learn/archives")
async def learn_list_archives(
    instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"archives": learn.list_archives(_iid(instance_id))})


@app.post("/api/learn/archives")
async def learn_create_archive(
    req: ArchiveCreateRequest, _: dict = Depends(require_device)
) -> JSONResponse:
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    return JSONResponse({"archive": learn.create_archive(_iid(req.instance_id), title)})


@app.delete("/api/learn/archives/{archive_id}")
async def learn_delete_archive(
    archive_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    learn.delete_archive(_iid(instance_id), archive_id)
    return JSONResponse({"ok": True})


@app.get("/api/learn/archives/{archive_id}/history")
async def learn_archive_history(
    archive_id: str, instance_id: Optional[str] = None, _: dict = Depends(require_device)
) -> JSONResponse:
    return JSONResponse({"history": learn.archive_history(_iid(instance_id), archive_id)})


@app.post("/api/learn/archives/{archive_id}/sources")
async def learn_archive_sources(
    archive_id: str,
    files: list[UploadFile] = File(...),
    instance_id: Optional[str] = None,
    _: dict = Depends(require_device),
) -> JSONResponse:
    named = [(f.filename or "file", await f.read()) for f in files]
    if not named:
        raise HTTPException(status_code=400, detail="no files uploaded")
    message = learn.add_archive_sources(_iid(instance_id), archive_id, named)
    return JSONResponse({"ok": True, "message": message})


def _mount_webapp() -> None:
    """Serve the PWA at ``/`` when the assets exist (built in a later step)."""
    if _WEBAPP_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_WEBAPP_DIR), html=True), name="webapp")


def _mount_mcp_host_sse() -> None:
    from remote.mcp_host_mount import get_mcp_host_sse_app

    app.mount("/api/mcp/host", get_mcp_host_sse_app())


_mount_mcp_host_sse()
_mount_webapp()
