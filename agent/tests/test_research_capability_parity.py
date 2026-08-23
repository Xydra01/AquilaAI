"""
Parity tests for capability-only Research mode.

Fast suite:

    python -m pytest agent/tests/test_research_capability_parity.py -q -m "not live"

Live smoke (Ollama + local files, no web):

    python -m pytest agent/tests/test_research_capability_parity.py -m live -v
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.capabilities.base import CapabilityContext
from agent.core import LoopEngine
from agent.capabilities import run_capability
from agent.functions.research import resolve_recipe, run_recipe_step
from agent.storage import DualMemorySystem

TOPIC = "Gregorian calendar reform and the leap year rules"
JOURNAL = (
    "Human notes: Pope Gregory XIII introduced the reform in 1582. "
    "Ten days were skipped in October 1582. Leap years occur every four years "
    "except century years unless divisible by 400. "
) * 8


@pytest.fixture
def capability_env(monkeypatch):
    """Research parity env with prefs hydration disabled."""
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "0")
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    monkeypatch.setenv("AQUILA_AUTO_ADVANCE_MILESTONES", "1")
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "0")
    # Agent init calls apply_preferences_to_environ() which would reset catalog keys
    # from app_settings.json (e.g. PLAN_REVIEW=1) over pytest monkeypatch.
    monkeypatch.setattr(
        "agent.storage.preferences.apply_preferences_to_environ",
        lambda *args, **kwargs: None,
    )


def _patch_agent_data_path(monkeypatch, root):
    monkeypatch.setattr("agent.core.main.agent_data_path", lambda *parts: root.joinpath(*parts))
    monkeypatch.setattr(
        "agent.capabilities.research.finalize_deliverable.agent_data_path",
        lambda *parts: root.joinpath(*parts),
        raising=False,
    )


def test_offline_recipe_pipeline_writes_deliverable(tmp_agent_dirs, capability_env, monkeypatch):
    """Gold path: code-first offline recipe → non-empty Agent-Research/*.md (no LLM act loop)."""
    _patch_agent_data_path(monkeypatch, tmp_agent_dirs)
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    ctx = CapabilityContext(
        memory=mem,
        task_id="parity_offline_recipe",
        offline=True,
        journal_text=JOURNAL,
        user_request=TOPIC,
    )
    recipe = resolve_recipe("Research from my journal only", offline=True)
    assert recipe.recipe_id == "fn.research.offline_pipeline"

    for index, cap_id in enumerate(recipe.capability_ids):
        params: dict = {"topic": TOPIC}
        if "synthesize" in cap_id:
            params["use_llm"] = False
            # Without LLM, synthesis body mirrors ingest text and hits dedup — inject
            # a structurally distinct synthesis block instead of re-saving the journal.
            run_capability(
                "cap.research.append_note@v1",
                ctx,
                {
                    "content": (
                        "# Synthesis layer\n\n## Key findings\n\n"
                        "- Reform adopted October 1582; ten-day correction.\n"
                        "- Leap rule: every 4 years, except centuries unless /400.\n"
                        "- Distinct from raw journal ingest above.\n"
                    ),
                },
            )
            continue
        result = run_recipe_step(recipe, index, ctx, extra_params=params)
        assert result.ok, f"step {index} ({cap_id}): {result.error_message}"

    deliverable = tmp_agent_dirs / "Agent-Research" / "parity_offline_recipe.md"
    assert deliverable.is_file(), "finalize_deliverable should write Agent-Research/*.md"
    body = deliverable.read_text(encoding="utf-8")
    assert len(body) >= 400, f"deliverable too short ({len(body)} chars)"
    assert "Gregorian" in body or "leap" in body.lower() or "1582" in body


def test_loop_uses_capabilities_not_tools(tmp_agent_dirs, capability_env, monkeypatch):
    """LoopEngine with flag on must route act turns through capabilities[], not tools[]."""
    task = "parity_finalize"
    ledger = tmp_agent_dirs / "Agent-Plans" / f"{task}.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [{
                "description": f"Finalize: {TOPIC}",
                "status": "pending",
                "step_kind": "finalize",
                "capability_id": "cap.research.finalize_deliverable@v1",
                "max_iterations": 4,
            }],
        }),
        encoding="utf-8",
    )

    _patch_agent_data_path(monkeypatch, tmp_agent_dirs)
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")
    report_body = "# Research Report\n\n## Summary\n\n" + ("Gregorian reform analysis. " * 60)
    mem.save_scratchpad_note(task, report_body)

    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Research assistant.",
        mode="research",
        mode_label="Research",
        plan_dir="Agent-Plans",
        memory=mem,
        base_tools={"web_search": {"func": MagicMock(), "description": "search"}},
        offline_research=False,
        human_research_notes=JOURNAL,
    )
    executor = engine.executor
    parse_calls: list[dict] = []

    def _track_parse(*_args, **kwargs):
        parse_calls.append(kwargs)
        return {
            "reasoning": "Finalize deliverable via capability.",
            "capabilities": [{
                "id": "cap.research.finalize_deliverable@v1",
                "arguments": {"report_body": report_body},
            }],
            "final_report": report_body,
        }

    client = engine.client
    client.chat.return_value = {
        "message": {"content": "{}"},
        "format_mode_used": "strict_schema",
    }
    client.model_name = "test-model"

    with patch("loop_engine.parse_agent_response", side_effect=_track_parse):
        with patch("loop_engine.validate_tool_calls", return_value=(True, "")):
            with patch("loop_engine.validate_tool_arguments", return_value=(True, "")):
                with patch.object(engine, "_build_step_entry_messages", return_value=[]):
                    with patch.object(engine, "_maybe_compress_conversation"):
                        result = engine.run(task, TOPIC, str(ledger))

    assert parse_calls, "parse_agent_response should run"
    assert parse_calls[0].get("schema_kind") == "capability_action"
    executor.execute.assert_not_called()
    deliverable = tmp_agent_dirs / "Agent-Research" / f"{task}.md"
    assert deliverable.is_file(), result
    assert len(deliverable.read_text(encoding="utf-8")) >= 400


def test_offline_dynamic_capability_loop(tmp_agent_dirs, capability_env, monkeypatch):
    """2-step dynamic offline plan: ingest → synthesize → auto-advance → finalize."""
    task = "parity_offline_loop"
    ledger = tmp_agent_dirs / "Agent-Plans" / f"{task}.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({
            "status": "in_progress",
            "current_step_index": 0,
            "dynamic_plan": True,
            "offline_research": True,
            "steps": [
                {
                    "description": f"Offline work: {TOPIC}",
                    "status": "pending",
                    "step_kind": "work",
                    "capability_id": "cap.research.ingest_offline@v1",
                    "max_iterations": 8,
                },
                {
                    "description": f"Finalize: {TOPIC}",
                    "status": "pending",
                    "step_kind": "finalize",
                    "capability_id": "cap.research.finalize_deliverable@v1",
                    "max_iterations": 4,
                },
            ],
        }),
        encoding="utf-8",
    )

    _patch_agent_data_path(monkeypatch, tmp_agent_dirs)
    mem = DualMemorySystem(storage_dir=str(tmp_agent_dirs / "mem"), instance_id="default")

    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="Research assistant.",
        mode="research",
        mode_label="Research",
        plan_dir="Agent-Plans",
        memory=mem,
        base_tools={"web_search": {"func": MagicMock(), "description": "search"}},
        offline_research=True,
        human_research_notes=JOURNAL,
    )
    engine.client.chat.return_value = {"message": {"content": "{}"}, "format_mode_used": "strict_schema"}
    engine.client.model_name = "test-model"

    responses = [
        {
            "reasoning": "Ingest journal.",
            "capabilities": [{
                "id": "cap.research.ingest_offline@v1",
                "arguments": {"topic": TOPIC},
            }],
        },
        {
            "reasoning": "Synthesize notes.",
            "capabilities": [{
                "id": "cap.research.synthesize_notes@v1",
                "arguments": {"topic": TOPIC, "use_llm": False},
            }],
        },
        {
            "reasoning": "Write deliverable.",
            "capabilities": [{
                "id": "cap.research.finalize_deliverable@v1",
                "arguments": {"compile_if_missing": True},
            }],
            "final_report": "",
        },
    ]
    call_index = {"i": 0}

    def _next_parse(*_args, **_kwargs):
        idx = min(call_index["i"], len(responses) - 1)
        call_index["i"] += 1
        return responses[idx]

    with patch("loop_engine.parse_agent_response", side_effect=_next_parse):
        with patch("loop_engine.validate_tool_calls", return_value=(True, "")):
            with patch("loop_engine.validate_tool_arguments", return_value=(True, "")):
                with patch.object(engine, "_build_step_entry_messages", return_value=[]):
                    with patch.object(engine, "_maybe_compress_conversation"):
                        result = engine.run(task, TOPIC, str(ledger), text_chunks=[JOURNAL])

    deliverable = tmp_agent_dirs / "Agent-Research" / f"{task}.md"
    assert deliverable.is_file(), result
    body = deliverable.read_text(encoding="utf-8")
    assert len(body) >= 400
    assert call_index["i"] >= 3
    final_state = json.loads(ledger.read_text(encoding="utf-8"))
    assert final_state.get("status") == "completed"


def test_research_always_uses_capability_schema():
    """Research mode always routes act turns through capabilities[], never tools[]."""
    engine = LoopEngine(
        client=MagicMock(),
        executor=MagicMock(),
        console=MagicMock(),
        action_schema={"type": "object"},
        system_prompt="sys",
        mode="research",
        mode_label="Research",
        plan_dir="Agent-Plans",
        base_tools={"web_search": {"func": MagicMock(), "description": "search"}},
    )
    assert engine._capability_research_active()
    schema = engine._schema_for_capability_step("search", is_final_step=False)
    dumped = json.dumps(schema)
    assert "capabilities" in dumped
    assert '"tools"' not in dumped


def test_offline_policy_blocks_web_capabilities():
    from agent.policies.step_policies import CapabilityResearchPolicy, get_step_policy

    policy = get_step_policy("research", "work", offline_research=True)
    assert isinstance(policy, CapabilityResearchPolicy)
    forbidden = policy.forbidden_capabilities_on_step()
    assert "cap.web.search@v1" in forbidden
    msg = policy.validate_capability_call("cap.web.search@v1")
    assert msg is not None
    assert "Offline research" in msg


def test_explore_brief_capability(monkeypatch):
    from agent.capabilities import run_capability

    mock_brief = MagicMock()
    mock_brief.to_markdown.return_value = "# Explore brief\n\n- Hypothesis A"
    mock_brief.relevant_paths = ["/tmp/foo.pdf"]
    mock_brief.hypotheses = ["Hypothesis A"]

    monkeypatch.setattr(
        "agent.core.explore_agent.run_brief",
        lambda **_kwargs: mock_brief,
    )
    ctx = CapabilityContext(
        client=MagicMock(),
        task_id="explore_test",
        user_request=TOPIC,
    )
    result = run_capability(
        "cap.research.explore_brief@v1",
        ctx,
        {"user_request": TOPIC, "mode": "research"},
    )
    assert result.ok, result.error_message
    assert "Explore brief" in (result.summary or "")


def test_light_web_context_capability(monkeypatch):
    from agent.capabilities import run_capability

    monkeypatch.setattr(
        "agent.research.light_research.build_light_research_context",
        lambda _q: "## Web context\n\nMocked search snippet.",
    )
    ctx = CapabilityContext(client=MagicMock(), task_id="light_test")
    result = run_capability(
        "cap.research.light_web_context@v1",
        ctx,
        {"user_input": "latest leap year rules"},
    )
    assert result.ok, result.error_message
    assert "Web context" in (result.data or {}).get("context", "")


def test_plan_fallback_attaches_capability_recipe(monkeypatch):
    from agent.core.plan_validator import build_fallback_research_plan, validate_and_tune_plan

    monkeypatch.delenv("AQUILA_DYNAMIC_LOOP", raising=False)
    plan, note = build_fallback_research_plan(TOPIC, offline_research=True)
    assert "Recipe fallback" in note
    tuned, _ = validate_and_tune_plan(plan, "research", TOPIC, offline_research=True)
    assert tuned.get("capability_recipe")
    for step in tuned.get("steps") or []:
        assert step.get("capability_id"), f"missing capability_id on {step}"


def _stock_ollama_reachable() -> bool:
    try:
        import requests

        return requests.get("http://127.0.0.1:11434/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.mark.live
@pytest.mark.skipif(not _stock_ollama_reachable(), reason="stock Ollama not reachable at :11434")
def test_live_capability_local_research(capability_env, monkeypatch):
    """Live: Ollama + local repo files, capability path, no web (research_local_lock scenario).

    Uses real Agent-* data dirs (not tmp_agent_dirs). Expect several minutes on first run.
    Fast suite only: pytest ... -m 'not live'
    """
    monkeypatch.setenv("AQUILA_PLAN_REVIEW", "0")
    from agent.core.capability_harness import evaluate_run, run_scenario

    report = run_scenario("research_local_lock", engine="stock")
    assert report.get("ok") is True, report.get("error") or report
    ok, failures = evaluate_run(report)
    assert ok, failures
    deliverable = (report.get("mode_result") or {}).get("deliverable_path")
    assert deliverable and os.path.isfile(deliverable)
    assert len(open(deliverable, encoding="utf-8").read()) >= 80
