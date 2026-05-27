import os

from context_budget import resolve_context_profile
from context_manager import (
    build_loop_messages,
    estimate_messages_tokens,
    on_step_advance,
)


def test_estimate_messages_tokens():
    msgs = [{"role": "user", "content": "x" * 400}]
    assert estimate_messages_tokens(msgs) >= 100


def test_build_loop_messages_includes_summary():
    profile = resolve_context_profile(model_name="aquila-tq-96k")
    msgs = build_loop_messages(
        system_prompt="sys",
        rolling_summary="# Summary\nDid step 1",
        step_entry=[{"role": "user", "content": "step entry"}],
        conversation_history=[],
        user_message={"role": "user", "content": "do work"},
        profile=profile,
    )
    joined = " ".join(m["content"] if isinstance(m.get("content"), str) else "" for m in msgs)
    assert "WORKSPACE SUMMARY" in joined
    assert "do work" in joined


def test_build_loop_messages_enforces_total_prompt_cap(monkeypatch):
    monkeypatch.delenv("AQUILA_CONTEXT_TIER", raising=False)
    profile = resolve_context_profile(model_name="aquila", num_ctx_override=8192)
    monkeypatch.setenv("AQUILA_TOTAL_PROMPT_TOKEN_CAP", "2000")
    big_notes = "n" * 200_000
    step_entry = [
        {
            "role": "user",
            "content": (
                f"--- SCRATCHPAD (prior steps) ---\n{big_notes}\n--- END SCRATCHPAD ---"
            ),
        }
    ]
    msgs = build_loop_messages(
        system_prompt="sys",
        rolling_summary="",
        step_entry=step_entry,
        conversation_history=[],
        user_message={"role": "user", "content": "do work"},
        profile=profile,
    )
    assert estimate_messages_tokens(msgs) <= 2500


def test_on_step_advance_compact_clears_history():
    # Ensure tier isn't forced by workspace env (repo .env uses standard).
    os.environ.pop("AQUILA_CONTEXT_TIER", None)
    profile = resolve_context_profile(model_name="aquila", num_ctx_override=8192)
    history = [
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "Tool Outputs:\nb"},
    ]

    class FakeMem:
        def save_workspace_summary_row(self, *a, **k):
            pass

    on_step_advance(
        conversation_history=history,
        instance_id="default",
        task_name="t1",
        advance_summary="done",
        client=None,
        memory=FakeMem(),
        profile=profile,
    )
    assert history == []
