"""Learn Mode prompt constraints."""
from prompts import get_learn_tutor_prompt, get_learn_archive_prompt, get_syllabus_build_prompt


def test_tutor_prompt_socratic_rules():
    p = get_learn_tutor_prompt("syllabus excerpt", "Unit 1", "u1", 2, "chunk text")
    lower = p.lower()
    assert "socratic" in lower
    assert "do not" in lower and "direct answer" in lower
    assert "tier 2" in lower or "tier 2 / 5" in p
    assert "no tool json" in lower


def test_archive_prompt_grounded():
    p = get_learn_archive_prompt("History", "source block")
    assert "History" in p
    assert "source block" in p
    assert "only from" in p.lower() or "only" in p.lower()


def test_syllabus_build_prompt_requires_write_syllabus():
    p = get_syllabus_build_prompt("- write_syllabus_file")
    assert "write_syllabus_file" in p
    assert "finalize_course" in p
