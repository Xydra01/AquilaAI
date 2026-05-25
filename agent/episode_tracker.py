"""Per-plan-step episode budget (toolful LLM turns), not reflect ticks."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepRunState:
    plan_step_index: int
    total_steps: int
    step_kind: str
    max_episodes: int
    episode_count: int = 0
    loop_tick: int = 0
    grace_used: bool = False
    tools_succeeded: set[str] = field(default_factory=set)

    def format_progress(self) -> str:
        return (
            f"Step {self.plan_step_index + 1}/{self.total_steps} ({self.step_kind}) · "
            f"Episode {self.episode_count + 1}/{self.max_episodes}"
        )

    def at_episode_limit(self) -> bool:
        return self.episode_count >= self.max_episodes

    def can_apply_grace(self) -> bool:
        return not self.grace_used and bool(self.tools_succeeded)

    def apply_grace(self, step: dict) -> int:
        """Extend max_episodes by 2 once; persist to step dict. Returns new max."""
        self.grace_used = True
        new_max = int(step.get("max_iterations", self.max_episodes)) + 2
        step["max_iterations"] = new_max
        self.max_episodes = new_max
        return new_max


def episode_count_from_history(conversation_history: list[dict]) -> int:
    """Count assistant turns marked as consuming an episode budget."""
    return sum(
        1
        for msg in conversation_history
        if msg.get("role") == "assistant" and msg.get("_counts_as_episode", False)
    )


def should_inject_checkpoint_nudge(state: StepRunState) -> bool:
    """Optional stall nudge when budget mostly consumed."""
    if state.max_episodes <= 0:
        return False
    ratio = state.episode_count / state.max_episodes
    return ratio >= 0.8 and state.episode_count < state.max_episodes
