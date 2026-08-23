"""Live tool-calling tests for aquila_qwopus (Qwopus Coder / agentic Qwen 3.5).

Requires stock Ollama on 11434 and model aquila_qwopus:
  .env: OLLAMA_MODEL=aquila_qwopus
  ./scripts/ollama-create-qwopus.sh

Run:
  cd agent && python -m pytest tests/test_live_qwopus_tools.py -m qwopus -v
"""
from __future__ import annotations

import json
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    OllamaClient,
    build_strict_schema,
    get_executable_tools,
    normalize_tool_calls_list,
    parse_agent_response,
    validate_tool_arguments,
    validate_tool_calls,
)
from agent.policies import resolve_thinking_policy

pytestmark = [pytest.mark.live, pytest.mark.qwopus]

_QWOPUS_MODEL = os.getenv("OLLAMA_MODEL", "aquila_qwopus").strip()
_PARSE_ATTEMPTS = int(os.getenv("AQUILA_QWOPUS_PARSE_ATTEMPTS", "3"))


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def _ollama_available() -> bool:
    try:
        return requests.get(f"{_base_url()}/api/tags", timeout=5).status_code == 200
    except Exception:
        return False


def _model_available(name: str) -> bool:
    try:
        r = requests.get(f"{_base_url()}/api/tags", timeout=5)
        r.raise_for_status()
        names = {m.get("name", "") for m in r.json().get("models", [])}
        return name in names or f"{name}:latest" in names or any(
            n == name or n.startswith(f"{name}:") for n in names
        )
    except Exception:
        return False


def _parse_live_schema_response(content: str, *, format_mode: str | None = None) -> dict:
    text = (content or "").strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    for candidate in (text, f"```json\n{text}"):
        parsed = parse_agent_response(candidate, format_mode=format_mode)
        if isinstance(parsed.get("tools"), list):
            return parsed
    return {}


def _schema_for_tool_names(tool_names: set[str]) -> dict:
    registry = get_executable_tools()
    subset = {k: v for k, v in registry.items() if k in tool_names}
    return build_strict_schema(subset)


def _assert_valid_tool_payload(parsed: dict, *, min_tools: int = 1) -> list[dict]:
    assert isinstance(parsed.get("reasoning"), str) and parsed["reasoning"].strip(), (
        "missing non-empty reasoning"
    )
    tools = parsed.get("tools")
    assert isinstance(tools, list), f"tools must be a list, got {type(tools)!r}"
    assert len(tools) >= min_tools, f"expected >={min_tools} tools, got {len(tools)}"

    normalized = normalize_tool_calls_list(tools)
    for i, tc in enumerate(tools):
        assert isinstance(tc, dict), (
            f"tool[{i}] must be {{name, arguments}} object, not string: {tc!r}"
        )
        assert "name" in tc, f"tool[{i}] missing name: {tc!r}"
        assert "arguments" in tc, f"tool[{i}] missing arguments: {tc!r}"
        assert "tool_name" not in tc, f"tool[{i}] uses illegal key tool_name"

    ok, err = validate_tool_calls(normalized)
    assert ok, f"validate_tool_calls: {err}"
    args_ok, args_err = validate_tool_arguments(normalized)
    assert args_ok, f"validate_tool_arguments: {args_err}"
    return normalized


def _chat_and_parse(
    client: OllamaClient,
    messages: list[dict],
    schema: dict,
    *,
    timeout: int = 180,
) -> tuple[dict, dict]:
    last_result: dict = {}
    last_parsed: dict = {}
    for attempt in range(_PARSE_ATTEMPTS):
        result = client.chat(
            messages,
            temperature=0.1,
            format=schema,
            stream=False,
            timeout=timeout,
        )
        content = result["message"]["content"]
        format_mode = result.get("format_mode_used")
        parsed = _parse_live_schema_response(content, format_mode=format_mode)
        last_result = result
        last_parsed = parsed
        if isinstance(parsed.get("tools"), list) and parsed.get("tools"):
            return result, parsed
        if attempt + 1 < _PARSE_ATTEMPTS:
            messages = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Your reply was not valid JSON with reasoning and tools array. "
                        "Each tool must be {\"name\": \"...\", \"arguments\": {...}}. "
                        "Try again."
                    ),
                },
            ]
    preview = (last_result.get("message") or {}).get("content", "")[:400]
    fmt = last_result.get("format_mode_used")
    raise AssertionError(
        f"failed to parse tools after {_PARSE_ATTEMPTS} attempts; "
        f"format_mode={fmt!r} keys={list(last_parsed.keys())!r} "
        f"content_preview={preview!r}"
    )


@pytest.fixture(scope="module", autouse=True)
def require_qwopus_model():
    model = os.getenv("OLLAMA_MODEL", "").lower()
    if "qwopus" not in model:
        pytest.skip(
            "Qwopus live tests require OLLAMA_MODEL containing 'qwopus' "
            "(e.g. aquila_qwopus on stock Ollama :11434)"
        )


