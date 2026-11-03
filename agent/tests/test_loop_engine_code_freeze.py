"""Phase 3: LoopEngine is frozen for code mode."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.core.loop_engine import LoopEngine


def test_loop_engine_rejects_code_mode_on_init():
    with pytest.raises(RuntimeError, match="code_agent.run_tool_session"):
        LoopEngine(
            client=MagicMock(),
            executor=MagicMock(),
            console=MagicMock(),
            action_schema={},
            system_prompt="x",
            mode="code",
            mode_label="Code",
            plan_dir=".",
        )


def test_capability_act_modes_excludes_code():
    assert "code" not in LoopEngine.CAPABILITY_ACT_MODES
    assert "research" in LoopEngine.CAPABILITY_ACT_MODES
