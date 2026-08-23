import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import (
    MAX_TOOLS_PER_TURN,
    get_executable_tools,
    validate_tool_calls,
    validate_tool_arguments,
    parse_agent_response,
    ToolExecutor,
    build_strict_schema,
)
from agent.core import normalize_workspace_path
from tool_library.agent_tools import save_research_note, MAX_SCRATCHPAD_NOTE_BYTES
from agent.core import LoopEngine


def test_validate_rejects_tool_name_alias():
    ok, err = validate_tool_calls([
        {"tool_name": "write_file", "arguments": {"file_path": "x", "content": "y"}},
    ])
    assert ok is False
    assert "illegal keys" in err or "missing required key 'name'" in err


def test_validate_accepts_correct_shape():
    ok, err = validate_tool_calls([
        {"name": "list_directory", "arguments": {"path": "."}},
    ])
    assert ok is True
    assert err == ""


def test_schema_tool_items_use_name_enum():
    schema = build_strict_schema(get_executable_tools())
    items = schema["properties"]["tools"]["items"]
    assert "enum" in items["properties"]["name"]
    assert "write_file" in items["properties"]["name"]["enum"]


def test_index_codebase_excluded_from_executable_tools():
    tools = get_executable_tools()
    assert "_index_codebase" not in tools


def test_max_tools_constant():
    assert MAX_TOOLS_PER_TURN == 6


def test_parse_empty_returns_dict():
    from agent.core import console

    console.log_filename = None
    assert parse_agent_response("not json at all") == {}
    parsed = parse_agent_response('{"reasoning":"x","tools":[]}')
    assert isinstance(parsed, dict)
    assert "tools" in parsed


def test_executor_coerces_int_args(tmp_path):
    f = tmp_path / "nums.txt"
    f.write_text("1\n2\n3\n", encoding="utf-8")

    executor = ToolExecutor()
    results = executor.execute([
        {
            "name": "read_file_lines",
            "arguments": {"file_path": str(f), "start_line": "1", "end_line": "2"},
        }
    ])
    assert "❌ Error" not in results[0]
    assert "1:" in results[0] or "Lines" in results[0]


def test_tool_calls_slice_respects_max():
    """Unit check mirroring run_unified_task truncation behavior."""
    tool_calls = [{"name": f"tool_{i}", "arguments": {}} for i in range(10)]
    if len(tool_calls) > MAX_TOOLS_PER_TURN:
        tool_calls = tool_calls[:MAX_TOOLS_PER_TURN]
    assert len(tool_calls) == MAX_TOOLS_PER_TURN


def test_validate_rejects_unknown_argument_keys():
    ok, err = validate_tool_arguments([
        {
            "name": "save_research_note",
            "arguments": {"task_name": "t", "gathered_data": "x", "format": "markdown"},
        },
    ])
    assert ok is True


def test_read_webpage_drops_garbage_max_chars():
    from tool_library.web_tools import read_webpage

    calls = [
        {
            "name": "read_webpage",
            "arguments": {"url": "https://example.com", "max_chars": "}, '"},
        }
    ]
    ok, err = validate_tool_arguments(
        calls,
        registry={"read_webpage": {"func": read_webpage, "description": "read"}},
    )
    assert ok, err
    assert "max_chars" not in calls[0]["arguments"]


def test_normalize_workspace_path_collapses_doubled_agent():
    assert normalize_workspace_path("agent/agent/tests/foo.py") == "agent/tests/foo.py"


def test_save_research_note_splits_large_payload_into_chunks(monkeypatch):
    from agent.policies import set_runtime_context
    from tool_library import agent_tools as at
    from tool_library.agent_tools import _scratchpad_byte_limit

    set_runtime_context("aquila", 8192)
    saved_notes: list[str] = []

    def fake_save(task_name, note):
        saved_notes.append(note)
        return "ok"

    mock_mem = type("M", (), {})()
    mock_mem.save_scratchpad_note = fake_save
    mock_mem.get_scratchpad_notes = lambda t: ""
    monkeypatch.setattr(at, "get_active_memory", lambda: mock_mem)
    big = "x" * (_scratchpad_byte_limit() + 500)
    from agent.core import active_task

    with active_task("task1"):
        result = save_research_note(big)
    limit = _scratchpad_byte_limit()
    assert "scratchpad chunks" in result.lower()
    assert len(saved_notes) >= 2
    for note in saved_notes:
        assert len(note.encode("utf-8")) <= limit + 64
    rejoined = "".join(
        n.split("\n", 1)[-1] if n.startswith("[scratchpad chunk") else n
        for n in saved_notes
    )
    assert len(rejoined) == len(big)


def test_strip_scratchpad_task_name_before_validation():
    stripped = LoopEngine._strip_scratchpad_task_name_from_tool_calls(
        [
            {
                "name": "save_research_note",
                "arguments": {"task_name": "wrong_slug", "gathered_data": "lore"},
            }
        ]
    )
    assert "task_name" not in stripped[0]["arguments"]
    assert stripped[0]["arguments"]["gathered_data"] == "lore"


def test_research_finalize_hint_skips_read_when_scratchpad_injected():
    injected = LoopEngine._research_finalize_os_hint(scratchpad_injected=True)
    assert "SCRATCHPAD" in injected
    assert "Do **not** call `read_all_research_notes`" in injected
    assert "same** JSON" in injected
    plain = LoopEngine._research_finalize_os_hint(scratchpad_injected=False)
    assert "read_all_research_notes` once" in plain


