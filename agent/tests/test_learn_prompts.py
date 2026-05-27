"""Learn Mode prompt constraints."""
from prompts import (
    build_learn_archive_user_message,
    get_learn_tutor_prompt,
    get_learn_archive_prompt,
    get_syllabus_build_prompt,
)


def test_tutor_prompt_socratic_rules():
    p = get_learn_tutor_prompt("syllabus excerpt", "Unit 1", "u1", 2, "chunk text")
    lower = p.lower()
    assert "socratic" in lower
    assert "do not" in lower and "direct answer" in lower
    assert "tier 2" in lower or "tier 2 / 5" in p
    assert "no tool json" in lower


def test_archive_prompt_direct_answer():
    p = get_learn_archive_prompt("History")
    assert "History" in p
    assert "json" in p.lower()
    assert "think" in p.lower() or "reasoning" in p.lower()


def test_archive_user_message_includes_sources():
    body = build_learn_archive_user_message("What is holoscopy?", "[1] (a.pdf)\nFact.")
    assert "holoscopy" in body
    assert "ARCHIVE SOURCES" in body
    assert "/no_think" in body


def test_syllabus_build_prompt_requires_write_syllabus():
    p = get_syllabus_build_prompt("- write_syllabus_file")
    assert "write_syllabus_file" in p
    assert "finalize_course" in p
