"""Tools for Learn Mode: syllabus build, assessments, archive indexing."""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from learn_index import format_retrieval_block, index_archive, search_index
from learn_registry import (
    MASTERY_TIER_MAX,
    SYLLABUS_MIN_NODES,
    advance_mastery_on_pass,
    assessments_dir,
    archive_outputs_dir,
    course_json_path,
    get_course,
    get_node,
    load_syllabus,
    new_assessment_id,
    save_assessment,
    save_course,
    save_syllabus,
    syllabus_path,
    validate_syllabus_structure,
)

_active_build: dict[str, Any] | None = None


def set_active_syllabus_build(instance_id: str, course_id: str) -> None:
    global _active_build
    _active_build = {
        "instance_id": instance_id,
        "course_id": course_id,
        "syllabus_written": False,
    }


def clear_active_syllabus_build() -> None:
    global _active_build
    _active_build = None


def get_active_syllabus_build() -> dict[str, Any] | None:
    return _active_build


def _build_root() -> Path | None:
    if not _active_build:
        return None
    from learn_registry import course_dir

    return course_dir(_active_build["instance_id"], _active_build["course_id"])


def syllabus_ready(instance_id: str, course_id: str) -> bool:
    data = load_syllabus(instance_id, course_id)
    if not data:
        return False
    nodes = [n for n in (data.get("nodes") or []) if isinstance(n, dict)]
    ok, _ = validate_syllabus_structure(nodes)
    return ok and data.get("status") != "building"


def write_syllabus_file(content: str) -> str:
    """Write syllabus.json for the active course build (JSON string)."""
    if not _active_build:
        return "❌ Error: No active syllabus build session."
    iid = _active_build["instance_id"]
    cid = _active_build["course_id"]
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON for syllabus: {e}"
    nodes = data.get("nodes") or []
    ok, err = validate_syllabus_structure(nodes)
    if not ok:
        return f"❌ Syllabus structure rejected: {err}"
    if _active_build.get("syllabus_written") or syllabus_ready(iid, cid):
        _active_build["syllabus_written"] = True
        return (
            "❌ OS BLOCK: syllabus.json already written. "
            "Call finalize_course then mark_objective_complete."
        )
    data.setdefault("version", 1)
    data.setdefault("status", "building")
    save_syllabus(iid, cid, data)
    _active_build["syllabus_written"] = True
    return (
        f"✅ Wrote syllabus with {len(nodes)} node(s). "
        "Call finalize_course then mark_objective_complete."
    )


def finalize_course() -> str:
    """Mark course and syllabus active after build."""
    if not _active_build:
        return "❌ Error: No active syllabus build session."
    iid = _active_build["instance_id"]
    cid = _active_build["course_id"]
    if not syllabus_ready(iid, cid):
        return "❌ Write syllabus.json first via write_syllabus_file."
    course = get_course(iid, cid)
    if not course:
        return "❌ Course record not found."
    syllabus = load_syllabus(iid, cid)
    if syllabus:
        syllabus["status"] = "active"
        save_syllabus(iid, cid, syllabus)
    course.build_complete = True
    save_course(iid, course)
    clear_active_syllabus_build()
    return f"✅ Course '{course.title}' finalized and ready for tutoring."


def generate_assessment(
    node_id: str,
    target_tier: int,
    questions_json: str,
    passing_score: float = 70.0,
) -> str:
    """Create assessment JSON for a syllabus node (questions_json = JSON array)."""
    if not _active_build:
        iid = None
        cid = None
    else:
        iid = _active_build["instance_id"]
        cid = _active_build["course_id"]
    if not iid or not cid:
        return "❌ Error: generate_assessment during build needs active session, or use GUI."
    syllabus = load_syllabus(iid, cid)
    if not syllabus:
        return "❌ No syllabus found."
    node = get_node(syllabus, node_id)
    if not node:
        return f"❌ Unknown node_id '{node_id}'."
    try:
        questions = json.loads(questions_json)
        if not isinstance(questions, list) or not questions:
            return "❌ questions_json must be a non-empty JSON array."
    except json.JSONDecodeError as e:
        return f"❌ Invalid questions_json: {e}"
    aid = new_assessment_id()
    tier = max(0, min(MASTERY_TIER_MAX, int(target_tier)))
    spec = {
        "id": aid,
        "node_id": node_id,
        "target_tier": tier,
        "passing_score": float(passing_score),
        "questions": questions,
    }
    save_assessment(iid, cid, aid, spec)
    node["required_assessment_id"] = aid
    assessments = syllabus.get("assessments") or []
    if not isinstance(assessments, list):
        assessments = []
    assessments.append({"id": aid, "node_id": node_id, "target_tier": tier})
    syllabus["assessments"] = assessments
    save_syllabus(iid, cid, syllabus)
    return f"✅ Assessment {aid} saved ({len(questions)} questions, tier {tier})."