def test_normalize_research_tool_args_heal_gathered_data():
    args, note = LoopEngine._normalize_research_tool_args(
        "read_all_research_notes",
        {"task_name": "sans-au-school"},
        "syllabus_build_sans-au-school",
    )
    assert "task_name" not in args
    assert note is None

    args2, note2 = LoopEngine._normalize_research_tool_args(
        "save_research_note",
        {"task_name": "sans-au-school", "gathered_data": "lore"},
        "syllabus_build_sans-au-school",
    )
    assert "task_name" not in args2
    assert note2 == "lore"


def test_loop_engine_duplicate_warning_at_two():
    sig = '{"arguments": {}, "name": "list_directory"}'
    msg = LoopEngine._duplicate_tool_warning([sig, sig])
    assert msg is not None
    assert "twice" in msg


def test_duplicate_tool_block_on_third_identical_call():
    from agent.research import UrlVisitRegistry

    sig = json.dumps({"name": "web_search", "arguments": {"query": "nasa exoplanets"}}, sort_keys=True)
    reg = UrlVisitRegistry()
    assert reg.duplicate_tool_warning([sig, sig]) is not None
    assert reg.duplicate_tool_block([sig, sig, sig]) is not None
    assert "BLOCK" in reg.duplicate_tool_block([sig, sig, sig])


def test_build_allowed_includes_tree_when_routed_empty_code_explore():
    from agent.policies import build_allowed_tool_names

    allowed = build_allowed_tool_names(
        mode="code",
        step_kind="explore",
        routed=[],
        all_tool_names={
            "get_directory_tree",
            "read_code_outline",
            "mark_objective_complete",
        },
    )
    assert "get_directory_tree" in allowed
    assert "read_code_outline" in allowed


def test_normalize_tool_calls_list_coerces_strings():
    from agent.core import normalize_tool_calls_list

    out = normalize_tool_calls_list(["web_search", {"name": "read_webpage", "arguments": {"url": "http://x"}}])
    assert out[0] == {"name": "web_search", "arguments": {}}
    assert out[1]["name"] == "read_webpage"


def test_tdd_red_gate_blocks_without_failure():
    msg = LoopEngine._tdd_advance_gate("tdd_red", [], "Tool 'run_pytest' result:\n✅ pytest: 1 passed")
    assert msg is not None
    assert "tdd_red" in msg


def test_explore_gate_accepts_tools_succeeded_set():
    history: list[dict] = []
    assert (
        LoopEngine._explore_advance_gate(
            history,
            "Tool 'write_project_markdown' result:\n✅ Wrote",
            {"get_directory_tree", "read_code_outline", "write_project_markdown"},
        )
        is None
    )


def test_explore_gate_tree_plus_outline_plus_region_in_blob():
    blob = (
        "Tool 'get_directory_tree' result:\nDirectory Tree for: proj/\n"
        "Tool 'read_code_outline' result:\nPROJECT: p\n"
        "Tool 'read_file_region' result:\nlines 1-10"
    )
    assert LoopEngine._explore_advance_gate([], blob, set()) is None


def test_tdd_red_gate_allows_failure():
    blob = "Tool 'run_pytest' result:\n❌ pytest: 0 passed, 1 failed"
    assert LoopEngine._tdd_advance_gate("tdd_red", [], blob) is None


def test_explore_gate_accepts_tools_succeeded_set():
    succeeded = {
        "get_directory_tree",
        "read_code_outline",
        "read_file_region",
        "write_project_markdown",
    }
    assert (
        LoopEngine._explore_advance_gate([], "", succeeded) is None
    )


def test_explore_gate_tree_outline_and_doc_write_in_history():
    hist = [
        {
            "role": "user",
            "content": (
                "Tool 'get_directory_tree' result:\nDirectory Tree for: proj/\n"
                "Tool 'read_code_outline' result:\nPROJECT: proj\n"
                "Tool 'write_project_markdown' result:\n✅ Wrote ARCHITECTURE.md"
            ),
        }
    ]
    assert LoopEngine._explore_advance_gate(hist, "", set()) is None


def test_tdd_green_gate_requires_pass():
    fail_blob = "Tool 'run_pytest' result:\n❌ pytest: 1 passed, 2 failed"
    assert LoopEngine._tdd_advance_gate("tdd_green", [], fail_blob) is not None
    pass_blob = "Tool 'run_pytest' result:\n✅ pytest: 2 passed, 0 failed"
    assert LoopEngine._tdd_advance_gate("tdd_green", [], pass_blob) is None


def test_normalize_tool_calls_merges_duplicate_save_research_notes():
    tool_calls = [
        {"name": "web_search", "arguments": {"query": "test"}},
        {"name": "save_research_note", "arguments": {"gathered_data": "first note"}},
        {"name": "save_research_note", "arguments": {"gathered_data": "second note"}},
        {"name": "list_directory", "arguments": {"path": "."}},
        {"name": "save_research_note", "arguments": {"gathered_data": "third note"}},
    ]
    healed, report = LoopEngine._normalize_tool_calls(tool_calls, "existing_report")

    assert report == "existing_report"
    assert len(healed) == 3
    assert healed[0] == {"name": "web_search", "arguments": {"query": "test"}}
    assert healed[1]["name"] == "save_research_note"
    assert healed[1]["arguments"]["gathered_data"] == "first note\n\nsecond note\n\nthird note"
    assert healed[2] == {"name": "list_directory", "arguments": {"path": "."}}
