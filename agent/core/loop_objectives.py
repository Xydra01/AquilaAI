"""Milestone state for dynamic (Cursor-style) act loop."""
from __future__ import annotations

from dataclasses import dataclass, field

# Maps (mode, milestone) → tool names that advance that milestone.
MILESTONE_TOOL_HINTS: dict[str, dict[str, list[str]]] = {
    "research": {
        "ingest": ["web_search"],
        "evidence": ["read_webpage", "save_research_note"],
        "progress": ["save_research_note"],
        "deliver": ["save_task_deliverable", "finish_task"],
    },
    "research_offline": {
        "ingest": ["save_research_note"],
        "evidence": ["save_research_note"],
        "progress": ["save_research_note", "read_all_research_notes"],
        "deliver": ["save_task_deliverable", "finish_task"],
    },
    "writing": {
        "draft": ["append_project_markdown", "write_section", "write_project_markdown"],
        "deliver": ["compile_final_document", "finish_task"],
    },
    "code": {
        "evidence": ["read_file_region", "grep_repo", "get_directory_tree", "read_code_outline"],
        "implement": ["replace_lines", "apply_unified_patch", "create_buffer_file"],
        "verify": ["run_pytest", "run_linter", "sync_project_to_disk"],
        "deliver": ["finish_task"],
    },
    "task": {
        "work": ["delegate_mode"],
        "deliver": ["finish_task"],
    },
    "autonomous": {
        "work": ["delegate_mode"],
        "deliver": ["finish_task"],
    },
}

MILESTONE_CAPABILITY_HINTS: dict[str, dict[str, list[str]]] = {
    "research": {
        "ingest": ["cap.research.gather_web_sources@v1", "cap.web.search@v1"],
        "evidence": ["cap.web.read_pages@v1", "cap.research.append_note@v1"],
        "progress": ["cap.research.synthesize_notes@v1", "cap.research.append_note@v1"],
        "deliver": ["cap.research.finalize_deliverable@v1"],
    },
    "research_offline": {
        "ingest": ["cap.research.ingest_offline@v1"],
        "evidence": ["cap.research.append_note@v1", "cap.research.read_notes@v1"],
        "progress": ["cap.research.synthesize_notes@v1"],
        "deliver": ["cap.research.finalize_deliverable@v1"],
    },
}


def milestone_hints_for_mode(
    mode: str,
    *,
    offline: bool = False,
    capability: bool = False,
) -> dict[str, list[str]]:
    mode_norm = (mode or "task").strip().lower()
    if mode_norm != "research":
        return MILESTONE_TOOL_HINTS.get(mode_norm, {})
    key = "research_offline" if offline else "research"
    table = MILESTONE_CAPABILITY_HINTS if capability else MILESTONE_TOOL_HINTS
    return table.get(key, {})


def milestone_hint_mode_key(
    mode: str,
    *,
    offline: bool = False,
    capability: bool = False,
) -> str:
    mode_norm = (mode or "task").strip().lower()
    if mode_norm != "research":
        return mode_norm
    if capability:
        return "research_offline" if offline else "research"
    return "research_offline" if offline else "research"


