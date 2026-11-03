"""Mode-specific ground-truth adapters for TaskRunContext."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from agent.storage import agent_data_path


class GroundTruthProvider(Protocol):
    def snapshot(self, *, task_id: str, mode: str, harness_ctx: Any = None) -> dict[str, Any]: ...

    def infer_checklist_ticks(
        self,
        cap_id: str,
        result: Any,
        snapshot: dict[str, Any],
    ) -> list[str]: ...

    def infer_milestones(self, snapshot: dict[str, Any]) -> dict[str, bool]: ...


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _buffer_file_paths(state: dict[str, Any]) -> list[str]:
    """Normalize code canvas ``files`` (list of entries or legacy path dict)."""
    raw = state.get("files")
    if isinstance(raw, dict):
        return [str(path) for path in raw.keys()]
    if isinstance(raw, list):
        paths: list[str] = []
        for entry in raw:
            if isinstance(entry, dict):
                path = entry.get("path")
                if path:
                    paths.append(str(path))
            elif isinstance(entry, str):
                paths.append(entry)
        return paths
    return []


def _is_test_buffer_path(path: str) -> bool:
    p = str(path or "").replace("\\", "/").lower()
    return "test" in p and ("/tests/" in p or p.startswith("tests/") or "/test_" in p)


def _is_impl_buffer_path(path: str) -> bool:
    from agent.core.implementation_plan import is_code_impl_source_path

    return is_code_impl_source_path(path)


class CodeGroundTruthProvider:
    def snapshot(self, *, task_id: str, mode: str, harness_ctx: Any = None) -> dict[str, Any]:
        from agent.tool_library.code_canvas_tools import active_code_file, _load_state

        state = _load_state()
        files = _buffer_file_paths(state)[:40]
        root = str(state.get("root") or "")
        setup_done = bool(state.get("project_id") or state.get("root"))
        tests_pass: bool | None = None
        if harness_ctx is not None:
            gt = getattr(harness_ctx, "ground_truth", None)
            if isinstance(gt, dict) and "tests_pass" in gt:
                tests_pass = gt.get("tests_pass")
        return {
            "project_root": root,
            "buffer_files": files,
            "file_count": len(files),
            "setup_done": setup_done,
            "tests_pass": tests_pass,
            "active_state_path": str(active_code_file()),
        }

    def infer_checklist_ticks(
        self,
        cap_id: str,
        result: Any,
        snapshot: dict[str, Any],
    ) -> list[str]:
        if not getattr(result, "ok", False):
            return []
        ticks: list[str] = []
        if cap_id == "cap.dev.project_setup@v1":
            ticks.extend(["setup-1", "setup"])
        if cap_id in ("cap.dev.create_file@v1", "cap.dev.edit_apply@v1"):
            from agent.core.implementation_plan import (
                is_code_impl_source_path,
                is_code_test_path,
            )

            data = getattr(result, "data", {}) or {}
            fp = str(data.get("file_path") or data.get("path") or "")
            if fp:
                if is_code_test_path(fp):
                    ticks.extend(["tests-1", "test"])
                elif is_code_impl_source_path(fp):
                    ticks.extend(["impl-1", "implement"])
        if cap_id == "cap.dev.run_tests@v1":
            ticks.extend(["test-1", "tests", "verify"])
        if cap_id == "cap.dev.sync_project@v1":
            ticks.append("sync-1")
        if cap_id == "cap.dev.write_docs@v1":
            ticks.append("docs-1")
        return ticks

    def infer_checklist_ticks_from_snapshot(self, snapshot: dict[str, Any]) -> list[str]:
        files = [str(f) for f in (snapshot.get("buffer_files") or [])]
        ticks: list[str] = []
        has_test = any(_is_test_buffer_path(f) for f in files)
        has_impl = any(_is_impl_buffer_path(f) for f in files)
        if has_test:
            ticks.append("tests-1")
        if has_test and has_impl:
            ticks.append("impl-1")
        if snapshot.get("setup_done"):
            ticks.append("setup-1")
        tests = snapshot.get("tests_pass")
        if tests is True:
            ticks.append("test-1")
        return list(dict.fromkeys(ticks))

    def infer_milestones(self, snapshot: dict[str, Any]) -> dict[str, bool]:
        from agent.core.implementation_plan import is_code_impl_source_path

        files = snapshot.get("buffer_files") or []
        has_impl = any(is_code_impl_source_path(str(f)) for f in files)
        has_evidence = bool(snapshot.get("setup_done")) or len(files) > 0
        tests = snapshot.get("tests_pass")
        return {
            "evidence": has_evidence,
            "implement": has_impl and len(files) > 0,
            "tests": bool(tests) if tests is not None else False,
            "file_edited": has_impl,
        }


class WritingGroundTruthProvider:
    def snapshot(self, *, task_id: str, mode: str, harness_ctx: Any = None) -> dict[str, Any]:
        from agent.functions.writing_scope import draft_metrics, load_draft_state

        state = load_draft_state()
        metrics = draft_metrics(state)
        sections = []
        if state:
            for sec in state.get("sections") or []:
                if isinstance(sec, dict):
                    sections.append({
                        "id": sec.get("id", ""),
                        "title": sec.get("title", ""),
                        "words": len(str(sec.get("content") or "").split()),
                    })
        return {
            "section_count": metrics.get("sections", 0),
            "word_count": metrics.get("words", 0),
            "sections": sections[:20],
            "has_draft": bool(state),
        }

    def infer_checklist_ticks(
        self,
        cap_id: str,
        result: Any,
        snapshot: dict[str, Any],
    ) -> list[str]:
        if not getattr(result, "ok", False):
            return []
        ticks: list[str] = []
        if cap_id == "cap.writing.init_document@v1":
            ticks.append("outline-1")
        if cap_id == "cap.writing.draft_sections@v1":
            ticks.extend(["draft-1", "draft"])
        if cap_id in ("cap.writing.compile_document@v1", "cap.writing.finalize_deliverable@v1"):
            ticks.append("final-1")
        return ticks

    def infer_milestones(self, snapshot: dict[str, Any]) -> dict[str, bool]:
        return {
            "draft": snapshot.get("section_count", 0) >= 1 or snapshot.get("word_count", 0) > 50,
            "deliver": snapshot.get("word_count", 0) > 200,
        }


class ResearchGroundTruthProvider:
    def snapshot(self, *, task_id: str, mode: str, harness_ctx: Any = None) -> dict[str, Any]:
        notes_count = 0
        deliverable = ""
        if harness_ctx is not None:
            memory = getattr(harness_ctx, "memory", None)
            instance_id = getattr(harness_ctx, "instance_id", "default")
            if memory and hasattr(memory, "get_scratchpad_notes"):
                try:
                    compiled = memory.get_scratchpad_notes(task_id, instance_id=instance_id)
                    notes_count = compiled.count("---") if compiled else 0
                except Exception:
                    pass
        return {
            "notes_count": notes_count,
            "has_deliverable": bool(deliverable),
        }

    def infer_checklist_ticks(
        self,
        cap_id: str,
        result: Any,
        snapshot: dict[str, Any],
    ) -> list[str]:
        if not getattr(result, "ok", False):
            return []
        ticks: list[str] = []
        if cap_id in (
            "cap.research.gather_web_sources@v1",
            "cap.web.search@v1",
            "cap.research.ingest_offline@v1",
        ):
            ticks.append("src-1")
        if cap_id in ("cap.research.append_note@v1", "cap.research.synthesize_notes@v1"):
            ticks.extend(["note-1", "note"])
        if cap_id == "cap.research.finalize_deliverable@v1":
            ticks.append("rep-1")
        return ticks

    def infer_milestones(self, snapshot: dict[str, Any]) -> dict[str, bool]:
        n = snapshot.get("notes_count", 0)
        return {
            "ingest": n >= 1,
            "evidence": n >= 1,
            "progress": n >= 2,
            "deliver": snapshot.get("has_deliverable", False),
        }


class LearnGroundTruthProvider:
    def snapshot(self, *, task_id: str, mode: str, harness_ctx: Any = None) -> dict[str, Any]:
        course_dir = agent_data_path("Agent-Learn", task_id)
        syllabus_path = course_dir / "syllabus.json"
        has_syllabus = syllabus_path.is_file()
        modules = 0
        if has_syllabus:
            data = _safe_json(syllabus_path)
            nodes = data.get("nodes") or data.get("modules") or []
            modules = len(nodes) if isinstance(nodes, list) else 0
        return {
            "has_syllabus": has_syllabus,
            "module_count": modules,
            "course_dir": str(course_dir),
        }

    def infer_checklist_ticks(
        self,
        cap_id: str,
        result: Any,
        snapshot: dict[str, Any],
    ) -> list[str]:
        if not getattr(result, "ok", False):
            return []
        ticks: list[str] = []
        if cap_id == "cap.learn.ingest_course_materials@v1":
            ticks.append("ingest-1")
        if cap_id == "cap.learn.write_syllabus@v1":
            ticks.append("syll-1")
        if cap_id == "cap.learn.finalize_course@v1":
            ticks.append("fin-1")
        return ticks

    def infer_milestones(self, snapshot: dict[str, Any]) -> dict[str, bool]:
        return {
            "ingest": snapshot.get("module_count", 0) > 0 or snapshot.get("has_syllabus"),
            "progress": snapshot.get("has_syllabus", False),
            "deliver": snapshot.get("module_count", 0) > 0,
        }


class CharacterGroundTruthProvider:
    def snapshot(self, *, task_id: str, mode: str, harness_ctx: Any = None) -> dict[str, Any]:
        persona_dir = agent_data_path("Agent-Personas", task_id)
        init_path = persona_dir / "initialization.md"
        finalized = (persona_dir / "persona.json").is_file()
        return {
            "has_initialization": init_path.is_file(),
            "initialization_chars": len(init_path.read_text(encoding="utf-8")) if init_path.is_file() else 0,
            "finalized": finalized,
            "persona_dir": str(persona_dir),
        }

    def infer_checklist_ticks(
        self,
        cap_id: str,
        result: Any,
        snapshot: dict[str, Any],
    ) -> list[str]:
        if not getattr(result, "ok", False):
            return []
        ticks: list[str] = []
        if cap_id in ("cap.persona.ingest_sources@v1", "cap.persona.gather_lore@v1"):
            ticks.append("lore-1")
        if cap_id == "cap.persona.write_initialization@v1":
            ticks.append("init-1")
        if cap_id == "cap.persona.finalize@v1":
            ticks.append("fin-1")
        return ticks

    def infer_milestones(self, snapshot: dict[str, Any]) -> dict[str, bool]:
        init_ok = snapshot.get("has_initialization") and snapshot.get("initialization_chars", 0) > 100
        return {
            "ingest": init_ok or snapshot.get("has_initialization"),
            "progress": init_ok,
            "deliver": snapshot.get("finalized", False),
        }


class DefaultGroundTruthProvider:
    def snapshot(self, *, task_id: str, mode: str, harness_ctx: Any = None) -> dict[str, Any]:
        return {"task_id": task_id, "mode": mode}

    def infer_checklist_ticks(
        self,
        cap_id: str,
        result: Any,
        snapshot: dict[str, Any],
    ) -> list[str]:
        if getattr(result, "ok", False):
            return ["work-1"]
        return []

    def infer_milestones(self, snapshot: dict[str, Any]) -> dict[str, bool]:
        return {"progress": True}


_PROVIDERS: dict[str, GroundTruthProvider] = {
    "code": CodeGroundTruthProvider(),
    "writing": WritingGroundTruthProvider(),
    "research": ResearchGroundTruthProvider(),
    "learn_syllabus_build": LearnGroundTruthProvider(),
    "character_build": CharacterGroundTruthProvider(),
    "task": DefaultGroundTruthProvider(),
    "autonomous": DefaultGroundTruthProvider(),
}


def get_ground_truth_provider(mode: str) -> GroundTruthProvider:
    key = (mode or "task").strip().lower()
    return _PROVIDERS.get(key, DefaultGroundTruthProvider())
