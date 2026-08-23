"""Capability-first plan step descriptions for capability-act modes."""
from __future__ import annotations

import re

# Outcome-focused copy keyed by (mode, variant, step_kind). No raw tool names.

_PERSONA_COPY: dict[str, str] = {
    "read": (
        "Ingest user description and attachments into scratchpad "
        "(cap.persona.ingest_sources@v1)."
    ),
    "synthesize": (
        "Write initialization.md once from scratchpad "
        "(cap.persona.write_initialization@v1; minimum ~800 characters)."
    ),
    "finalize": (
        "Finalize persona with greeting and tagline "
        "(cap.persona.finalize@v1)."
    ),
}

_PERSONA_LORE_COPY: dict[str, str] = {
    "search": (
        "Gather character lore from web sources into scratchpad "
        "(cap.persona.gather_lore@v1)."
    ),
    "read": (
        "Merge user description and attachments into scratchpad "
        "(cap.persona.ingest_sources@v1)."
    ),
    "synthesize": _PERSONA_COPY["synthesize"],
    "finalize": _PERSONA_COPY["finalize"],
}

_LEARN_COPY: dict[str, str] = {
    "read": (
        "Ingest uploaded course materials and user brief into scratchpad "
        "(cap.learn.ingest_course_materials@v1)."
    ),
    "synthesize": (
        "Write syllabus JSON once from scratchpad "
        "(cap.learn.write_syllabus@v1; ≥8 nodes, ≥5 sub-units with parent_id)."
    ),
    "finalize": (
        "Finalize course record and complete build "
        "(cap.learn.finalize_course@v1)."
    ),
}

_LEARN_WEB_COPY: dict[str, str] = {
    "search": (
        "Gather topic sources from the web into scratchpad "
        "(cap.learn.gather_topic_sources@v1)."
    ),
    "read": _LEARN_COPY["read"],
    "synthesize": _LEARN_COPY["synthesize"],
    "finalize": _LEARN_COPY["finalize"],
}

_RESEARCH_COPY: dict[str, str] = {
    "explore": "Reconnaissance: survey sources before deeper research work.",
    "search": "Gather web sources on the research topic.",
    "read": "Read and extract key facts from URLs or attachments.",
    "synthesize": "Synthesize findings into scratchpad notes.",
    "finalize": "Compile final report and finalize deliverable.",
    "work": "Research work: gather sources, ingest attachments, synthesize notes.",
    "write": "Draft the assigned writing section.",
    "code": "Implement or edit code for this step.",
    "verify": "Verify outputs (tests, grep, lint).",
}

# Tokens that indicate pre-capability planner leakage in step descriptions.
TOOL_LEAK_TOKENS: frozenset[str] = frozenset({
    "web_search",
    "read_webpage",
    "save_research_note",
    "read_all_research_notes",
    "write_syllabus_file",
    "write_persona_file",
    "finalize_persona",
    "finalize_course",
    "finish_task",
    "generate_assessment",
})

_RESEARCH_TOOL_LEAK = frozenset({
    "web_search",
    "read_webpage",
    "save_research_note",
    "finish_task",
    "read_all_research_notes",
})

_CHARACTER_TOOL_LEAK = frozenset({
    "web_search",
    "read_webpage",
    "save_research_note",
    "write_persona_file",
    "finalize_persona",
    "read_all_research_notes",
    "finish_task",
})

_LEARN_TOOL_LEAK = frozenset({
    "web_search",
    "read_webpage",
    "save_research_note",
    "write_syllabus_file",
    "finalize_course",
    "generate_assessment",
    "read_all_research_notes",
    "finish_task",
})