@dataclass
class MilestoneState:
    ingest_done: bool = False
    evidence_count: int = 0
    file_edited: bool = False
    tests_green: bool | None = None
    deliverable_draft: bool = False
    web_search_count: int = 0
    read_webpage_count: int = 0
    notes_saved: int = 0
    sections_written: int = 0
    delegate_done: bool = False
    offline_research: bool = False
    offline_sources_available: bool = False

    def completed_count(self, mode: str, *, is_final_step: bool) -> int:
        checks = self._checks(mode, is_final_step=is_final_step)
        return sum(1 for _, ok in checks if ok)

    def total_count(self, mode: str, *, is_final_step: bool) -> int:
        return len(self._checks(mode, is_final_step=is_final_step))

    def _checks(self, mode: str, *, is_final_step: bool) -> list[tuple[str, bool]]:
        mode_norm = (mode or "task").strip().lower()
        if mode_norm == "code":
            base = [
                ("evidence", self.evidence_count > 0 or self.ingest_done),
                ("implement", self.file_edited),
            ]
            if self.tests_green is not None:
                base.append(("tests", self.tests_green))
            else:
                base.append(("verify", self.file_edited))
            if is_final_step:
                base.append(("deliver", self.deliverable_draft or self.file_edited))
            return base
        if mode_norm == "research":
            if self.offline_research:
                ingest_ok = (
                    self.offline_sources_available
                    or self.notes_saved >= 1
                    or self.ingest_done
                )
                evidence_ok = self.notes_saved >= 1
                progress_ok = self.notes_saved >= 2
            else:
                ingest_ok = self.web_search_count >= 1
                evidence_ok = self.read_webpage_count >= 1 or self.evidence_count >= 2
                progress_ok = self.notes_saved >= 2 or (
                    self.notes_saved >= 1 and self.web_search_count >= 2
                )
            base = [
                ("ingest", ingest_ok),
                ("evidence", evidence_ok),
            ]
            if is_final_step:
                base.append(("deliver", self.deliverable_draft))
            else:
                base.append(("progress", progress_ok))
            return base
        if mode_norm == "writing":
            base = [
                ("draft", self.sections_written >= 1 or self.deliverable_draft),
            ]
            if is_final_step:
                base.append(("deliver", self.deliverable_draft))
            return base
        if mode_norm in ("task", "autonomous"):
            base = [
                ("work", self.evidence_count > 0 or self.delegate_done),
            ]
            if is_final_step:
                base.append(("deliver", self.deliverable_draft or self.delegate_done))
            return base
        return [("progress", self.evidence_count > 0)]

    def progress_line(self, mode: str, *, is_final_step: bool) -> str:
        done = self.completed_count(mode, is_final_step=is_final_step)
        total = self.total_count(mode, is_final_step=is_final_step)
        mode_key = (mode or "task").strip().lower()
        capability = mode_key == "research"
        if mode_key == "research" and self.offline_research:
            mode_key = "research_offline"
        hints_mode = milestone_hint_mode_key(
            mode,
            offline=self.offline_research,
            capability=capability,
        )
        names = [label for label, ok in self._checks(mode, is_final_step=is_final_step) if ok]
        pending = [
            label
            for label, ok in self._checks(mode, is_final_step=is_final_step)
            if not ok
        ]
        parts = [f"Milestones {done}/{total} complete."]
        if names:
            parts.append(f"Done: {', '.join(names)}.")
        if pending:
            pending_parts = []
            mode_hints = (
                MILESTONE_CAPABILITY_HINTS if capability else MILESTONE_TOOL_HINTS
            ).get(hints_mode, {})
            for p in pending:
                hints = mode_hints.get(p)
                if hints:
                    pending_parts.append(f"{p} (try: {', '.join(hints)})")
                else:
                    pending_parts.append(p)
            parts.append(f"Remaining: {', '.join(pending_parts)}.")
        return " ".join(parts)


