"""Per-mode step policies: hints, forbidden tools, and advance rules for LoopEngine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tool_catalog import CHARACTER_BUILD_FORBIDDEN_FILE_TOOLS


@dataclass
class StepPolicy:
    mode: str
    step_kind: str = ""
    persona_research_lore: bool = False
    learn_syllabus_web: bool = False
    offline_research: bool = False

    def forbidden_tools_on_step(self) -> frozenset[str]:
        return frozenset()

    def should_auto_advance_after_tool(
        self,
        tool_name: str,
        *,
        tools_succeeded: set[str],
        scratchpad_has_lore: bool = False,
    ) -> bool:
        return False

    def advance_summary_for_tool(self, tool_name: str) -> str:
        return "Step complete."

    def os_suffix_after_tool(self, tool_name: str, result: str) -> str:
        return ""

    def block_message(
        self,
        tool_name: str,
        *,
        tools_succeeded: set[str],
        scratchpad_empty: bool = True,
    ) -> str | None:
        return None


class CharacterBuildPolicy(StepPolicy):
    def forbidden_tools_on_step(self) -> frozenset[str]:
        if self.step_kind in ("read", "search"):
            return frozenset({"write_persona_file", "summarize_sources"})
        if self.step_kind == "synthesize":
            return frozenset({"save_research_note", "read_webpage", "web_search"})
        return frozenset()

    def should_auto_advance_after_tool(
        self,
        tool_name: str,
        *,
        tools_succeeded: set[str],
        scratchpad_has_lore: bool = False,
    ) -> bool:
        if tool_name == "write_persona_file" and self.step_kind == "synthesize":
            return "write_persona_file" in tools_succeeded
        if tool_name == "save_research_note" and self.step_kind == "read":
            return "save_research_note" in tools_succeeded
        if (
            tool_name == "save_research_note"
            and self.step_kind == "search"
            and self.persona_research_lore
        ):
            return "save_research_note" in tools_succeeded
        if (
            tool_name == "mark_objective_complete"
            and self.step_kind == "read"
            and scratchpad_has_lore
            and self.persona_research_lore
        ):
            return False
        return False

    def should_auto_advance_read_with_scratchpad(
        self, *, scratchpad_has_lore: bool, tools_succeeded: set[str]
    ) -> bool:
        """Auto-advance read step when search already populated scratchpad."""
        if self.step_kind != "read" or not self.persona_research_lore:
            return False
        if not scratchpad_has_lore:
            return False
        if "save_research_note" in tools_succeeded:
            return True
        return False

    def advance_summary_for_tool(self, tool_name: str) -> str:
        if self.step_kind == "read":
            return (
                "Ingested persona source material into scratchpad; "
                "advancing to synthesize initialization.md."
            )
        if self.step_kind == "search":
            return "Search lore captured; advancing to read/ingest or synthesize."
        if self.step_kind == "synthesize":
            return "Wrote initialization.md; advancing to finalize_persona."
        return "Persona build step complete."

    def os_suffix_after_tool(self, tool_name: str, result: str) -> str:
        if result.startswith("❌"):
            return ""
        if self.step_kind == "read" and tool_name == "save_research_note":
            return (
                "\n✅ OS: Lore saved. Call mark_objective_complete now "
                "(or the OS will auto-advance after this turn)."
            )
        if self.step_kind == "search" and tool_name == "save_research_note":
            return (
                "\n✅ OS: Search lore saved. Call mark_objective_complete when ready — "
                "do not re-read the same URL."
            )
        if self.step_kind == "synthesize" and tool_name == "read_all_research_notes":
            return (
                "\n✅ OS: Notes loaded. Call write_persona_file for "
                "initialization.md now — do NOT call summarize_sources."
            )
        if self.step_kind == "synthesize" and tool_name == "write_persona_file" and result.startswith("✅"):
            return (
                "\n✅ OS: initialization.md written. Call "
                "mark_objective_complete (or OS will auto-advance)."
            )
        return ""

    def block_message(
        self,
        tool_name: str,
        *,
        tools_succeeded: set[str],
        scratchpad_empty: bool = True,
    ) -> str | None:
        forbidden = self.forbidden_tools_on_step()
        if tool_name in forbidden:
            if tool_name == "write_persona_file":
                return (
                    f"❌ OS BLOCK: {self.step_kind} step is ingest/research only. Use "
                    "save_research_note / web_search then mark_objective_complete. "
                    "write_persona_file belongs on the synthesize step."
                )
            if tool_name == "summarize_sources":
                return (
                    "❌ OS BLOCK: summarize_sources is for research mode only. "
                    "On persona build, use write_persona_file for initialization.md "
                    "(synthesize step) or save_research_note (ingest step)."
                )
            return (
                f"❌ OS BLOCK: {tool_name} is not used on persona {self.step_kind}. "
                "Call write_persona_file for initialization.md on synthesize."
            )
        if (
            self.step_kind == "read"
            and tool_name == "save_research_note"
            and "save_research_note" in tools_succeeded
        ):
            return (
                "❌ OS BLOCK: Ingest note already saved for this step. "
                "Call mark_objective_complete(summary_of_work="
                "'Ingested persona lore from user text and attachments.') "
                "— do NOT call save_research_note again."
            )
        if (
            self.step_kind == "read"
            and tool_name == "read_all_research_notes"
        ):
            if scratchpad_empty or "read_all_research_notes" in tools_succeeded:
                return (
                    "❌ OS BLOCK: read_all_research_notes is not allowed on "
                    "persona ingest. Call save_research_note with gathered_data, "
                    "then mark_objective_complete."
                )
            return (
                "❌ OS BLOCK: On ingest step use save_research_note, not "
                "read_all_research_notes. Reading notes is for the synthesize step only."
            )
        if (
            self.step_kind == "synthesize"
            and tool_name == "read_all_research_notes"
            and "read_all_research_notes" in tools_succeeded
        ):
            return (
                "❌ OS BLOCK: Scratchpad notes already loaded this step. "
                "Call write_persona_file for initialization.md now, "
                "then mark_objective_complete."
            )
        if tool_name in CHARACTER_BUILD_FORBIDDEN_FILE_TOOLS:
            return (
                f"❌ OS BLOCK: {tool_name} cannot create persona files. "
                "On the synthesize step use write_persona_file("
                "file_path='initialization.md', content='...') with the "
                "full character bible (800+ characters)."
            )
        return None


class LearnSyllabusPolicy(StepPolicy):
    def forbidden_tools_on_step(self) -> frozenset[str]:
        if self.step_kind in ("read", "search"):
            return frozenset({"write_syllabus_file"})
        if self.step_kind == "synthesize":
            return frozenset({"save_research_note", "read_webpage", "web_search"})
        return frozenset()

    def should_auto_advance_after_tool(
        self,
        tool_name: str,
        *,
        tools_succeeded: set[str],
        scratchpad_has_lore: bool = False,
    ) -> bool:
        if self.step_kind in ("read", "search") and tool_name == "save_research_note":
            return "save_research_note" in tools_succeeded
        if self.step_kind == "synthesize" and tool_name == "write_syllabus_file":
            return "write_syllabus_file" in tools_succeeded
        return False

    def advance_summary_for_tool(self, tool_name: str) -> str:
        if self.step_kind in ("read", "search"):
            return "Ingested course research; advancing to syllabus synthesis."
        if self.step_kind == "synthesize":
            return "Wrote syllabus.json; advancing to finalize_course."
        return "Learn syllabus step complete."

    def block_message(
        self,
        tool_name: str,
        *,
        tools_succeeded: set[str],
        scratchpad_empty: bool = True,
    ) -> str | None:
        if tool_name in self.forbidden_tools_on_step():
            if tool_name == "write_syllabus_file":
                return (
                    f"❌ OS BLOCK: {self.step_kind} step is ingest/research only. "
                    "write_syllabus_file belongs on the synthesize step."
                )
            return (
                f"❌ OS BLOCK: {tool_name} is not used on syllabus {self.step_kind}. "
                "Call write_syllabus_file with JSON on synthesize."
            )
        if (
            self.step_kind in ("read", "search")
            and tool_name == "save_research_note"
            and "save_research_note" in tools_succeeded
        ):
            return (
                "❌ OS BLOCK: Research note already saved for this step. "
                "Call mark_objective_complete — do NOT call save_research_note again."
            )
        return None


class ResearchPolicy(StepPolicy):
    _OFFLINE_FORBIDDEN = frozenset({"web_search", "read_webpage"})

    def forbidden_tools_on_step(self) -> frozenset[str]:
        if self.offline_research:
            return self._OFFLINE_FORBIDDEN
        return frozenset()

    def block_message(
        self,
        tool_name: str,
        *,
        tools_succeeded: set[str] | None = None,
        web_search_done_this_turn: int = 0,
        **kwargs,
    ) -> str | None:
        if self.offline_research and tool_name in self._OFFLINE_FORBIDDEN:
            return (
                f"❌ OS BLOCK: Offline research mode — {tool_name} is disabled. "
                "Use only user attachments, human journal, and save_research_note."
            )
        if (
            self.step_kind == "search"
            and tool_name == "web_search"
            and web_search_done_this_turn >= 1
        ):
            return (
                "❌ OS BLOCK: One web_search per turn on research search steps. "
                "Split topics across iterations."
            )
        return None


class CapabilityResearchPolicy(ResearchPolicy):
    """Research act loop policy for capability invocations."""

    _OFFLINE_FORBIDDEN_CAPS = frozenset({
        "cap.web.search@v1",
        "cap.web.read_pages@v1",
        "cap.research.gather_web_sources@v1",
    })

    def forbidden_capabilities_on_step(
        self,
        *,
        has_attachments: bool = False,
    ) -> frozenset[str]:
        if self.offline_research:
            return self._OFFLINE_FORBIDDEN_CAPS
        return frozenset()

    def validate_capability_call(
        self,
        cap_id: str,
        *,
        tools_succeeded: set[str] | None = None,
        web_search_done_this_turn: int = 0,
        **_kwargs,
    ) -> str | None:
        cap_id = (cap_id or "").strip()
        if self.offline_research and cap_id in self._OFFLINE_FORBIDDEN_CAPS:
            return (
                f"❌ OS BLOCK: Offline research — `{cap_id}` is disabled. "
                "Use cap.research.ingest_offline@v1 or cap.research.synthesize_notes@v1."
            )
        if (
            self.step_kind == "search"
            and cap_id in ("cap.web.search@v1", "cap.research.gather_web_sources@v1")
            and web_search_done_this_turn >= 1
        ):
            return (
                "❌ OS BLOCK: One web gather capability per turn on search steps. "
                "Split topics across iterations."
            )
        succeeded = tools_succeeded or set()
        if (
            cap_id == "cap.research.ingest_offline@v1"
            and "cap.research.ingest_offline@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: Offline ingest already ran this step "
                "(including OS pre-ingest). "
                "Use cap.research.synthesize_notes@v1 once, then advance."
            )
        if (
            cap_id == "cap.research.synthesize_notes@v1"
            and "cap.research.synthesize_notes@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: Synthesis already ran this step. "
                "Call mark_objective_complete to advance to finalize."
            )
        if (
            cap_id == "cap.research.read_notes@v1"
            and "cap.research.synthesize_notes@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: Notes already synthesized this step. "
                "Advance to finalize or call cap.research.finalize_deliverable@v1."
            )
        if (
            cap_id == "cap.research.ingest_offline@v1"
            and "cap.research.synthesize_notes@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: Work step complete (ingest + synthesis done). "
                "Advance to finalize."
            )
        return None

    def should_auto_advance_after_capability(
        self,
        cap_id: str,
        result_ok: bool,
        *,
        step_kind: str = "",
    ) -> bool:
        if not result_ok:
            return False
        kind = (step_kind or self.step_kind or "").strip().lower()
        if cap_id == "cap.research.synthesize_notes@v1":
            return kind in ("work", "read", "search", "verify")
        if cap_id == "cap.research.ingest_offline@v1":
            # Dynamic offline work steps need synthesize before advance.
            return kind in ("read", "search", "verify")
        return False

    def advance_summary_for_capability(self, cap_id: str) -> str:
        if cap_id == "cap.research.ingest_offline@v1":
            return "Ingested offline sources into scratchpad."
        if cap_id == "cap.research.synthesize_notes@v1":
            return "Synthesized research notes."
        if cap_id == "cap.research.gather_web_sources@v1":
            return "Gathered web sources and saved notes."
        return f"Completed capability {cap_id}."


class CapabilityPersonaPolicy(CharacterBuildPolicy):
    """Character build act loop policy for capability invocations."""

    _WRITE_CAPS = frozenset({"cap.persona.write_initialization@v1"})
    _FINALIZE_CAPS = frozenset({"cap.persona.finalize@v1"})
    _GATHER_CAPS = frozenset({"cap.persona.gather_lore@v1"})
    _INGEST_CAPS = frozenset({"cap.persona.ingest_sources@v1"})

    def forbidden_capabilities_on_step(self) -> frozenset[str]:
        if self.step_kind in ("read", "search"):
            return self._WRITE_CAPS | self._FINALIZE_CAPS
        if self.step_kind == "synthesize":
            return self._GATHER_CAPS
        return frozenset()

    def validate_capability_call(
        self,
        cap_id: str,
        *,
        tools_succeeded: set[str] | None = None,
        **kwargs,
    ) -> str | None:
        cap_id = (cap_id or "").strip()
        forbidden = self.forbidden_capabilities_on_step()
        if cap_id in forbidden:
            if cap_id in self._WRITE_CAPS:
                return (
                    f"❌ OS BLOCK: {self.step_kind} step is ingest only. "
                    "Use cap.persona.ingest_sources@v1 or gather_lore; "
                    "write_initialization belongs on synthesize."
                )
            if cap_id in self._GATHER_CAPS:
                return (
                    "❌ OS BLOCK: gather_lore is not used on synthesize. "
                    "Call cap.persona.write_initialization@v1."
                )
            return (
                f"❌ OS BLOCK: `{cap_id}` is not allowed on persona {self.step_kind}."
            )
        succeeded = tools_succeeded or set()
        if (
            cap_id in self._INGEST_CAPS
            and "cap.persona.ingest_sources@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: Ingest already ran this step. "
                "Call mark_objective_complete to advance."
            )
        if (
            cap_id in self._WRITE_CAPS
            and "cap.persona.write_initialization@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: initialization.md already written this step. "
                "Advance to finalize."
            )
        return None

    def should_auto_advance_after_capability(
        self,
        cap_id: str,
        result_ok: bool,
        *,
        step_kind: str = "",
    ) -> bool:
        if not result_ok:
            return False
        kind = (step_kind or self.step_kind or "").strip().lower()
        if cap_id in self._INGEST_CAPS and kind in ("read", "search"):
            return True
        if cap_id in self._GATHER_CAPS and kind == "search":
            return True
        if cap_id in self._WRITE_CAPS and kind == "synthesize":
            return True
        return False

    def advance_summary_for_capability(self, cap_id: str) -> str:
        if cap_id in self._INGEST_CAPS:
            return "Ingested persona source material into scratchpad."
        if cap_id in self._GATHER_CAPS:
            return "Gathered persona lore."
        if cap_id in self._WRITE_CAPS:
            return "Wrote initialization.md."
        if cap_id in self._FINALIZE_CAPS:
            return "Finalized persona."
        return f"Completed capability {cap_id}."


class CapabilityLearnPolicy(LearnSyllabusPolicy):
    """Learn syllabus build act loop policy for capability invocations."""

    _WRITE_CAPS = frozenset({"cap.learn.write_syllabus@v1"})
    _FINALIZE_CAPS = frozenset({"cap.learn.finalize_course@v1"})
    _GATHER_CAPS = frozenset({"cap.learn.gather_topic_sources@v1"})
    _INGEST_CAPS = frozenset({"cap.learn.ingest_course_materials@v1"})
    _ASSESS_CAPS = frozenset({"cap.learn.generate_assessments@v1"})

    def forbidden_capabilities_on_step(self) -> frozenset[str]:
        if self.step_kind in ("read", "search"):
            return self._WRITE_CAPS | self._FINALIZE_CAPS | self._ASSESS_CAPS
        if self.step_kind == "synthesize":
            return self._GATHER_CAPS
        return frozenset()

    def validate_capability_call(
        self,
        cap_id: str,
        *,
        tools_succeeded: set[str] | None = None,
        **kwargs,
    ) -> str | None:
        cap_id = (cap_id or "").strip()
        forbidden = self.forbidden_capabilities_on_step()
        if cap_id in forbidden:
            if cap_id in self._WRITE_CAPS:
                return (
                    f"❌ OS BLOCK: {self.step_kind} step is ingest only. "
                    "write_syllabus belongs on synthesize."
                )
            return (
                f"❌ OS BLOCK: `{cap_id}` is not allowed on syllabus {self.step_kind}."
            )
        succeeded = tools_succeeded or set()
        if (
            cap_id in self._INGEST_CAPS
            and "cap.learn.ingest_course_materials@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: Course materials already ingested this step. "
                "Call mark_objective_complete to advance."
            )
        if (
            cap_id in self._WRITE_CAPS
            and "cap.learn.write_syllabus@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: syllabus.json already written this step. "
                "Advance to finalize."
            )
        if cap_id not in (
            "cap.learn.write_syllabus@v1",
            "cap.learn.ingest_course_materials@v1",
            "cap.learn.gather_topic_sources@v1",
            "cap.learn.finalize_course@v1",
            "cap.learn.generate_assessments@v1",
        ) and cap_id.startswith("cap.learn."):
            return (
                f"❌ OS BLOCK: Unknown/forbidden learn capability `{cap_id}`. "
                "On synthesize use only `cap.learn.write_syllabus@v1` with "
                "arguments.content = syllabus JSON string."
            )
        return None

    def should_auto_advance_after_capability(
        self,
        cap_id: str,
        result_ok: bool,
        *,
        step_kind: str = "",
    ) -> bool:
        if not result_ok:
            return False
        kind = (step_kind or self.step_kind or "").strip().lower()
        if cap_id in self._INGEST_CAPS and kind in ("read", "search"):
            return True
        if cap_id in self._GATHER_CAPS and kind == "search":
            return True
        if cap_id in self._WRITE_CAPS and kind == "synthesize":
            return True
        return False

    def advance_summary_for_capability(self, cap_id: str) -> str:
        if cap_id in self._INGEST_CAPS:
            return "Ingested course research into scratchpad."
        if cap_id in self._GATHER_CAPS:
            return "Gathered topic sources."
        if cap_id in self._WRITE_CAPS:
            return "Wrote syllabus.json."
        if cap_id in self._FINALIZE_CAPS:
            return "Finalized course."
        return f"Completed capability {cap_id}."


class CapabilityWritingPolicy(StepPolicy):
    """Writing act-loop policy for capability invocations."""

    _INIT_CAPS = frozenset({"cap.writing.init_document@v1"})
    _DRAFT_CAPS = frozenset({
        "cap.writing.draft_sections@v1",
        "cap.writing.read_outline@v1",
    })
    _WORK_CAPS = _INIT_CAPS | _DRAFT_CAPS
    _FINALIZE_CAPS = frozenset({
        "cap.writing.compile_document@v1",
        "cap.writing.finalize_deliverable@v1",
    })

    def __init__(
        self,
        *,
        mode: str = "writing",
        step_kind: str = "",
        writing_brief: dict | None = None,
    ) -> None:
        super().__init__(mode=mode, step_kind=step_kind)
        self.writing_brief = writing_brief

    def _should_advance_after_draft(self) -> bool:
        from agent.functions.writing_brief import WritingBrief
        from agent.functions.writing_scope import draft_scope_satisfied, load_draft_state

        brief = WritingBrief.from_plan_dict(self.writing_brief)
        if brief is None or brief.advance_when == "single_draft":
            return True
        if brief.advance_when == "manual":
            return False
        return draft_scope_satisfied(brief, load_draft_state())

    def forbidden_capabilities_on_step(self) -> frozenset[str]:
        if self.step_kind in ("write", "work"):
            return self._FINALIZE_CAPS
        if self.step_kind == "finalize":
            return self._WORK_CAPS
        return frozenset()

    def validate_capability_call(
        self,
        cap_id: str,
        *,
        tools_succeeded: set[str] | None = None,
        **kwargs,
    ) -> str | None:
        cap_id = (cap_id or "").strip()
        forbidden = self.forbidden_capabilities_on_step()
        if cap_id in forbidden:
            if cap_id in self._FINALIZE_CAPS:
                return (
                    "❌ OS BLOCK: compile/finalize belongs on the finalize step, "
                    "not work/write."
                )
            return (
                "❌ OS BLOCK: init/draft/read_outline is not allowed on finalize. "
                "Call `cap.writing.finalize_deliverable@v1`."
            )
        succeeded = tools_succeeded or set()
        if cap_id in self._INIT_CAPS and "cap.writing.init_document@v1" in succeeded:
            return (
                "❌ OS BLOCK: Document already initialized this step. "
                "Call `cap.writing.draft_sections@v1` or mark_objective_complete."
            )
        if cap_id in self._INIT_CAPS:
            try:
                from agent.tool_library.writing_tools import ACTIVE_DRAFT_FILE

                if ACTIVE_DRAFT_FILE.exists():
                    return (
                        "❌ OS BLOCK: Draft buffer already exists. "
                        "Call `cap.writing.draft_sections@v1` instead of init."
                    )
            except Exception:
                pass
        if cap_id.startswith("cap.writing.") and cap_id not in (
            "cap.writing.init_document@v1",
            "cap.writing.draft_sections@v1",
            "cap.writing.read_outline@v1",
            "cap.writing.ingest_sources@v1",
            "cap.writing.compile_document@v1",
            "cap.writing.finalize_deliverable@v1",
        ):
            return (
                f"❌ OS BLOCK: Unknown/forbidden writing capability `{cap_id}`. "
                "Do not invent capability IDs."
            )
        return None

    def should_auto_advance_after_capability(
        self,
        cap_id: str,
        result_ok: bool,
        *,
        step_kind: str = "",
    ) -> bool:
        if not result_ok:
            return False
        kind = (step_kind or self.step_kind or "").strip().lower()
        if cap_id in self._INIT_CAPS and kind in ("write", "work"):
            # Init alone must not advance — draft_sections (or mark_objective_complete) ends the step.
            return False
        if cap_id == "cap.writing.draft_sections@v1" and kind in ("write", "work"):
            return self._should_advance_after_draft()
        if cap_id == "cap.writing.ingest_sources@v1" and kind == "read":
            return True
        if cap_id in self._FINALIZE_CAPS and kind == "finalize":
            return True
        return False

    def advance_summary_for_capability(self, cap_id: str) -> str:
        if cap_id in self._INIT_CAPS:
            return "Initialized writing document."
        if cap_id == "cap.writing.draft_sections@v1":
            return "Drafted document section(s)."
        if cap_id == "cap.writing.read_outline@v1":
            return "Read document outline."
        if cap_id == "cap.writing.ingest_sources@v1":
            return "Ingested writing source material."
        if cap_id == "cap.writing.compile_document@v1":
            return "Compiled final document."
        if cap_id == "cap.writing.finalize_deliverable@v1":
            return "Finalized writing deliverable."
        return f"Completed capability {cap_id}."


class CapabilityCodePolicy(StepPolicy):
    """Code act-loop policy for capability invocations."""

    _SETUP = frozenset({"cap.dev.project_setup@v1"})
    _RECON = frozenset({
        "cap.dev.recon@v1",
        "cap.dev.read_region@v1",
    })
    _EDIT = frozenset({
        "cap.dev.edit_apply@v1",
        "cap.dev.create_file@v1",
        "cap.dev.write_docs@v1",
    })
    _TEST = frozenset({
        "cap.dev.run_tests@v1",
        "cap.dev.run_linter@v1",
    })
    _SYNC = frozenset({"cap.dev.sync_project@v1"})
    _RAW = frozenset({"cap.dev.raw_tool@v1"})

    def __init__(
        self,
        *,
        mode: str = "code",
        step_kind: str = "",
        allow_raw_tool: bool | None = None,
    ) -> None:
        super().__init__(mode=mode, step_kind=step_kind)
        if allow_raw_tool is None:
            import os

            allow_raw_tool = os.getenv("AQUILA_DEV_RAW_TOOL", "0").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        self.allow_raw_tool = bool(allow_raw_tool)

    def forbidden_capabilities_on_step(self) -> frozenset[str]:
        kind = (self.step_kind or "").strip().lower()
        if kind in ("explore", "read"):
            return self._EDIT | self._SYNC | self._TEST
        if kind in ("verify", "tdd_red", "tdd_green", "tdd_refactor"):
            return self._SETUP
        if kind == "finalize":
            return self._SETUP | self._RECON | frozenset({
                "cap.dev.edit_apply@v1",
                "cap.dev.write_docs@v1",
            })
        return frozenset()

    def validate_capability_call(
        self,
        cap_id: str,
        *,
        tools_succeeded: set[str] | None = None,
        **kwargs,
    ) -> str | None:
        cap_id = (cap_id or "").strip()
        if cap_id in self._RAW and not self.allow_raw_tool:
            return (
                "❌ OS BLOCK: `cap.dev.raw_tool@v1` is disabled. "
                "Set AQUILA_DEV_RAW_TOOL=1 for debug, or use composite caps."
            )
        forbidden = self.forbidden_capabilities_on_step()
        if cap_id in forbidden:
            return (
                f"❌ OS BLOCK: `{cap_id}` is not allowed on step_kind "
                f"`{self.step_kind}`. Use the step allowlist."
            )
        succeeded = tools_succeeded or set()
        kind = (self.step_kind or "").strip().lower()
        if cap_id == "cap.dev.create_file@v1" and kind == "finalize":
            fp = str(kwargs.get("file_path") or "").replace("\\", "/").lower()
            if not fp.endswith("readme.md"):
                return (
                    "❌ OS BLOCK (finalize): Only `README.md` may be created on "
                    "finalize. Use `file_path` = `README.md` with short docs in "
                    "`arguments.content`, then `cap.dev.sync_project@v1`."
                )
        if cap_id == "cap.dev.create_file@v1" and kind in (
            "work",
            "code",
            "tdd_red",
            "tdd_green",
            "micro",
        ):
            fp = str(kwargs.get("file_path") or "").strip()
            if fp:
                try:
                    from agent.tool_library import code_canvas_tools as canvas

                    if canvas.buffer_has_file(fp):
                        return (
                            f"❌ OS BLOCK: `{fp}` already exists in the buffer. "
                            "Use `cap.dev.edit_apply@v1` to modify it or "
                            "`cap.dev.run_tests@v1` if ready."
                        )
                except Exception:
                    pass
        if (
            cap_id == "cap.dev.sync_project@v1"
            and "cap.dev.sync_project@v1" in succeeded
        ):
            return (
                "❌ OS BLOCK: `cap.dev.sync_project@v1` already succeeded this step. "
                "Stop — the project is synced."
            )
        if cap_id == "cap.dev.project_setup@v1":
            if "cap.dev.project_setup@v1" in succeeded:
                return (
                    "❌ OS BLOCK: Project already set up this step. "
                    "Next: `cap.dev.create_file@v1` / `cap.dev.edit_apply@v1` "
                    "(TDD), not project_setup again."
                )
            try:
                from pathlib import Path

                from agent.storage import resolve_under_data_root
                from agent.tool_library.code_canvas_tools import get_active_project_scope

                scope = get_active_project_scope()
                if scope and scope.get("root"):
                    root = Path(str(scope["root"]))
                    if not root.is_absolute():
                        root = resolve_under_data_root(str(scope["root"]))
                    if root.exists():
                        name = scope.get("project_name") or "project"
                        return (
                            f"❌ OS BLOCK: Code project '{name}' already active "
                            f"(root exists). Skip setup; call "
                            "`cap.dev.create_file@v1` or `cap.dev.edit_apply@v1`."
                        )
            except Exception:
                pass
        if (
            cap_id == "cap.dev.recon@v1"
            and "cap.dev.recon@v1" in succeeded
            and kind in ("work", "code", "tdd_red", "tdd_green", "tdd_refactor", "")
        ):
            return (
                "❌ OS BLOCK: Recon already completed this step. "
                "Do not re-recon — call `cap.dev.create_file@v1` / "
                "`cap.dev.edit_apply@v1` / `cap.dev.run_tests@v1` next."
            )
        if cap_id == "cap.dev.recon@v1" and kind in (
            "work",
            "code",
            "tdd_red",
            "tdd_green",
            "tdd_refactor",
        ):
            try:
                from agent.tool_library.code_canvas_tools import _load_state

                state = _load_state() or {}
                raw = state.get("files")
                paths: list[str] = []
                if isinstance(raw, dict):
                    paths = [str(p) for p in raw.keys()]
                elif isinstance(raw, list):
                    for entry in raw:
                        if isinstance(entry, dict) and entry.get("path"):
                            paths.append(str(entry["path"]))
                if not paths:
                    return (
                        "❌ OS BLOCK (greenfield): Skip recon on an empty project. "
                        "Call `cap.dev.create_file@v1` with `file_path` and full "
                        "`arguments.content` for the next deliverable."
                    )
            except Exception:
                pass
        if cap_id == "cap.plan.update_checklist@v1" and kind in ("work", "code"):
            count = int(kwargs.get("update_checklist_step_count") or 0)
            if count >= 2:
                return (
                    "❌ OS BLOCK: Checklist updates are automatic after create_file / "
                    "run_tests. Use `cap.dev.create_file@v1` to write project files."
                )
            try:
                from agent.tool_library.code_canvas_tools import _load_state

                state = _load_state() or {}
                raw = state.get("files")
                paths: list[str] = []
                if isinstance(raw, dict):
                    paths = [str(p) for p in raw.keys()]
                elif isinstance(raw, list):
                    for entry in raw:
                        if isinstance(entry, dict) and entry.get("path"):
                            paths.append(str(entry["path"]))
                if not paths:
                    return (
                        "❌ OS BLOCK: No files in buffer yet. Call "
                        "`cap.dev.create_file@v1` first — checklist ticks automatically."
                    )
            except Exception:
                pass
        if cap_id == "cap.dev.edit_apply@v1" and kind in ("work", "code", "micro"):
            try:
                from agent.tool_library import code_canvas_tools as canvas

                fp = str(kwargs.get("file_path") or "").strip()
                if fp and not canvas.buffer_has_file(fp):
                    return (
                        f"❌ OS BLOCK: `{fp}` is not in the buffer. Use "
                        "`cap.dev.create_file@v1` with full `arguments.content` first."
                    )
            except Exception:
                pass
        if cap_id == "cap.dev.edit_apply@v1" and kind == "tdd_red":
            return (
                "❌ OS BLOCK (tdd_red): Use `cap.dev.create_file@v1` only — "
                "`file_path` = `tests/test_habit.py` and `arguments.content` = "
                "full pytest source. edit_apply is not allowed on this step."
            )
        if cap_id == "cap.dev.edit_apply@v1" and kind == "tdd_green":
            try:
                from agent.core.implementation_plan import is_code_impl_source_path
                from agent.tool_library.code_canvas_tools import _load_state

                state = _load_state() or {}
                raw = state.get("files")
                paths: list[str] = []
                if isinstance(raw, dict):
                    paths = [str(p) for p in raw.keys()]
                elif isinstance(raw, list):
                    for entry in raw:
                        if isinstance(entry, dict) and entry.get("path"):
                            paths.append(str(entry["path"]))
                if not any(is_code_impl_source_path(p) for p in paths):
                    return (
                        "❌ OS BLOCK (tdd_green): Create the implementation module "
                        "with `cap.dev.create_file@v1` (`file_path` + full CLI source "
                        "in `arguments.content`, e.g. `habit.py`) before edit_apply."
                    )
            except Exception:
                pass
        if cap_id == "cap.dev.read_region@v1" and kind in ("tdd_red", "tdd_green"):
            try:
                from agent.core.implementation_plan import (
                    is_code_impl_source_path,
                    is_code_test_path,
                )
                from agent.tool_library.code_canvas_tools import _load_state

                state = _load_state() or {}
                raw = state.get("files")
                paths: list[str] = []
                if isinstance(raw, dict):
                    paths = [str(p) for p in raw.keys()]
                elif isinstance(raw, list):
                    for entry in raw:
                        if isinstance(entry, dict) and entry.get("path"):
                            paths.append(str(entry["path"]))
                if kind == "tdd_red" and not any(is_code_test_path(p) for p in paths):
                    return (
                        "❌ OS BLOCK (tdd_red): Create failing tests first with "
                        "`cap.dev.create_file@v1` (`tests/test_habit.py` + full pytest "
                        "in `arguments.content`). read_region is not useful on an "
                        "empty greenfield project."
                    )
                if kind == "tdd_green" and not any(
                    is_code_impl_source_path(p) for p in paths
                ):
                    return (
                        "❌ OS BLOCK (tdd_green): Implement the module with "
                        "`cap.dev.create_file@v1` (impl `.py` + full CLI source in "
                        "`arguments.content`) before read_region."
                    )
            except Exception:
                pass
        if cap_id == "cap.dev.read_region@v1" and kind in (
            "tdd_red",
            "tdd_green",
            "work",
            "code",
        ):
            count = int(kwargs.get("read_region_step_count") or 0)
            if count >= 4:
                return (
                    f"❌ OS BLOCK: read_region called {count} times this step. "
                    "Stop reading — write code with `cap.dev.create_file@v1` or "
                    "`cap.dev.edit_apply@v1`."
                )
        if cap_id == "cap.dev.sync_project@v1" and kind == "finalize":
            count = int(kwargs.get("sync_project_step_count") or 0)
            if count >= 1:
                return (
                    "❌ OS BLOCK: sync_project already attempted this finalize step. "
                    "Create missing files (e.g. README.md) with "
                    "`cap.dev.create_file@v1`, then sync once."
                )
        if cap_id.startswith("cap.dev.") and cap_id not in (
            "cap.dev.project_setup@v1",
            "cap.dev.recon@v1",
            "cap.dev.read_region@v1",
            "cap.dev.edit_apply@v1",
            "cap.dev.create_file@v1",
            "cap.dev.run_tests@v1",
            "cap.dev.run_linter@v1",
            "cap.dev.sync_project@v1",
            "cap.dev.write_docs@v1",
            "cap.dev.light_coding_context@v1",
            "cap.dev.raw_tool@v1",
        ):
            return (
                f"❌ OS BLOCK: Unknown/forbidden code capability `{cap_id}`. "
                "Do not invent capability IDs."
            )
        return None

    def should_auto_advance_after_capability(
        self,
        cap_id: str,
        result_ok: bool,
        *,
        step_kind: str = "",
        result_summary: str = "",
        result_data: dict | None = None,
        milestone_tracker=None,
    ) -> bool:
        if not result_ok:
            return False
        kind = (step_kind or self.step_kind or "").strip().lower()
        if cap_id == "cap.dev.sync_project@v1" and kind == "finalize":
            return True
        if cap_id == "cap.dev.recon@v1" and kind in ("explore", "read"):
            return True
        if cap_id == "cap.dev.run_tests@v1" and kind in (
            "verify",
            "tdd_green",
            "tdd_refactor",
            "work",
            "code",
        ):
            if kind in ("work", "code") and milestone_tracker is not None:
                if not getattr(milestone_tracker.state, "file_edited", False):
                    return False
            low = (result_summary or "").lower()
            if "failed" in low and "0 failed" not in low:
                return False
            return "passed" in low or "0 failed" in low or "✅" in (result_summary or "")
        if kind == "tdd_red" and cap_id == "cap.dev.create_file@v1":
            fp = str((result_data or {}).get("file_path") or (result_data or {}).get("path") or "")
            return bool(fp) and "test" in fp.lower()
        if kind == "tdd_green" and cap_id == "cap.dev.create_file@v1":
            from agent.core.implementation_plan import is_code_impl_source_path

            fp = str((result_data or {}).get("file_path") or (result_data or {}).get("path") or "")
            return is_code_impl_source_path(fp)
        if kind == "work" and cap_id == "cap.dev.create_file@v1":
            fp = str((result_data or {}).get("file_path") or (result_data or {}).get("path") or "")
            return "readme" in fp.lower()
        if kind in ("work", "code") and milestone_tracker is not None:
            advance_fn = getattr(milestone_tracker, "should_suggest_advance", None)
            if callable(advance_fn) and advance_fn("code", is_final_step=False):
                return True
        return False

    def advance_summary_for_capability(self, cap_id: str) -> str:
        if cap_id == "cap.dev.project_setup@v1":
            return "Set up code project."
        if cap_id == "cap.dev.recon@v1":
            return "Completed code recon."
        if cap_id == "cap.dev.read_region@v1":
            return "Read file region."
        if cap_id == "cap.dev.edit_apply@v1":
            return "Applied code edit."
        if cap_id == "cap.dev.create_file@v1":
            return "Created buffer file."
        if cap_id == "cap.dev.run_tests@v1":
            return "Ran tests."
        if cap_id == "cap.dev.run_linter@v1":
            return "Ran linter."
        if cap_id == "cap.dev.sync_project@v1":
            return "Synced project to disk."
        if cap_id == "cap.dev.write_docs@v1":
            return "Wrote project documentation."
        return f"Completed capability {cap_id}."


def get_step_policy(
    mode: str,
    step_kind: str,
    *,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
    offline_research: bool = False,
    writing_brief: dict | None = None,
) -> StepPolicy:
    if mode == "character_build":
        return CapabilityPersonaPolicy(
            mode=mode,
            step_kind=step_kind,
            persona_research_lore=persona_research_lore,
        )
    if mode == "learn_syllabus_build":
        return CapabilityLearnPolicy(
            mode=mode,
            step_kind=step_kind,
            learn_syllabus_web=learn_syllabus_web,
        )
    if mode == "research":
        return CapabilityResearchPolicy(
            mode=mode,
            step_kind=step_kind,
            offline_research=offline_research,
        )
    if mode == "writing":
        return CapabilityWritingPolicy(
            mode=mode,
            step_kind=step_kind,
            writing_brief=writing_brief,
        )
    if mode == "code":
        return CapabilityCodePolicy(mode=mode, step_kind=step_kind)
    return StepPolicy(mode=mode, step_kind=step_kind)
