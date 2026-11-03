import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.policies import CharacterBuildPolicy, CapabilityWritingPolicy, CapabilityCodePolicy, get_step_policy


def test_character_build_blocks_write_on_search():
    policy = CharacterBuildPolicy(
        mode="character_build", step_kind="search", persona_research_lore=True
    )
    msg = policy.block_message("write_persona_file", tools_succeeded=set())
    assert msg is not None
    assert "synthesize" in msg


def test_get_step_policy_character():
    p = get_step_policy("character_build", "read", persona_research_lore=True)
    assert isinstance(p, CharacterBuildPolicy)


def test_get_step_policy_writing():
    p = get_step_policy("writing", "write")
    assert isinstance(p, CapabilityWritingPolicy)


def test_get_step_policy_code():
    p = get_step_policy("code", "explore")
    assert isinstance(p, CapabilityCodePolicy)


def test_code_policy_forbids_edit_on_explore():
    p = get_step_policy("code", "explore")
    msg = p.validate_capability_call("cap.dev.edit_apply@v1")
    assert msg and "OS BLOCK" in msg


def test_code_policy_auto_advance_sync_on_finalize():
    p = get_step_policy("code", "finalize")
    assert p.should_auto_advance_after_capability(
        "cap.dev.sync_project@v1", True, step_kind="finalize"
    )


def test_code_policy_blocks_repeat_project_setup():
    p = get_step_policy("code", "work")
    msg = p.validate_capability_call(
        "cap.dev.project_setup@v1",
        tools_succeeded={"cap.dev.project_setup@v1"},
    )
    assert msg and "already set up" in msg.lower()


def test_code_policy_blocks_repeat_recon_on_work():
    p = get_step_policy("code", "work")
    msg = p.validate_capability_call(
        "cap.dev.recon@v1",
        tools_succeeded={"cap.dev.recon@v1"},
    )
    assert msg and "recon already" in msg.lower()


def test_code_policy_blocks_recon_on_greenfield_empty_buffer(monkeypatch):
    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools._load_state",
        lambda: {"files": []},
    )
    p = get_step_policy("code", "work")
    msg = p.validate_capability_call("cap.dev.recon@v1")
    assert msg and "greenfield" in msg.lower()


def test_code_policy_blocks_duplicate_create_file_in_buffer(monkeypatch):
    monkeypatch.setattr(
        "agent.tool_library.code_canvas_tools.buffer_has_file",
        lambda fp: fp == "habit.py",
    )
    p = get_step_policy("code", "tdd_green")
    msg = p.validate_capability_call(
        "cap.dev.create_file@v1",
        file_path="habit.py",
    )
    assert msg and "already exists" in msg.lower()


def test_code_policy_allows_readme_create_on_finalize():
    p = get_step_policy("code", "finalize")
    assert "cap.dev.create_file@v1" not in p.forbidden_capabilities_on_step()
    msg = p.validate_capability_call(
        "cap.dev.create_file@v1",
        file_path="README.md",
    )
    assert msg is None


def test_code_policy_blocks_non_readme_create_on_finalize():
    p = get_step_policy("code", "finalize")
    msg = p.validate_capability_call(
        "cap.dev.create_file@v1",
        file_path="habit.py",
    )
    assert msg and "README.md" in msg


def test_code_policy_auto_advance_tdd_green_on_impl_module():
    p = get_step_policy("code", "tdd_green")
    assert p.should_auto_advance_after_capability(
        "cap.dev.create_file@v1",
        True,
        step_kind="tdd_green",
        result_data={"file_path": "habit_manager.py"},
    )
    assert not p.should_auto_advance_after_capability(
        "cap.dev.create_file@v1",
        True,
        step_kind="tdd_green",
        result_data={"file_path": "tests/test_habit.py"},
    )


def test_writing_policy_does_not_auto_advance_on_init_only():
    p = get_step_policy("writing", "write")
    assert not p.should_auto_advance_after_capability(
        "cap.writing.init_document@v1", True, step_kind="write"
    )


def test_writing_policy_single_draft_advances_after_draft():
    p = get_step_policy(
        "writing",
        "write",
        writing_brief={"scope": "quick_edit", "advance_when": "single_draft"},
    )
    assert p.should_auto_advance_after_capability(
        "cap.writing.draft_sections@v1", True, step_kind="write"
    )


def test_writing_policy_scope_met_waits_for_sections():
    p = get_step_policy(
        "writing",
        "write",
        writing_brief={
            "scope": "standard",
            "advance_when": "scope_met",
            "length_mode": "sections",
            "target_sections": 4,
        },
    )
    assert not p.should_auto_advance_after_capability(
        "cap.writing.draft_sections@v1", True, step_kind="write"
    )