def _copy_table(
    mode: str,
    *,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> dict[str, str]:
    if mode == "character_build":
        return _PERSONA_LORE_COPY if persona_research_lore else _PERSONA_COPY
    if mode == "learn_syllabus_build":
        return _LEARN_WEB_COPY if learn_syllabus_web else _LEARN_COPY
    if mode == "research":
        return _RESEARCH_COPY
    return {}


def capability_step_body(
    mode: str,
    step_kind: str,
    *,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> str:
    """Outcome-focused description body without Topic suffix."""
    table = _copy_table(
        mode,
        persona_research_lore=persona_research_lore,
        learn_syllabus_web=learn_syllabus_web,
    )
    kind = (step_kind or "").strip().lower()
    if kind in table:
        return table[kind]
    return f"Complete {kind or 'step'}."


def short_topic_for_plan(user_request: str, *, max_chars: int = 160) -> str:
    """
    Extract a short, human topic for plan step Topic: / user_goal.

    Learn/Character GUI prompts historically embed intake metadata, tool names,
    and pipeline instructions — those must not appear in every step description.
    """
    text = (user_request or "").strip()
    if not text:
        return "the task"

    # Prefer quoted course / persona titles from the lead sentence.
    for pattern in (
        r"course\s+'([^']+)'",
        r'course\s+"([^"]+)"',
        r"Display name:\s*(.+)",
        r"^Build a learning syllabus for course\s+'([^']+)'",
        r'^Build a learning syllabus for course\s+"([^"]+)"',
    ):
        m = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            title = m.group(1).strip()
            if title:
                return title[:max_chars]

    # First non-empty line, then strip known boilerplate fragments.
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), text)
    first = strip_planner_boilerplate(first)
    first = re.sub(
        r"\b(?:Intake|course_id|Persona id)\s*[:=]\s*\S+",
        "",
        first,
        flags=re.IGNORECASE,
    )
    first = re.sub(r"\s{2,}", " ", first).strip(" .;")
    if not first:
        first = "the task"
    return first[:max_chars]


def capability_step_description(
    mode: str,
    step_kind: str,
    user_request: str = "",
    *,
    persona_research_lore: bool = False,
    learn_syllabus_web: bool = False,
) -> str:
    """Canonical capability-first step description with a single Topic suffix."""
    topic = short_topic_for_plan(user_request)
    body = capability_step_body(
        mode,
        step_kind,
        persona_research_lore=persona_research_lore,
        learn_syllabus_web=learn_syllabus_web,
    )
    return f"{body} Topic: {topic}."


def has_tool_leak(description: str, tokens: frozenset[str]) -> bool:
    """True if description contains legacy tool names outside capability IDs."""
    lower = (description or "").lower()
    stripped = re.sub(r"cap\.\w+\.\w+@v\d+", "", lower)
    return any(tok in stripped for tok in tokens)


def tool_leak_tokens_for_mode(mode: str) -> frozenset[str]:
    if mode == "character_build":
        return _CHARACTER_TOOL_LEAK
    if mode == "learn_syllabus_build":
        return _LEARN_TOOL_LEAK
    if mode == "research":
        return _RESEARCH_TOOL_LEAK
    return TOOL_LEAK_TOKENS


def strip_planner_boilerplate(description: str) -> str:
    """Remove common LLM planner leakage from step descriptions."""
    text = (description or "").strip()
    if not text:
        return text

    # Drop embedded pipeline instructions (often repeated per step).
    text = re.sub(
        r"\bSteps:\s*ingest\s*→.*?finalize[^\.\n]*\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bDo NOT use web_search unless attachments are[^\.\n]*\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bFiction Intake:[^\.\n]*\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Keep only the first Topic: block.
    topic_parts = re.split(r"(?<=\.)\s*Topic:\s*", text, maxsplit=1, flags=re.IGNORECASE)
    if len(topic_parts) > 1:
        first = topic_parts[0].strip()
        rest = topic_parts[1]
        # If the first segment already ends with topic-like content, drop duplicate tail.
        if re.search(r"Topic:\s*", rest, flags=re.IGNORECASE):
            text = first
        else:
            text = f"{first} Topic: {rest.strip()}"

    # Collapse repeated "Topic: X. Topic: X." patterns.
    while True:
        collapsed = re.sub(
            r"(Topic:\s*[^.]+\.)\s*\1",
            r"\1",
            text,
            flags=re.IGNORECASE,
        )
        if collapsed == text:
            break
        text = collapsed

    return re.sub(r"\s{2,}", " ", text).strip()
