import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tool_catalog import TOOL_ALIASES, build_executable_registry


def test_alias_targets_exist():
    tools = build_executable_registry()
    for alias, canonical in TOOL_ALIASES.items():
        assert canonical in tools, f"missing canonical {canonical} for {alias}"
        assert alias in tools, f"missing alias {alias}"