def _instance_id() -> str | None:
    if _active_build:
        return _active_build["instance_id"]
    if _learn_runtime:
        return _learn_runtime.get("instance_id")
    return None


def record_assessment_result(
    course_id: str,
    node_id: str,
    assessment_id: str,
    score_percent: float,
) -> str:
    """Record score and bump mastery tier if passing."""
    iid = _instance_id()
    if not iid:
        return "❌ Error: set course context via GUI for assessment grading."
    if not iid:
        return "❌ Error: missing instance_id."
    syllabus = load_syllabus(iid, course_id)
    if not syllabus:
        return "❌ Syllabus not found."
    from learn_registry import load_assessment

    spec = load_assessment(iid, course_id, assessment_id)
    if not spec:
        return "❌ Assessment not found."
    passing = float(spec.get("passing_score", 70))
    syllabus, msg = advance_mastery_on_pass(syllabus, node_id, float(score_percent), passing)
    save_syllabus(iid, course_id, syllabus)
    return f"✅ {msg}"


def set_mastery_tier(course_id: str, node_id: str, tier: int) -> str:
    """Set node mastery tier (0-5) — tutor override."""
    iid = _instance_id()
    if not iid:
        return "❌ Error: no active learn session."
    syllabus = load_syllabus(iid, course_id)
    if not syllabus:
        return "❌ Syllabus not found."
    node = get_node(syllabus, node_id)
    if not node:
        return f"❌ Unknown node '{node_id}'."
    node["mastery_tier"] = max(0, min(MASTERY_TIER_MAX, int(tier)))
    save_syllabus(iid, course_id, syllabus)
    return f"✅ Set '{node.get('title')}' to tier {node['mastery_tier']}."


def index_archive_sources(archive_id: str) -> str:
    iid = _instance_id()
    if not iid:
        return "❌ Error: no active learn session for indexing."
    return index_archive(iid, archive_id)


def search_archive_sources(archive_id: str, query: str, top_k: int = 5) -> str:
    iid = _instance_id()
    if not iid:
        return "❌ Error: no active learn session."
    hits = search_index(iid, "archive", archive_id, query, top_k=int(top_k))
    if not hits:
        return "No results — index archive sources first."
    return format_retrieval_block(hits, "ARCHIVE")


def generate_archive_quiz(archive_id: str, content_markdown: str) -> str:
    """Save quiz markdown under archive outputs/."""
    iid = _instance_id()
    if not iid:
        return "❌ Error: no active learn session."
    out = archive_outputs_dir(iid, archive_id)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out / f"quiz_{ts}.md"
    path.write_text((content_markdown or "").strip() + "\n", encoding="utf-8")
    return f"✅ Wrote quiz to {path.as_posix()}"


def generate_archive_study_doc(archive_id: str, content_markdown: str) -> str:
    iid = _instance_id()
    if not iid:
        return "❌ Error: no active learn session."
    out = archive_outputs_dir(iid, archive_id)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out / f"study_guide_{ts}.md"
    path.write_text((content_markdown or "").strip() + "\n", encoding="utf-8")
    return f"✅ Wrote study guide to {path.as_posix()}"


# Runtime context for non-build tools (GUI sets this)
_learn_runtime: dict[str, str] | None = None


def set_learn_runtime(instance_id: str, course_id: str = "", archive_id: str = "") -> None:
    global _learn_runtime, _active_build
    _learn_runtime = {
        "instance_id": instance_id,
        "course_id": course_id,
        "archive_id": archive_id,
    }
    if course_id:
        _active_build = {
            "instance_id": instance_id,
            "course_id": course_id,
            "syllabus_written": True,
        }


def clear_learn_runtime() -> None:
    global _learn_runtime
    _learn_runtime = None


LEARN_TOOLS = {
    "write_syllabus_file": {
        "func": write_syllabus_file,
        "description": inspect.getdoc(write_syllabus_file),
    },
    "finalize_course": {
        "func": finalize_course,
        "description": inspect.getdoc(finalize_course),
    },
    "generate_assessment": {
        "func": generate_assessment,
        "description": inspect.getdoc(generate_assessment),
    },
    "record_assessment_result": {
        "func": record_assessment_result,
        "description": inspect.getdoc(record_assessment_result),
    },
    "set_mastery_tier": {
        "func": set_mastery_tier,
        "description": inspect.getdoc(set_mastery_tier),
    },
    "index_archive_sources": {
        "func": index_archive_sources,
        "description": inspect.getdoc(index_archive_sources),
    },
    "search_archive_sources": {
        "func": search_archive_sources,
        "description": inspect.getdoc(search_archive_sources),
    },
    "generate_archive_quiz": {
        "func": generate_archive_quiz,
        "description": inspect.getdoc(generate_archive_quiz),
    },
    "generate_archive_study_doc": {
        "func": generate_archive_study_doc,
        "description": inspect.getdoc(generate_archive_study_doc),
    },
}