@dataclass
class MilestoneTracker:
    """Accumulates milestone signals from tool runs."""

    state: MilestoneState = field(default_factory=MilestoneState)
    _saw_final_report: bool = False

    def record_tool(
        self,
        tool_name: str,
        result: str,
        *,
        mode: str,
    ) -> None:
        name = (tool_name or "").strip()
        text = str(result or "")
        ok = not text.startswith("❌")

        if name in (
            "read_file",
            "read_file_region",
            "read_file_smart",
            "read_webpage",
            "grep_repo",
            "read_code_outline",
            "get_directory_tree",
            "list_directory",
        ):
            if ok:
                self.state.evidence_count += 1
                self.state.ingest_done = True

        if name == "web_search" and ok:
            self.state.web_search_count += 1
            self.state.ingest_done = True

        if name == "read_webpage" and ok:
            self.state.read_webpage_count += 1

        if name == "save_research_note" and ok:
            self.state.notes_saved += 1
            self.state.ingest_done = True

        if name in (
            "replace_lines",
            "apply_patch",
            "apply_unified_patch",
            "replace_symbol",
            "create_buffer_file",
            "write_file",
            "replace_in_file",
            "write_project_markdown",
            "append_project_markdown",
        ):
            if ok:
                self.state.file_edited = True

        if name == "run_pytest":
            low = text.lower()
            if ok and ("passed" in low or "0 failed" in low):
                self.state.tests_green = True
            elif "failed" in low:
                self.state.tests_green = False

        if name == "run_linter" and ok and "no issues" in text.lower():
            if self.state.tests_green is None:
                self.state.tests_green = True

        if name in (
            "write_section", "compile_final_document", "init_document",
            "append_project_markdown", "write_project_markdown",
        ):
            if ok:
                self.state.sections_written += 1
                self.state.deliverable_draft = True

        if name == "delegate_mode" and ok:
            self.state.delegate_done = True

        if name == "finish_task" and ok:
            self.state.deliverable_draft = True

    def record_capability(
        self,
        cap_id: str,
        result: "CapabilityResult | None",
        *,
        mode: str,
    ) -> None:
        """Map capability outcomes to milestone counters."""
        from agent.capabilities.base import CapabilityResult

        cap_id = (cap_id or "").strip()
        if not cap_id:
            return
        ok = isinstance(result, CapabilityResult) and result.ok
        summary = ""
        if isinstance(result, CapabilityResult):
            summary = result.summary or result.error_message or ""

        if cap_id.endswith("gather_web_sources@v1") and ok:
            self.record_tool("web_search", summary or "ok", mode=mode)
            self.record_tool("read_webpage", summary or "ok", mode=mode)
            self.record_tool("save_research_note", summary or "ok", mode=mode)
            return
        if cap_id.endswith("ingest_offline@v1") and ok:
            self.record_tool("save_research_note", summary or "ok", mode=mode)
            return
        if cap_id.endswith("append_note@v1") and ok:
            self.record_tool("save_research_note", summary or "ok", mode=mode)
            return
        if cap_id.endswith("synthesize_notes@v1") and ok:
            self.record_tool("save_research_note", summary or "ok", mode=mode)
            return
        if cap_id.endswith("read_pages@v1") and ok:
            self.record_tool("read_webpage", summary or "ok", mode=mode)
            return
        if cap_id.endswith("search@v1") and ok:
            self.record_tool("web_search", summary or "ok", mode=mode)
            return
        if cap_id.endswith("finalize_deliverable@v1") and ok:
            self.record_tool("finish_task", summary or "ok", mode=mode)
            self.note_final_report()

    def note_final_report(self) -> None:
        self._saw_final_report = True
        self.state.deliverable_draft = True

    def should_suggest_advance(
        self,
        mode: str,
        *,
        is_final_step: bool,
    ) -> bool:
        if is_final_step:
            return False
        mode_norm = (mode or "task").strip().lower()
        if mode_norm == "research":
            return self.should_suggest_advance_research()
        st = self.state
        total = st.total_count(mode, is_final_step=False)
        done = st.completed_count(mode, is_final_step=False)
        return total > 0 and done >= total

    def should_suggest_advance_research(self) -> bool:
        """Work-step advance: require ingest + evidence + progress notes."""
        st = self.state
        if st.offline_research:
            ingest_ok = (
                st.offline_sources_available
                or st.notes_saved >= 1
                or st.ingest_done
            )
            evidence_ok = st.notes_saved >= 1
            progress_ok = st.notes_saved >= 2
            return ingest_ok and evidence_ok and progress_ok
        ingest_ok = st.web_search_count >= 1
        evidence_ok = st.read_webpage_count >= 1 or st.evidence_count >= 2
        progress_ok = st.notes_saved >= 2 or (
            st.notes_saved >= 1 and st.web_search_count >= 2
        )
        return ingest_ok and evidence_ok and progress_ok

    def should_allow_finish(
        self,
        mode: str,
        *,
        is_final_step: bool,
        pending_final_report: bool = False,
    ) -> bool:
        if not is_final_step:
            return False
        if pending_final_report or self._saw_final_report:
            if (mode or "").strip().lower() == "research":
                st = self.state
                if st.notes_saved < 1:
                    return False
                if not st.offline_research and st.read_webpage_count < 1 and st.evidence_count < 2:
                    return False
            return True
        st = self.state
        mode_norm = (mode or "task").strip().lower()
        if mode_norm == "research":
            if st.notes_saved < 1:
                return False
            if not st.offline_research and st.read_webpage_count < 1 and st.evidence_count < 2:
                return False
            # On the final step, final_report and finish_task ship in one act JSON turn.
            return True
        done = st.completed_count(mode, is_final_step=True)
        total = st.total_count(mode, is_final_step=True)
        return total > 0 and done >= max(1, total - 1)

    def to_log_dict(self, mode: str, *, is_final_step: bool) -> dict:
        st = self.state
        return {
            "ingest_done": st.ingest_done,
            "evidence_count": st.evidence_count,
            "file_edited": st.file_edited,
            "tests_green": st.tests_green,
            "deliverable_draft": st.deliverable_draft,
            "notes_saved": st.notes_saved,
            "web_search_count": st.web_search_count,
            "read_webpage_count": st.read_webpage_count,
            "completed": st.completed_count(mode, is_final_step=is_final_step),
            "total": st.total_count(mode, is_final_step=is_final_step),
        }
