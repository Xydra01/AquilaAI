"""Live structured-output success rate (requires local Ollama + OLLAMA_MODEL)."""
from __future__ import annotations

import inspect
import os
import sys
import time

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    OllamaClient,
    assemble_agent_response,
    build_strict_schema,
    get_executable_tools,
    normalize_tool_calls_list,
    parse_agent_response,
    validate_tool_arguments,
    validate_tool_calls,
)

pytestmark = pytest.mark.live

_TRIALS = int(os.getenv("AQUILA_LIVE_STRUCTURED_TRIALS", "20"))
_ATTEMPTS = int(os.getenv("AQUILA_LIVE_STRUCTURED_ATTEMPTS", "4"))
_PAUSE_SEC = float(os.getenv("AQUILA_LIVE_STRUCTURED_PAUSE_SEC", "2"))
_KEEP_ALIVE = os.getenv("AQUILA_LIVE_KEEP_ALIVE", "30m")
_INFRA_RETRY_SLEEP = float(os.getenv("AQUILA_LIVE_INFRA_RETRY_SLEEP_SEC", "8"))


def _tool_docs(subset: dict) -> str:
    lines: list[str] = []
    for name, meta in subset.items():
        desc = str(meta.get("description", "")).strip().split("\n")[0]
        sig = inspect.signature(meta["func"])
        args = [
            p
            for p, p_info in sig.parameters.items()
            if p_info.kind
            not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        ]
        lines.append(f"- `{name}({', '.join(args)})`: {desc}")
    return "\n".join(lines)


def _live_system_prompt(subset: dict) -> str:
    """Compact system prompt — full get_base_context is ~700 tok and slows long runs."""
    return (
        "You are Aquila. The host executes every tool in your JSON `tools` array on the "
        "real filesystem. Output ONLY one JSON object with `reasoning` (string) and "
        "`tools` (array). Never claim you lack file or tool access.\n\n"
        f"Tools:\n{_tool_docs(subset)}"
    )


def _transient_failure(fmt: str, body: str, note: str = "") -> bool:
    if fmt == "error":
        return True
    blob = f"{body} {note}".lower()
    return any(
        s in blob
        for s in (
            "timeout",
            "vram",
            "forcibly severed",
            "read_timeout",
        )
    )


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def _ollama_up() -> bool:
    try:
        return requests.get(f"{_base_url()}/api/tags", timeout=5).status_code == 200
    except Exception:
        return False


def _model_available(name: str) -> bool:
    try:
        r = requests.get(f"{_base_url()}/api/tags", timeout=5)
        r.raise_for_status()
        names = {m.get("name", "") for m in r.json().get("models", [])}
        return any(n == name or n.startswith(f"{name}:") for n in names)
    except Exception:
        return False


def _run_one_trial(
    client: OllamaClient,
    *,
    system: str,
    user_content: str,
    schema: dict,
    names: frozenset[str],
    subset: dict,
) -> tuple[bool, str, bool]:
    """
    Returns (trial_ok, last_note, got_structured_response).
    got_structured_response is True when Ollama returned strict_schema/json_object.
    """
    last_note = ""
    got_structured = False
    for attempt in range(_ATTEMPTS):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        result = client.chat(
            messages,
            temperature=0.1,
            format=schema,
            stream=False,
            keep_alive=_KEEP_ALIVE,
        )
        raw = result.get("message", {}).get("content", "") or ""
        fmt = result.get("format_mode_used", "") or "unknown"
        if fmt not in ("strict_schema", "json_object"):
            last_note = f"format={fmt!r} body={raw[:120]!r}"
            if _transient_failure(fmt, raw, last_note) and attempt + 1 < _ATTEMPTS:
                time.sleep(_INFRA_RETRY_SLEEP)
                continue
            return False, last_note, got_structured

        got_structured = True
        text = assemble_agent_response("", raw)
        parsed = parse_agent_response(
            text,
            quiet=True,
            tool_names=names,
            format_mode=fmt,
            registry=subset,
        )
        tool_list = parsed.get("tools") if isinstance(parsed, dict) else None
        if not tool_list:
            last_note = f"empty tools fmt={fmt} body={text[:160]!r}"
            if attempt + 1 < _ATTEMPTS:
                time.sleep(_INFRA_RETRY_SLEEP)
                continue
            return False, last_note, got_structured

        tcs = normalize_tool_calls_list(tool_list)
        s_ok, s_err = validate_tool_calls(tcs, valid_names=set(names))
        a_ok, a_err = validate_tool_arguments(tcs, registry=subset)
        if s_ok and a_ok:
            return True, "", got_structured

        last_note = f"schema={s_err or 'ok'} args={a_err or 'ok'} tools={tcs!r}"
        if attempt + 1 < _ATTEMPTS:
            time.sleep(_INFRA_RETRY_SLEEP)
            continue

    return False, last_note, got_structured


