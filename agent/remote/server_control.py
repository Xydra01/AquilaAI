"""Start/stop the Ollama engines and report status for the Remote Companion.

A button in the PWA maps to the cross-platform bash serve scripts
(``ollama-serve-*.sh``). They are launched via **bash** on every OS - Git Bash
on Windows, native bash on macOS/Linux - so one code path works everywhere.
PIDs are tracked in ``remote_config.json`` so a later request can stop them.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from . import config

# repo root = two levels up from agent/remote/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

ENGINES: dict[str, dict] = {
    "tq": {
        "script": "ollama-serve-turboquant-port.sh",
        "base_url": "http://127.0.0.1:11435",
        "label": "TurboQuant",
    },
    "stock": {
        "script": "ollama-serve-stock.sh",
        "base_url": "http://127.0.0.1:11434",
        "label": "Stock",
    },
}


# --- bash resolution -------------------------------------------------------

def resolve_bash() -> Optional[str]:
    """Locate a bash interpreter. Prefer Git Bash on Windows over WSL bash."""
    override = os.getenv("AQUILA_BASH_BIN", "").strip()
    if override and Path(override).exists():
        return override

    if os.name == "nt":
        candidates = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]
        local = os.getenv("LOCALAPPDATA")
        if local:
            candidates.append(str(Path(local) / "Programs" / "Git" / "bin" / "bash.exe"))
        for c in candidates:
            if Path(c).exists():
                return c
        # Fall back to PATH (may be WSL bash; better than nothing).
        found = shutil.which("bash")
        if found:
            return found
        return None

    return shutil.which("bash") or ("/bin/bash" if Path("/bin/bash").exists() else None)


def _script_arg(engine: str) -> str:
    path = _SCRIPTS_DIR / ENGINES[engine]["script"]
    # Git Bash accepts forward-slash paths even on Windows.
    return str(path).replace("\\", "/")


def _other_engine(engine: str) -> str:
    return "stock" if engine == "tq" else "tq"


def _launch_mode() -> str:
    try:
        from agent.aquila_runtime.paths import launch_mode

        return launch_mode()
    except Exception:
        return "dev"


def _stock_serve_env(port: str = "11434") -> dict[str, str]:
    env = os.environ.copy()
    env.pop("OLLAMA_NEW_ENGINE", None)
    flash = env.get("OLLAMA_FLASH_ATTENTION", "1")
    kv = env.get("OLLAMA_KV_CACHE_TYPE", "q8_0")
    if kv.startswith("tq"):
        kv = "q8_0"
    if flash.lower() in ("0", "false", "off", "no", ""):
        flash = "0"
        kv = "f16"
    env["OLLAMA_FLASH_ATTENTION"] = flash
    env["OLLAMA_KV_CACHE_TYPE"] = kv
    env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
    binary = _packaged_ollama_binary()
    if binary:
        env["PATH"] = str(binary.parent) + os.pathsep + env.get("PATH", "")
    return env


def _packaged_ollama_binary() -> Path | None:
    try:
        from agent.aquila_runtime.paths import packaged_ollama_binary

        return packaged_ollama_binary()
    except Exception:
        return None


def _start_engine_packaged(engine: str) -> dict:
    if engine != "stock":
        return {
            "ok": False,
            "message": "Packaged installs support stock Ollama only (TurboQuant: dev install)",
            "engine": engine,
        }
    from agent.aquila_runtime.ollama_bundle import ensure_packaged_ollama

    ok, msg = ensure_packaged_ollama()
    if not ok:
        return {"ok": False, "message": msg, "engine": engine}
    binary = _packaged_ollama_binary()
    if not binary or not binary.is_file():
        return {
            "ok": False,
            "message": "bundled Ollama binary not found under runtime/ollama",
            "engine": engine,
        }
    port = ENGINES[engine]["base_url"].rsplit(":", 1)[-1]
    env = _stock_serve_env(port)
    try:
        log_handle = open(log_path(engine), "a", encoding="utf-8", errors="replace")
        log_handle.write(
            f"\n===== {ENGINES[engine]['label']} packaged start {time.ctime()} =====\n"
        )
        log_handle.flush()
    except OSError:
        log_handle = None
    try:
        from agent.aquila_runtime.subprocess_win import popen_hidden

        proc = popen_hidden(
            [str(binary), "serve"],
            cwd=str(binary.parent),
            env=env,
            stdout=log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if log_handle else subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            new_process_group=True,
            start_new_session=(os.name != "nt"),
        )
    except Exception as exc:  # noqa: BLE001
        if log_handle:
            log_handle.close()
        return {"ok": False, "message": f"failed to launch: {exc}", "engine": engine}
    finally:
        if log_handle:
            log_handle.close()
    _set_tracked_pid(engine, proc.pid)
    return {
        "ok": True,
        "message": f"starting {ENGINES[engine]['label']} (packaged)",
        "engine": engine,
        "pid": proc.pid,
    }



def log_path(engine: str) -> Path:
    """Captured stdout/stderr for an engine launched by the companion."""
    from agent.storage import agent_data_path

    log_dir = agent_data_path("Agent-Logs", "remote")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"ollama-{engine}.log"


def tail_log(engine: str, lines: int = 200) -> str:
    if engine not in ENGINES:
        return ""
    path = log_path(engine)
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    parts = text.splitlines()
    return "\n".join(parts[-max(1, int(lines)):])


# --- probing ---------------------------------------------------------------

def probe(base_url: str) -> bool:
    import requests

    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def loaded_models(base_url: str) -> list[str]:
    import requests

    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/ps", timeout=3)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


# --- pid tracking ----------------------------------------------------------

def _get_tracked_pid(engine: str) -> Optional[int]:
    servers = config.load_config().get("servers", {})
    rec = servers.get(engine) or {}
    pid = rec.get("pid")
    return int(pid) if pid else None


def _set_tracked_pid(engine: str, pid: Optional[int]) -> None:
    cfg = config.load_config()
    servers = cfg.setdefault("servers", {})
    if pid is None:
        servers.pop(engine, None)
    else:
        servers[engine] = {"pid": pid, "started_at": time.time()}
    config.save_config(cfg)


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        # Best-effort fallback without psutil.
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


# --- lifecycle -------------------------------------------------------------

def start_engine(engine: str, stop_other: bool = False) -> dict:
    if engine not in ENGINES:
        return {"ok": False, "message": f"unknown engine '{engine}'", "engine": engine}

    base_url = ENGINES[engine]["base_url"]
    if probe(base_url):
        return {
            "ok": True,
            "message": f"{ENGINES[engine]['label']} already running",
            "engine": engine,
            "pid": _get_tracked_pid(engine),
        }

    # Single-engine enforcement: never run TQ + stock together (VRAM).
    other = _other_engine(engine)
    other_up = probe(ENGINES[other]["base_url"])
    other_pid = _get_tracked_pid(other)
    if (other_up or other_pid) and not stop_other:
        return {
            "ok": False,
            "needs_confirm": True,
            "engine": engine,
            "message": (
                f"{ENGINES[other]['label']} is running. Stop it and start "
                f"{ENGINES[engine]['label']} instead?"
            ),
        }
    if stop_other and (other_up or other_pid):
        stop_engine(other)

    if _launch_mode() == "packaged":
        return _start_engine_packaged(engine)

    bash = resolve_bash()
    if not bash:
        return {
            "ok": False,
            "message": "bash not found (install Git for Windows / use a bash shell)",
            "engine": engine,
        }

    script = _SCRIPTS_DIR / ENGINES[engine]["script"]
    if not script.is_file():
        return {"ok": False, "message": f"missing script {script.name}", "engine": engine}

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    # Capture output so mobile clients can read what the (invisible) Git Bash
    # window would have shown.
    try:
        log_handle = open(log_path(engine), "a", encoding="utf-8", errors="replace")
        log_handle.write(f"\n===== {ENGINES[engine]['label']} start {time.ctime()} =====\n")
        log_handle.flush()
    except OSError:
        log_handle = None

    try:
        from agent.aquila_runtime.subprocess_win import popen_hidden

        proc = popen_hidden(
            [bash, _script_arg(engine)],
            cwd=str(_REPO_ROOT),
            stdout=log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if log_handle else subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            new_process_group=True,
            start_new_session=(os.name != "nt"),
        )
    except Exception as exc:  # noqa: BLE001
        if log_handle:
            log_handle.close()
        return {"ok": False, "message": f"failed to launch: {exc}", "engine": engine}
    finally:
        # The child keeps its own duplicated handle; close ours.
        if log_handle:
            log_handle.close()

    _set_tracked_pid(engine, proc.pid)
    return {
        "ok": True,
        "message": f"starting {ENGINES[engine]['label']} (warming up)",
        "engine": engine,
        "pid": proc.pid,
    }


def stop_engine(engine: str) -> dict:
    if engine not in ENGINES:
        return {"ok": False, "message": f"unknown engine '{engine}'", "engine": engine}

    pid = _get_tracked_pid(engine)
    if not pid:
        return {
            "ok": False,
            "message": f"no managed {ENGINES[engine]['label']} process to stop",
            "engine": engine,
        }

    killed = _terminate_tree(pid)
    _set_tracked_pid(engine, None)
    return {
        "ok": killed,
        "message": "stopped" if killed else "process not found (cleared tracking)",
        "engine": engine,
    }


def _terminate_tree(pid: int) -> bool:
    """Terminate a process and its children (the bash wrapper + ollama)."""
    try:
        import psutil
    except Exception:
        try:
            os.kill(pid, 15)
            return True
        except OSError:
            return False

    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False

    procs = parent.children(recursive=True)
    procs.append(parent)
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=5)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    return True


def engine_status() -> list[dict]:
    out: list[dict] = []
    for engine, meta in ENGINES.items():
        base_url = meta["base_url"]
        up = probe(base_url)
        pid = _get_tracked_pid(engine)
        if pid and not _pid_alive(pid):
            _set_tracked_pid(engine, None)
            pid = None
        out.append(
            {
                "engine": engine,
                "base_url": base_url,
                "up": up,
                "managed_pid": pid,
                "loaded_models": loaded_models(base_url) if up else [],
            }
        )
    return out


# --- model lifecycle (delegate to shared OllamaClient) ---------------------

def warmup_model(base_url: Optional[str] = None) -> dict:
    import main as brain
    from agent.storage import load_runtime_settings, resolve_model_tag

    brain.apply_runtime_settings(brain.client)
    settings = load_runtime_settings()
    target_url = (base_url or settings.ollama_base_url).rstrip("/")
    tags = brain.client.list_models(base_url=target_url, name_filter="aquila")
    resolved = resolve_model_tag(settings.ollama_model, tags) or settings.ollama_model
    brain.client.configure(base_url=target_url, model_name=resolved)
    ok, msg = brain.client.ensure_warmup(force=True)
    brain.apply_runtime_settings(brain.client)
    return {"ok": bool(ok), "message": msg}


def eject_model(base_url: Optional[str] = None, all_loaded: bool = False) -> dict:
    import main as brain

    brain.apply_runtime_settings(brain.client)
    if base_url:
        brain.client.base_url = base_url.rstrip("/")
    ok, msg = brain.client.eject_model(all_loaded=all_loaded)
    brain.apply_runtime_settings(brain.client)
    return {"ok": bool(ok), "message": msg}
