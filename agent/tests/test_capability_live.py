"""Optional live capability smoke (requires Ollama + GPU)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.mark.live
def test_capability_persona_build_smoke():
    """Short lore topic: finish within budget when Ollama is available."""
    from agent.core import get_agent

    agent = get_agent("default")
    ok, msg = agent.client.warmup()
    if not ok:
        pytest.skip(f"Ollama warmup failed: {msg}")

    task_name = "capability_smoke_lore"
    result = agent.run_unified_task(
        task_name,
        "Brief persona smoke: one paragraph character named Test Smoke, lore off.",
        "character_build",
        persona_research_lore=False,
    )
    assert result
    assert "Error" not in result[:80] or "✅" in result