@pytest.fixture(scope="module", autouse=True)
def require_qwopus_ollama():
    if not _ollama_available():
        pytest.skip(
            f"Ollama not reachable at {_base_url()} — run ./scripts/ollama-serve-stock.sh"
        )
    if not _model_available(_QWOPUS_MODEL):
        pytest.skip(
            f"Model {_QWOPUS_MODEL!r} not in ollama list — run ./scripts/ollama-create-qwopus.sh"
        )


@pytest.fixture(scope="module")
def qwopus_client() -> OllamaClient:
    client = OllamaClient()
    assert "qwopus" in client.model_name.lower(), (
        f"expected qwopus model, got {client.model_name!r}"
    )
    os.environ["AQUILA_SKIP_WARMUP"] = "0"
    ok, msg = client.ensure_warmup()
    if not ok:
        pytest.skip(f"warmup failed: {msg}")
    return client


def test_qwopus_thinking_policy_enabled(monkeypatch):
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "chat")
    p = resolve_thinking_policy(surface="chat", model_name="aquila_qwopus")
    assert p.think is True


def test_qwopus_client_uses_configured_model(qwopus_client: OllamaClient):
    assert "qwopus" in qwopus_client.model_name.lower()
    assert qwopus_client.model_name == _QWOPUS_MODEL


def test_qwopus_chat_thinking_and_content(qwopus_client: OllamaClient):
    policy = resolve_thinking_policy(surface="chat", model_name=qwopus_client.model_name)
    assert policy.think is True
    result = qwopus_client.chat(
        [{"role": "user", "content": "What is 2+2? Reply with the number only."}],
        temperature=0.2,
        stream=False,
        timeout=180,
        surface="chat",
    )
    msg = result.get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = (msg.get("thinking") or "").strip()
    assert content or thinking, "expected content or native thinking from qwopus chat"
    if thinking:
        assert len(thinking) > 0


def test_qwopus_strict_schema_no_think_http_400(qwopus_client: OllamaClient):
    """Structured schema pass must disable thinking (no HTTP 400)."""
    tools = {k: get_executable_tools()[k] for k in ("list_directory",)}
    schema = build_strict_schema(tools)
    policy = resolve_thinking_policy(
        surface="act",
        model_name=qwopus_client.model_name,
        has_format_schema=True,
    )
    assert policy.think is False
    result = qwopus_client.chat(
        [
            {
                "role": "system",
                "content": "Output JSON only with reasoning and tools.",
            },
            {
                "role": "user",
                "content": "List the current directory with list_directory path '.'.",
            },
        ],
        temperature=0.1,
        format=schema,
        stream=False,
        timeout=180,
        surface="act",
    )
    assert "message" in result
    assert result["message"].get("content") is not None


def test_qwopus_strict_schema_list_directory(qwopus_client: OllamaClient):
    tools = {k: get_executable_tools()[k] for k in ("list_directory",)}
    schema = build_strict_schema(tools)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aquila. Output JSON only with keys reasoning and tools. "
                "Each tool must be {\"name\": \"...\", \"arguments\": {...}}."
            ),
        },
        {
            "role": "user",
            "content": "List the current directory. Use list_directory with path '.'.",
        },
    ]
    result, parsed = _chat_and_parse(qwopus_client, messages, schema)
    tools_out = _assert_valid_tool_payload(parsed)
    names = [t["name"] for t in tools_out]
    assert "list_directory" in names, (
        f"expected list_directory in {names!r}; "
        f"format_mode={result.get('format_mode_used')!r}"
    )


def test_qwopus_strict_schema_save_research_note(qwopus_client: OllamaClient):
    schema = _schema_for_tool_names({"save_research_note"})
    messages = [
        {
            "role": "system",
            "content": (
                "Output JSON with reasoning and tools. "
                "Call save_research_note exactly once with task_name and gathered_data."
            ),
        },
        {
            "role": "user",
            "content": (
                'task_name: "qwopus_smoke"\n'
                'gathered_data: "Qwopus live test note."'
            ),
        },
    ]
    result, parsed = _chat_and_parse(qwopus_client, messages, schema)
    tools = _assert_valid_tool_payload(parsed)
    assert all(t.get("name") == "save_research_note" for t in tools)
    args = tools[0].get("arguments") or {}
    assert str(args.get("task_name", "")).strip()
    assert str(args.get("gathered_data", "")).strip()


def test_qwopus_routed_tools_subset(qwopus_client: OllamaClient):
    allowed = {
        "save_research_note",
        "read_all_research_notes",
        "mark_objective_complete",
    }
    schema = _schema_for_tool_names(allowed)
    messages = [
        {
            "role": "system",
            "content": (
                "Output JSON only. Call save_research_note once, then "
                "mark_objective_complete. Only use schema-allowed tools."
            ),
        },
        {
            "role": "user",
            "content": (
                "Ingest: Qwopus routes tools correctly. task_name: qwopus_routed_test"
            ),
        },
    ]
    result, parsed = _chat_and_parse(qwopus_client, messages, schema)
    tools = _assert_valid_tool_payload(parsed)
    names = {t["name"] for t in tools}
    assert names <= allowed, (
        f"unexpected tools outside allowlist: {names!r}; "
        f"format_mode={result.get('format_mode_used')!r}"
    )
    assert names
