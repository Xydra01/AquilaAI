"""Per-instance Learn Mode storage: courses (syllabus ledger) and archives."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from instance_registry import instance_dir

SYLLABUS_VERSION = 1
MAX_CHAT_TURNS = 40
MAX_CHAT_CHARS = 120_000
MASTERY_TIER_MAX = 5
# Syllabus build quality gates (reject shallow outlines)
SYLLABUS_MIN_NODES = 8
SYLLABUS_MIN_CHILD_NODES = 5  # units with parent_id (subtopics under modules)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "item").lower()).strip("-")
    return slug[:64] or "item"


def learn_root(instance_id: str) -> Path:
    return instance_dir(instance_id) / "learn"


def courses_root(instance_id: str) -> Path:
    return learn_root(instance_id) / "courses"


def archives_root(instance_id: str) -> Path:
    return learn_root(instance_id) / "archives"


def course_dir(instance_id: str, course_id: str) -> Path:
    return courses_root(instance_id) / course_id


def course_json_path(instance_id: str, course_id: str) -> Path:
    return course_dir(instance_id, course_id) / "course.json"


def syllabus_path(instance_id: str, course_id: str) -> Path:
    return course_dir(instance_id, course_id) / "syllabus.json"


def course_sources_dir(instance_id: str, course_id: str) -> Path:
    return course_dir(instance_id, course_id) / "sources"


def assessments_dir(instance_id: str, course_id: str) -> Path:
    return course_dir(instance_id, course_id) / "assessments"


def tutor_history_path(instance_id: str, course_id: str) -> Path:
    return course_dir(instance_id, course_id) / "tutor_history.json"


def archive_dir(instance_id: str, archive_id: str) -> Path:
    return archives_root(instance_id) / archive_id


def archive_json_path(instance_id: str, archive_id: str) -> Path:
    return archive_dir(instance_id, archive_id) / "archive.json"


def archive_sources_dir(instance_id: str, archive_id: str) -> Path:
    return archive_dir(instance_id, archive_id) / "sources"


def archive_outputs_dir(instance_id: str, archive_id: str) -> Path:
    return archive_dir(instance_id, archive_id) / "outputs"


def archive_chat_history_path(instance_id: str, archive_id: str) -> Path:
    return archive_dir(instance_id, archive_id) / "chat_history.json"


@dataclass
class Course:
    id: str
    title: str
    topic: str = ""
    intake: str = "files"  # files | topic_web | placement
    created_at: str = ""
    build_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Course":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "Course")),
            topic=str(data.get("topic", "")),
            intake=str(data.get("intake", "files")),
            created_at=str(data.get("created_at", "")),
            build_complete=bool(data.get("build_complete", False)),
        )


@dataclass
class Archive:
    id: str
    title: str
    created_at: str = ""
    source_count: int = 0
    index_ready: bool = False
    chunk_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Archive":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "Archive")),
            created_at=str(data.get("created_at", "")),
            source_count=int(data.get("source_count", 0)),
            index_ready=bool(data.get("index_ready", False)),
            chunk_count=int(data.get("chunk_count", 0)),
        )


def default_syllabus(title: str, topic: str, intake: str) -> dict[str, Any]:
    root_id = "root"
    return {
        "version": SYLLABUS_VERSION,
        "title": title,
        "topic": topic,
        "intake": intake,
        "status": "building",
        "current_node_id": root_id,
        "nodes": [
            {
                "id": root_id,
                "title": title or "Course overview",
                "parent_id": None,
                "order": 0,
                "mastery_tier": 0,
                "tier_gate": 0,
                "required_assessment_id": None,
            }
        ],
        "assessments": [],
    }


def load_syllabus(instance_id: str, course_id: str) -> dict[str, Any] | None:
    path = syllabus_path(instance_id, course_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_syllabus(instance_id: str, course_id: str, data: dict[str, Any]) -> None:
    path = syllabus_path(instance_id, course_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def validate_syllabus_structure(nodes: list[Any]) -> tuple[bool, str]:
    """Ensure syllabus has enough units and a real hierarchy (not 3 flat bullets)."""
    valid = [n for n in nodes if isinstance(n, dict) and n.get("id") and n.get("title")]
    if len(valid) < SYLLABUS_MIN_NODES:
        return (
            False,
            f"Need at least {SYLLABUS_MIN_NODES} learning units (got {len(valid)}). "
            "Add modules and subtopics from the course material.",
        )
    children = [n for n in valid if n.get("parent_id")]
    if len(children) < SYLLABUS_MIN_CHILD_NODES:
        return (
            False,
            f"Need at least {SYLLABUS_MIN_CHILD_NODES} sub-units with parent_id "
            f"(got {len(children)}). Use a tree: 1 root → 3–5 modules → 2–4 lessons each.",
        )
    roots = [n for n in valid if not n.get("parent_id")]
    if not roots:
        return False, "Include at least one root node (parent_id null)."
    return True, ""


def get_node(syllabus: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in syllabus.get("nodes") or []:
        if isinstance(n, dict) and n.get("id") == node_id:
            return n
    return None


def node_children(syllabus: dict[str, Any], parent_id: str | None) -> list[dict[str, Any]]:
    nodes = [n for n in (syllabus.get("nodes") or []) if isinstance(n, dict)]
    return sorted(
        [n for n in nodes if n.get("parent_id") == parent_id],
        key=lambda x: int(x.get("order", 0)),
    )


def is_node_unlocked(syllabus: dict[str, Any], node: dict[str, Any]) -> bool:
    parent_id = node.get("parent_id")
    if not parent_id:
        return True
    parent = get_node(syllabus, parent_id)
    if not parent:
        return True
    gate = int(parent.get("tier_gate", 1))
    return int(parent.get("mastery_tier", 0)) >= gate


def syllabus_excerpt(syllabus: dict[str, Any], max_chars: int = 4000) -> str:
    lines = [f"# {syllabus.get('title', 'Course')}", f"Topic: {syllabus.get('topic', '')}"]
    for n in syllabus.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        indent = "  " if n.get("parent_id") else ""
        lines.append(
            f"{indent}- [{n.get('id')}] {n.get('title')} (tier {n.get('mastery_tier', 0)}/5)"
        )
    text = "\n".join(lines)
    return text[:max_chars]


def list_courses(instance_id: str) -> list[Course]:
    root = courses_root(instance_id)
    if not root.is_dir():
        return []
    out: list[Course] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            c = get_course(instance_id, child.name)
            if c:
                out.append(c)
    return sorted(out, key=lambda c: c.created_at, reverse=True)


def get_course(instance_id: str, course_id: str) -> Course | None:
    path = course_json_path(instance_id, course_id)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return Course.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
        return None


def create_course(
    instance_id: str,
    title: str,
    topic: str = "",
    intake: str = "files",
    *,
    course_id: str | None = None,
) -> Course:
    base = course_id or _slugify(title)
    candidate = base
    n = 1
    while course_json_path(instance_id, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    now = _now_iso()
    course = Course(
        id=candidate,
        title=title.strip() or "Untitled course",
        topic=(topic or title).strip(),
        intake=intake if intake in ("files", "topic_web", "placement") else "files",
        created_at=now,
        build_complete=False,
    )
    cdir = course_dir(instance_id, course.id)
    cdir.mkdir(parents=True, exist_ok=True)
    course_sources_dir(instance_id, course.id).mkdir(exist_ok=True)
    assessments_dir(instance_id, course.id).mkdir(exist_ok=True)
    with open(course_json_path(instance_id, course.id), "w", encoding="utf-8") as f:
        json.dump(course.to_dict(), f, indent=2)
    save_syllabus(
        instance_id,
        course.id,
        default_syllabus(course.title, course.topic, course.intake),
    )
    return course


def save_course(instance_id: str, course: Course) -> Course:
    course_dir(instance_id, course.id).mkdir(parents=True, exist_ok=True)
    with open(course_json_path(instance_id, course.id), "w", encoding="utf-8") as f:
        json.dump(course.to_dict(), f, indent=2)
    return course


def delete_course(instance_id: str, course_id: str) -> None:
    import shutil

    root = course_dir(instance_id, course_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def list_archives(instance_id: str) -> list[Archive]:
    root = archives_root(instance_id)
    if not root.is_dir():
        return []
    out: list[Archive] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            a = get_archive(instance_id, child.name)
            if a:
                out.append(a)
    return sorted(out, key=lambda a: a.created_at, reverse=True)


def get_archive(instance_id: str, archive_id: str) -> Archive | None:
    path = archive_json_path(instance_id, archive_id)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return Archive.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
        return None


def create_archive(
    instance_id: str,
    title: str,
    *,
    archive_id: str | None = None,
) -> Archive:
    base = archive_id or _slugify(title)
    candidate = base
    n = 1
    while archive_json_path(instance_id, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    now = _now_iso()
    archive = Archive(id=candidate, title=title.strip() or "Untitled archive", created_at=now)
    adir = archive_dir(instance_id, archive.id)
    adir.mkdir(parents=True, exist_ok=True)
    archive_sources_dir(instance_id, archive.id).mkdir(exist_ok=True)
    archive_outputs_dir(instance_id, archive.id).mkdir(exist_ok=True)
    with open(archive_json_path(instance_id, archive.id), "w", encoding="utf-8") as f:
        json.dump(archive.to_dict(), f, indent=2)
    return archive


def save_archive(instance_id: str, archive: Archive) -> Archive:
    archive_dir(instance_id, archive.id).mkdir(parents=True, exist_ok=True)
    with open(archive_json_path(instance_id, archive.id), "w", encoding="utf-8") as f:
        json.dump(archive.to_dict(), f, indent=2)
    return archive


def delete_archive(instance_id: str, archive_id: str) -> None:
    import shutil

    root = archive_dir(instance_id, archive_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def load_tutor_history(instance_id: str, course_id: str) -> list[dict[str, str]]:
    path = tutor_history_path(instance_id, course_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict) and m.get("role")]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_tutor_history(
    instance_id: str, course_id: str, messages: list[dict[str, str]]
) -> None:
    path = tutor_history_path(instance_id, course_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = messages[-MAX_CHAT_TURNS:]
    while trimmed and sum(len(m.get("content", "")) for m in trimmed) > MAX_CHAT_CHARS:
        trimmed = trimmed[2:]
    path.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")


def trim_chat_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep recent turns within Learn chat caps (archive + tutor)."""
    trimmed = [m for m in messages if isinstance(m, dict) and m.get("role")]
    trimmed = trimmed[-MAX_CHAT_TURNS:]
    while trimmed and sum(len(m.get("content", "")) for m in trimmed) > MAX_CHAT_CHARS:
        trimmed = trimmed[2:]
    return trimmed


