import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    act_two_phase_enabled,
    auto_advance_milestones_enabled,
    dynamic_loop_enabled,
    plan_num_predict,
    task_episode_max,
    task_web_search_cap,
)


def test_dynamic_loop_defaults_off(monkeypatch):
    monkeypatch.delenv("AQUILA_DYNAMIC_LOOP", raising=False)
    assert dynamic_loop_enabled() is False


def test_dynamic_loop_on(monkeypatch):
    monkeypatch.setenv("AQUILA_DYNAMIC_LOOP", "1")
    assert dynamic_loop_enabled() is True


def test_task_episode_max_floor(monkeypatch):
    monkeypatch.setenv("AQUILA_TASK_EPISODE_MAX", "3")
    assert task_episode_max() >= 8


def test_auto_advance_default_false(monkeypatch):
    monkeypatch.delenv("AQUILA_AUTO_ADVANCE_MILESTONES", raising=False)
    assert auto_advance_milestones_enabled() is False


def test_web_search_cap(monkeypatch):
    monkeypatch.setenv("AQUILA_TASK_WEB_SEARCH_CAP", "5")
    assert task_web_search_cap() == 5


def test_act_two_phase_defaults_on(monkeypatch):
    monkeypatch.delenv("AQUILA_ACT_TWO_PHASE", raising=False)
    assert act_two_phase_enabled() is True


def test_act_two_phase_off(monkeypatch):
    monkeypatch.setenv("AQUILA_ACT_TWO_PHASE", "0")
    assert act_two_phase_enabled() is False


def test_plan_num_predict_default(monkeypatch):
    monkeypatch.delenv("AQUILA_PLAN_NUM_PREDICT", raising=False)
    assert plan_num_predict() == 2048


def test_plan_num_predict_env(monkeypatch):
    monkeypatch.setenv("AQUILA_PLAN_NUM_PREDICT", "1024")
    assert plan_num_predict() == 1024
