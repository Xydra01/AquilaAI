import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from episode_tracker import (
    StepRunState,
    episode_count_from_history,
    should_inject_checkpoint_nudge,
)


def test_episode_count_from_history():
    hist = [
        {"role": "assistant", "_counts_as_episode": True},
        {"role": "user", "content": "Tool Outputs:"},
        {"role": "assistant", "_counts_as_episode": False},
    ]
    assert episode_count_from_history(hist) == 1


def test_format_progress():
    s = StepRunState(1, 4, "code", 8, episode_count=2)
    assert "Step 2/4" in s.format_progress()
    assert "Episode 3/8" in s.format_progress()


def test_checkpoint_nudge():
    s = StepRunState(0, 4, "code", 10, episode_count=8)
    assert should_inject_checkpoint_nudge(s) is True
