"""Learn workspace helpers for the Remote Companion REST endpoints.

Wrappers over :mod:`learn_registry` / :mod:`learn_index` that return
JSON-serializable data and mirror the desktop GUI's course/archive flows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


# --- courses ---------------------------------------------------------------

def _course_info(c: Any) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "topic": c.topic,
        "intake": c.intake,
        "build_complete": bool(c.build_complete),
        "created_at": c.created_at,
    }


def list_courses(instance_id: str) -> list[dict[str, Any]]:
    import learn_registry as lr

    return [_course_info(c) for c in lr.list_courses(instance_id)]


def get_syllabus(instance_id: str, course_id: str) -> Optional[dict[str, Any]]:
    import learn_registry as lr

    return lr.load_syllabus(instance_id, course_id)


def tutor_history(instance_id: str, course_id: str) -> list[dict[str, str]]:
    import learn_registry as lr

    return lr.load_tutor_history(instance_id, course_id)


def create_course_for_build(
    instance_id: str, title: str, topic: str, intake: str, web: bool
) -> dict[str, Any]:
    """Mirror learn_page._start_syllabus_build (minus source copy/index)."""
    import learn_registry as lr
    from agent.storage import agent_data_path

    topic = (topic or title).strip()
    course = lr.create_course(instance_id, title, topic, intake)
    lr.course_sources_dir(instance_id, course.id).mkdir(parents=True, exist_ok=True)
    web = bool(web or intake == "topic_web")
    lore = (
        "User enabled web research — use web_search on the search step."
        if web
        else "Do NOT use web_search unless attachments are insufficient."
    )
    placement_note = (
        "Placement intake: synthesize syllabus weighted toward typical weak areas "
        "from user topic (MVP: infer from topic text, no separate quiz UI)."
        if intake == "placement"
        else ""
    )
    prompt = (
        f"Build a learning syllabus for course '{course.title}'.\n"
        f"Topic: {topic}\nIntake: {intake}\ncourse_id={course.id}\n{lore}\n{placement_note}\n"
        f"Steps: ingest → write_syllabus_file (≥8 nodes, ≥5 sub-units in a module/lesson tree) "
        f"→ finalize_course."
    )
    task_name = f"syllabus_build_{course.id}"
    stale = agent_data_path("Agent-Tasks", f"{task_name}.json")
    if stale.is_file():
        try:
            stale.unlink()
        except OSError:
            pass
    return {
        "course": _course_info(course),
        "task_name": task_name,
        "mode": "learn_syllabus_build",
        "prompt": prompt,
        "learn_syllabus_web": web,
    }


def delete_course(instance_id: str, course_id: str) -> None:
    import learn_registry as lr

    lr.delete_course(instance_id, course_id)


def add_course_sources(
    instance_id: str, course_id: str, named_bytes: list[tuple[str, bytes]]
) -> str:
    import learn_registry as lr
    from agent.storage import index_course_sources

    dest = lr.course_sources_dir(instance_id, course_id)
    dest.mkdir(parents=True, exist_ok=True)
    _write_sources(dest, named_bytes)
    return index_course_sources(instance_id, course_id)


def list_assessments(instance_id: str, course_id: str) -> list[dict[str, Any]]:
    import learn_registry as lr

    syllabus = lr.load_syllabus(instance_id, course_id) or {}
    out: list[dict[str, Any]] = []
    for node in syllabus.get("nodes", []) or []:
        aid = node.get("required_assessment_id")
        if not aid:
            continue
        spec = lr.load_assessment(instance_id, course_id, aid) or {}
        questions = []
        for q in spec.get("questions") or []:
            if isinstance(q, dict):
                questions.append(q.get("prompt") or q.get("question") or str(q))
            else:
                questions.append(str(q))
        out.append(
            {
                "node_id": node.get("id"),
                "node_title": node.get("title"),
                "assessment_id": aid,
                "mastery_tier": int(node.get("mastery_tier", 0)),
                "passing_score": float(spec.get("passing_score", 70)),
                "questions": questions,
            }
        )
    return out


def submit_assessment(
    instance_id: str, course_id: str, node_id: str, assessment_id: str, score: float
) -> dict[str, Any]:
    from tool_library.learn_tools import record_assessment_result, set_learn_runtime

    set_learn_runtime(instance_id, course_id=course_id)
    message = record_assessment_result(course_id, node_id, assessment_id, float(score))
    return {"message": message, "syllabus": get_syllabus(instance_id, course_id)}


# --- archives --------------------------------------------------------------

def _archive_info(a: Any) -> dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "created_at": a.created_at,
        "source_count": a.source_count,
        "index_ready": bool(a.index_ready),
        "chunk_count": a.chunk_count,
    }


def list_archives(instance_id: str) -> list[dict[str, Any]]:
    import learn_registry as lr

    return [_archive_info(a) for a in lr.list_archives(instance_id)]


def create_archive(instance_id: str, title: str) -> dict[str, Any]:
    import learn_registry as lr

    archive = lr.create_archive(instance_id, title)
    lr.archive_sources_dir(instance_id, archive.id).mkdir(parents=True, exist_ok=True)
    return _archive_info(archive)


def delete_archive(instance_id: str, archive_id: str) -> None:
    import learn_registry as lr

    root = lr.archive_dir(instance_id, archive_id)
    if root.is_dir():
        import shutil

        shutil.rmtree(root, ignore_errors=True)


def archive_history(instance_id: str, archive_id: str) -> list[dict[str, str]]:
    import learn_registry as lr

    return lr.load_archive_chat_history(instance_id, archive_id)


def add_archive_sources(
    instance_id: str, archive_id: str, named_bytes: list[tuple[str, bytes]]
) -> str:
    import learn_registry as lr
    from agent.storage import index_archive

    dest = lr.archive_sources_dir(instance_id, archive_id)
    dest.mkdir(parents=True, exist_ok=True)
    _write_sources(dest, named_bytes)
    return index_archive(instance_id, archive_id)


def _write_sources(dest: Path, named_bytes: list[tuple[str, bytes]]) -> None:
    for name, content in named_bytes:
        safe = Path(name or "file").name or "file"
        target = dest / safe
        counter = 1
        while target.exists():
            target = dest / f"{target.stem}_{counter}{target.suffix}"
            counter += 1
        try:
            target.write_bytes(content)
        except OSError:
            pass