def load_archive_chat_history(instance_id: str, archive_id: str) -> list[dict[str, str]]:
    path = archive_chat_history_path(instance_id, archive_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return trim_chat_messages(
                [m for m in data if isinstance(m, dict) and m.get("role")]
            )
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_archive_chat_history(
    instance_id: str, archive_id: str, messages: list[dict[str, str]]
) -> None:
    path = archive_chat_history_path(instance_id, archive_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(trim_chat_messages(messages), indent=2), encoding="utf-8"
    )


def load_assessment(instance_id: str, course_id: str, assessment_id: str) -> dict[str, Any] | None:
    path = assessments_dir(instance_id, course_id) / f"{assessment_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_assessment(
    instance_id: str, course_id: str, assessment_id: str, data: dict[str, Any]
) -> None:
    path = assessments_dir(instance_id, course_id) / f"{assessment_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def new_assessment_id() -> str:
    return f"assess_{uuid.uuid4().hex[:10]}"


def advance_mastery_on_pass(
    syllabus: dict[str, Any],
    node_id: str,
    score: float,
    passing_score: float,
) -> tuple[dict[str, Any], str]:
    node = get_node(syllabus, node_id)
    if not node:
        return syllabus, "Node not found."
    if score < passing_score:
        return syllabus, f"Score {score:.0f}% below passing {passing_score:.0f}%."
    tier = int(node.get("mastery_tier", 0))
    if tier >= MASTERY_TIER_MAX:
        return syllabus, "Already at maximum mastery tier."
    node["mastery_tier"] = tier + 1
    return syllabus, f"Mastery advanced to tier {tier + 1} for '{node.get('title')}'."
