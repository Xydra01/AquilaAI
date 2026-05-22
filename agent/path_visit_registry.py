"""Per-step guards against degenerative list_directory loops."""
from __future__ import annotations

import json


class PathVisitRegistry:
    def __init__(self) -> None:
        self._step_index = 0
        self._list_dir_total: dict[int, int] = {}
        self._list_dir_paths: dict[int, list[str]] = {}
        self._tree_used: dict[int, bool] = {}
        self._outline_used: dict[int, bool] = {}

    def set_step_index(self, index: int) -> None:
        self._step_index = index

    def record_tool(self, tool_name: str, arguments: dict) -> None:
        idx = self._step_index
        if tool_name == "get_directory_tree":
            self._tree_used[idx] = True
        elif tool_name == "read_code_outline":
            self._outline_used[idx] = True
        elif tool_name == "list_directory":
            self._list_dir_total[idx] = self._list_dir_total.get(idx, 0) + 1
            path = str(arguments.get("path", ".")).strip().lower()
            paths = self._list_dir_paths.setdefault(idx, [])
            paths.append(path)

    def check_list_directory(self, path: str) -> str | None:
        """Return OS block/warning message, or None to allow the call."""
        idx = self._step_index
        count = self._list_dir_total.get(idx, 0)
        norm_path = (path or ".").strip().lower()

        paths = self._list_dir_paths.get(idx, [])
        same_path_hits = sum(1 for p in paths if p == norm_path)

        if count >= 2:
            return (
                "❌ OS BLOCK: Too many list_directory calls this step. "
                "Use get_directory_tree(path='.', max_depth=2) once, then read_code_outline."
            )
        if same_path_hits >= 1:
            return (
                "⚠️ OS WARNING: You already listed this path. "
                "Use get_directory_tree or read_code_outline instead of re-listing."
            )
        return None

    def check_before_execute(self, tool_name: str, arguments: dict) -> str | None:
        if tool_name == "list_directory":
            return self.check_list_directory(str(arguments.get("path", ".")))
        return None

    @staticmethod
    def tool_signature(tool_name: str, arguments: dict) -> str:
        return json.dumps({"name": tool_name, "arguments": arguments}, sort_keys=True)
