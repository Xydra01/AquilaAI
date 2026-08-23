"""Harness scenario registry smoke tests."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import get_scenario, list_scenarios
from agent.core import CAPABILITY_SCENARIOS


def test_research_web_chronology_mini_registered():
    spec = get_scenario("research_web_chronology_mini")
    assert spec is not None
    assert spec.get("mode") == "research"
    assert spec.get("rubric_key") == "research_web_chronology_mini"
    rubric = CAPABILITY_SCENARIOS["research_web_chronology_mini"]
    assert rubric.get("min_web_search") == 2
    assert rubric.get("min_read_webpage") == 1
    assert rubric.get("require_finish") is True
    ids = [r["id"] for r in list_scenarios(mode="research")]
    assert "research_web_chronology_mini" in ids


def test_research_harness_scenarios_use_capability_contract():
    local = get_scenario("research_local_lock")
    web = get_scenario("research_web_chronology_mini")
    for spec in (local, web):
        blob = " ".join(
            str(spec.get(k, "")) for k in ("objective", "context", "description")
        ).lower()
        assert "save_research_note" not in blob
        assert "finish_task" not in blob
    assert "cap.research" in web["objective"].lower()
    assert "cap.research.finalize_deliverable@v1" in web["context"].lower()
    assert "web_search" not in local["context"].lower()
    assert "ingest" in local["context"].lower() or "offline" in local["context"].lower()
