import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import resolve_context_profile
from agent.policies import should_proactive_summarize, should_force_summarize


def test_proactive_summarize_only_on_max_tier(monkeypatch):
    monkeypatch.setenv("AQUILA_CONTEXT_TIER", "max")
    profile = resolve_context_profile("aquila-tq-96k")
    assert profile.tier == "max"
    cap = profile.in_step_token_cap
    assert should_proactive_summarize(profile, int(cap * 0.55)) is True
    assert should_proactive_summarize(profile, int(cap * 0.4)) is False


def test_force_summarize_above_cap():
    profile = resolve_context_profile("aquila-tq-32k")
    cap = profile.in_step_token_cap
    assert should_force_summarize(profile, cap + 1) is True
    assert should_proactive_summarize(profile, cap + 1) is False
