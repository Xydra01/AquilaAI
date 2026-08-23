"""Walkthrough artifact tests."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.task_artifacts import render_walkthrough_markdown, write_walkthrough_artifact
from agent.core.walkthrough import build_walkthrough_prompt, summarize_tool_log


def test_render_walkthrough_sections():
    md = render_walkthrough_markdown(
        {
            "summary": "Done.",
            "what_we_did": ["Ran tests"],
            "how_to_verify": ["Open file"],
        },
        task_name="t1",
    )
    assert "Done." in md
    assert "Ran tests" in md


def test_write_walkthrough_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wt = {"summary": "s", "what_we_did": ["a"], "lessons_learned": ["l"]}
    md_path, refl = write_walkthrough_artifact("t1", "task", wt)
    assert os.path.isfile(md_path)
    assert os.path.isfile(refl)


def test_summarize_tool_log_extracts_tools():
    history = [
        {"role": "user", "content": "Tool 'web_search' result:\nfound data"},
    ]
    log = summarize_tool_log(history)
    assert "web_search" in log


def test_summarize_tool_log_extracts_capabilities():
    history = [
        {
            "role": "user",
            "content": (
                "Tool Outputs:\nCapability 'cap.research.synthesize_notes@v1' result:\n"
                "Synthesis note saved.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                "Tool Outputs:\nCapability 'cap.research.finalize_deliverable@v1' result:\n"
                "Report written (10167 bytes) from offline/attachment notes.\n"
            ),
        },
    ]
    log = summarize_tool_log(history)
    assert "cap.research.synthesize_notes@v1" in log
    assert "cap.research.finalize_deliverable@v1" in log
    assert "no tool log captured" not in log


def test_build_walkthrough_prompt_includes_goal():
    p = build_walkthrough_prompt(
        task_name="t",
        mode="code",
        user_goal="fix bug",
        plan_summary="TDD",
        tool_summary="grep",
        deliverable_path="/x.md",
        finish_msg="ok",
    )
    assert "fix bug" in p
    assert "do NOT claim sources were missing" in p
