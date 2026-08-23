"""Offline research mode: capability policy and milestone gates."""
from agent.capabilities.base import CapabilityResult
from agent.core.loop_objectives import MilestoneState, MilestoneTracker
from agent.policies.step_policies import CapabilityResearchPolicy, get_step_policy

_NOTE_OK = CapabilityResult.success("saved")


def test_research_policy_forbids_web_capabilities_when_offline():
    policy = get_step_policy("research", "work", offline_research=True)
    assert isinstance(policy, CapabilityResearchPolicy)
    forbidden = policy.forbidden_capabilities_on_step()
    assert "cap.web.search@v1" in forbidden
    assert "cap.research.gather_web_sources@v1" in forbidden
    msg = policy.validate_capability_call("cap.web.search@v1")
    assert msg is not None
    assert "Offline research" in msg


def test_offline_milestone_advance_without_web():
    tracker = MilestoneTracker()
    tracker.state.offline_research = True
    tracker.state.offline_sources_available = True
    assert not tracker.should_suggest_advance_research()
    tracker.record_capability("cap.research.append_note@v1", _NOTE_OK, mode="research")
    assert not tracker.should_suggest_advance_research()
    tracker.record_capability("cap.research.append_note@v1", _NOTE_OK, mode="research")
    assert tracker.should_suggest_advance_research()


def test_offline_finish_allows_without_webpage():
    tracker = MilestoneTracker()
    tracker.state.offline_research = True
    tracker.record_capability("cap.research.append_note@v1", _NOTE_OK, mode="research")
    assert tracker.should_allow_finish("research", is_final_step=True)


def test_offline_policy_blocks_repeat_synthesize():
    from agent.policies.step_policies import CapabilityResearchPolicy

    policy = CapabilityResearchPolicy(
        mode="research", step_kind="work", offline_research=True
    )
    succeeded = {"cap.research.synthesize_notes@v1"}
    msg = policy.validate_capability_call(
        "cap.research.synthesize_notes@v1",
        tools_succeeded=succeeded,
    )
    assert msg is not None
    assert "already ran" in msg.lower() or "already" in msg.lower()


def test_synthesize_auto_advance_on_work_step():
    from agent.policies.step_policies import CapabilityResearchPolicy

    policy = CapabilityResearchPolicy(
        mode="research", step_kind="work", offline_research=True
    )
    assert policy.should_auto_advance_after_capability(
        "cap.research.synthesize_notes@v1",
        True,
        step_kind="work",
    )
    assert not policy.should_auto_advance_after_capability(
        "cap.research.ingest_offline@v1",
        True,
        step_kind="work",
    )


def test_recommended_capability_offline_work_pipeline():
    from agent.functions.research import recommended_capability_for_step

    step = {"step_kind": "work", "capability_id": "cap.research.ingest_offline@v1"}
    cap, _ = recommended_capability_for_step(
        step, "topic", offline=True, has_attachments=True
    )
    assert cap == "cap.research.ingest_offline@v1"
    cap2, _ = recommended_capability_for_step(
        step,
        "topic",
        offline=True,
        has_attachments=True,
        caps_succeeded={"cap.research.ingest_offline@v1"},
    )
    assert cap2 == "cap.research.synthesize_notes@v1"


def test_policy_blocks_reingest_after_preingest_mark():
    from agent.policies.step_policies import CapabilityResearchPolicy

    policy = CapabilityResearchPolicy(
        mode="research", step_kind="work", offline_research=True
    )
    msg = policy.validate_capability_call(
        "cap.research.ingest_offline@v1",
        tools_succeeded={"cap.research.ingest_offline@v1"},
    )
    assert msg is not None
    assert "synthesize" in msg.lower()


def test_scratchpad_dedup_block_detection():
    from agent.capabilities.base import CapabilityResult
    from agent.core.loop_engine import _is_scratchpad_dedup_block

    fail = CapabilityResult.failure(
        "save_failed",
        "❌ OS BLOCK: This note is ≥85% similar to existing scratchpad content. "
        "(similarity: 99%)",
    )
    assert _is_scratchpad_dedup_block(fail)
    ok = CapabilityResult.success("Ingested 1 offline source block(s).")
    assert not _is_scratchpad_dedup_block(ok)


def test_offline_milestone_checks_use_save_notes():
    state = MilestoneState(
        offline_research=True,
        offline_sources_available=True,
        notes_saved=2,
    )
    checks = dict(state._checks("research", is_final_step=False))
    assert checks["ingest"] is True
    assert checks["evidence"] is True
    assert checks["progress"] is True
