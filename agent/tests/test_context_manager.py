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


def test_on_step_advance_compact_clears_history():
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