@pytest.fixture
def structured_client():
    if not _ollama_up():
        pytest.fail(
            f"Ollama not reachable at {_base_url()}. "
            "Start the server (e.g. ollama-serve-turboquant-port.ps1 or tray app) "
            "then re-run."
        )
    model = os.getenv("OLLAMA_MODEL", "aquila").strip()
    if not _model_available(model):
        pytest.fail(f"Model {model!r} not found on Ollama at {_base_url()}")
    return OllamaClient()


def test_live_structured_success_rate(structured_client):
    """
    Target >=99% parse+schema success on structured turns (strict or json_object).

    Do NOT use assistant JSON prefill with strict json_schema — models return prose.
  Long runs use keep_alive + pauses so Ollama does not evict the model mid-suite.
    """
    tools = get_executable_tools()
    subset = {k: tools[k] for k in ("list_directory", "save_research_note") if k in tools}
    schema = build_strict_schema(subset)
    names = frozenset(subset.keys())
    ok_count = 0
    structured_trials = 0
    failures: list[str] = []
    infra_failures: list[str] = []

    system = _live_system_prompt(subset)
    user_template = (
        "Trial {n}: Output ONLY one JSON object. Call list_directory once with "
        'arguments {{"path": "."}}.'
    )

    # Warmup: load model once before counting trials (reduces trial-1 cold start).
    _run_one_trial(
        structured_client,
        system=system,
        user_content="Warmup: JSON with reasoning and tools calling list_directory on '.'.",
        schema=schema,
        names=names,
        subset=subset,
    )
    if _PAUSE_SEC > 0:
        time.sleep(_PAUSE_SEC)

    for i in range(_TRIALS):
        trial_ok, last_note, got_structured = _run_one_trial(
            structured_client,
            system=system,
            user_content=user_template.format(n=i + 1),
            schema=schema,
            names=names,
            subset=subset,
        )
        if got_structured:
            structured_trials += 1
        if trial_ok:
            ok_count += 1
        elif _transient_failure("error", "", last_note) or last_note.startswith("format='error'"):
            infra_failures.append(f"trial {i + 1}: {last_note}")
        else:
            failures.append(f"trial {i + 1}: {last_note}")

        if _PAUSE_SEC > 0 and i + 1 < _TRIALS:
            time.sleep(_PAUSE_SEC)

    if structured_trials == 0:
        pytest.fail(
            "No trials used strict_schema or json_object — check Ollama / model / schema. "
            f"Sample failures: {failures[:5]} {infra_failures[:3]}"
        )

    infra_cap = max(1, _TRIALS // 20)
    if len(infra_failures) > infra_cap:
        pytest.fail(
            f"Too many infrastructure failures ({len(infra_failures)}/{_TRIALS}, cap={infra_cap}). "
            "Restart TurboQuant, free GPU memory, then re-run. "
            f"Samples: {infra_failures[:5]}"
        )

    rate = ok_count / structured_trials
    assert rate >= 0.99, (
        f"structured success {ok_count}/{structured_trials} ({rate:.1%}) below 99% "
        f"for model {structured_client.model_name} @ {_base_url()}. "
        f"Failures: {failures[:8]}"
    )
