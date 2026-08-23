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


def get_step_policy(
    mode: str,
    step_kind: str,
    *,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
    offline_research: bool = False,
) -> StepPolicy:
    if mode == "character_build":
        return CharacterBuildPolicy(
            mode=mode,
            step_kind=step_kind,
            persona_research_lore=persona_research_lore,
        )
    if mode == "learn_syllabus_build":
        return LearnSyllabusPolicy(
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
    return StepPolicy(mode=mode, step_kind=step_kind)
