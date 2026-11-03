import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies.thinking_tiers import (
    micro_plan_act_num_predict_enabled,
    resolve_thinking_tier,
    should_run_reflect_pass,
)


def test_micro_structured_tier(monkeypatch):
    monkeypatch.delenv("AQUILA_ACT_TWO_PHASE_MICRO", raising=False)
    tier = resolve_thinking_tier(mode="code", micro_plan=True)
    assert tier.tier == "micro_structured"
    assert tier.allow_reflect_pass is False
    assert tier.force_act_think_disabled is True
    assert tier.act_num_predict == 1024


def test_capability_task_tier(monkeypatch):
    monkeypatch.delenv("AQUILA_REFLECT_ON_FAILURE", raising=False)
    tier = resolve_thinking_tier(mode="research", micro_plan=False)
    assert tier.tier == "capability_task"
    assert tier.allow_reflect_pass is True
    assert tier.reflect_on_failure_only is True


def test_reflect_on_failure_skips_when_act_ok(monkeypatch):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "1")
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "reflect")
    monkeypatch.delenv("AQUILA_REFLECT_ON_FAILURE", raising=False)
    assert should_run_reflect_pass(
        mode="research",
        micro_plan=False,
        parse_retries=0,
        last_act_needs_reflect=False,
    ) is False


def test_reflect_runs_when_act_failed(monkeypatch):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "1")
    monkeypatch.setenv("AQUILA_ENABLE_THINK", "1")
    monkeypatch.setenv("AQUILA_THINK_SURFACES", "reflect")
    monkeypatch.delenv("AQUILA_REFLECT_ON_FAILURE", raising=False)
    assert should_run_reflect_pass(
        mode="research",
        micro_plan=False,
        parse_retries=0,
        last_act_needs_reflect=True,
        model_name="aquila:latest",
    ) is True


def test_micro_plan_act_num_predict_harness_flag(monkeypatch):
    monkeypatch.delenv("AQUILA_SLOT_FILL", raising=False)
    monkeypatch.setenv("AQUILA_HARNESS_FORCE_MICRO_PLAN", "1")
    assert micro_plan_act_num_predict_enabled() is True
