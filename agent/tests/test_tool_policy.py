from tool_policy import EXPLORE_TOOLS, build_allowed_tool_names


def test_explore_tools_read_only():
    assert "write_file" not in EXPLORE_TOOLS
    assert "read_code_outline" in EXPLORE_TOOLS


def test_build_allowed_includes_meta_and_required():
    all_names = {
        "read_code_outline",
        "run_pytest",
        "replace_lines",
        "web_search",
        "mark_objective_complete",
        "finish_task",
        "write_file",
    }
    allowed = build_allowed_tool_names(
        mode="code",
        step_kind="explore",
        routed=["write_file"],
        all_tool_names=all_names,
    )
    assert "mark_objective_complete" in allowed
    assert "read_code_outline" in allowed
    assert "write_file" not in allowed
