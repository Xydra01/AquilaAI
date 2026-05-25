"""Learn Mode registry and mastery."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from learn_registry import (
    advance_mastery_on_pass,
    create_course,
    create_archive,
    default_syllabus,
    get_node,
    is_node_unlocked,
    load_syllabus,
    save_syllabus,
)


def test_default_syllabus_has_root_node():
    s = default_syllabus("Algebra", "equations", "files")
    assert s["version"] == 1
    assert len(s["nodes"]) >= 1
    assert get_node(s, "root") is not None


def test_advance_mastery_on_pass():
    s = default_syllabus("Test", "topic", "files")
    s["nodes"][0]["id"] = "u1"
    s["nodes"][0]["mastery_tier"] = 1
    updated, msg = advance_mastery_on_pass(s, "u1", 80.0, 70.0)
    assert updated["nodes"][0]["mastery_tier"] == 2
    assert "tier 2" in msg.lower()


def test_advance_mastery_fails_below_threshold():
    s = default_syllabus("Test", "topic", "files")
    s["nodes"][0]["id"] = "u1"
    _, msg = advance_mastery_on_pass(s, "u1", 50.0, 70.0)
    assert "below" in msg.lower()


def test_node_unlocked_by_parent_tier():
    s = {
        "nodes": [
            {"id": "p", "parent_id": None, "mastery_tier": 1, "tier_gate": 2},
            {"id": "c", "parent_id": "p", "mastery_tier": 0},
        ]
    }
    assert not is_node_unlocked(s, s["nodes"][1])
    s["nodes"][0]["mastery_tier"] = 2
    assert is_node_unlocked(s, s["nodes"][1])


def test_create_course_writes_files(tmp_path):
    inst = "test_inst"
    with patch("learn_registry.instance_dir", return_value=tmp_path / inst):
        course = create_course(inst, "Physics 101", "motion", "topic_web")
        assert course.build_complete is False
        syl_path = tmp_path / inst / "learn" / "courses" / course.id / "syllabus.json"
        assert syl_path.is_file()
        data = json.loads(syl_path.read_text(encoding="utf-8"))
        assert data["intake"] == "topic_web"


def test_create_archive(tmp_path):
    inst = "test_inst"
    with patch("learn_registry.instance_dir", return_value=tmp_path / inst):
        arch = create_archive(inst, "My Notes")
        path = tmp_path / inst / "learn" / "archives" / arch.id / "archive.json"
        assert path.is_file()
