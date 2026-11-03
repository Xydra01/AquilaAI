"""Prompt assembly tests for RunState integration."""
from __future__ import annotations

from agent.core.loop_engine import LoopEngine
from agent.core.run_state import TaskRunContext
from agent.policies.context_budget import resolve_context_profile
from agent.policies.context_manager import build_loop_messages


def test_build_loop_messages_run_state_block():
    profile = resolve_context_profile(num_ctx_override=32768)
    block = "--- RUN STATE ---\nprogress\n--- END RUN STATE ---"
    msgs = build_loop_messages(
        system_prompt="sys",
        rolling_summary="",
        step_entry=[],
        conversation_history=[],
        user_message={"role": "user", "content": "hi"},
        profile=profile,
        run_state_block=block,
    )
    text = msgs[1]["content"]
    assert "RUN STATE" in text
    assert "WORKSPACE SUMMARY" not in text


def test_loop_engine_assemble_uses_run_state(monkeypatch):
    monkeypatch.setenv("AQUILA_RUN_STATE_ENABLED", "1")
    engine = LoopEngine.__new__(LoopEngine)
    engine.workspace_summary = ""
    engine._run_ctx = TaskRunContext.bootstrap(
        task_id="t",
        mode="code",
        goal="Build something",
    )
    engine._run_ctx.run_digest = "- did setup"
    msgs = engine._assemble_loop_messages(
        system_prompt="sys",
        step_entry=[],
        conversation_history=[],
        user_message={"role": "user", "content": "go"},
        profile=resolve_context_profile(num_ctx_override=32768),
        include_full_goal=True,
    )
    blob = "\n".join(
        m["content"] for m in msgs if isinstance(m.get("content"), str)
    )
    assert "RUN STATE" in blob
    assert "did setup" in blob


def test_render_think_anchor_shows_buffer_and_exists_hint():
    from agent.core.run_state import CapabilityCheckpoint, TaskRunContext

    ctx = TaskRunContext.bootstrap(task_id="t", mode="code", goal="habit tracker")
    ctx.ground_truth = {
        "buffer_files": ["tests/test_habit.py", "habit.py"],
        "setup_done": True,
    }
    ctx.last_capability = CapabilityCheckpoint(
        cap_id="cap.dev.create_file@v1",
        ok=False,
        summary="OS BLOCK: tests/test_habit.py already exists",
    )
    anchor = ctx.render_think_anchor()
    assert "tests/test_habit.py" in anchor
    assert "edit_apply" in anchor.lower() or "read_region" in anchor.lower()


def test_digest_for_prompt_strips_bootstrap_prefix():
    from agent.core.run_state import TaskRunContext
    from agent.policies.context_budget import resolve_context_profile

    ctx = TaskRunContext.bootstrap(task_id="t", mode="code", goal="g")
    ctx.run_digest = (
        "[Bootstrapped from workspace summary]\n# old\n"
        "- [cap.dev.project_setup@v1] OK\n"
        "- [cap.dev.create_file@v1] OK: created test\n"
    )
    profile = resolve_context_profile(num_ctx_override=32768)
    digest = ctx._digest_for_prompt(profile)
    assert "[Bootstrapped" not in digest
    assert "create_file" in digest
