import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui_state import resolve_ledger_path, render_step_ledger_html
from conftest import load_fixture_ledger


def test_resolve_autonomous_ledger():
    path = resolve_ledger_path("autonomous", "my_task_123")
    assert path == resolve_ledger_path("task", "my_task_123")
    assert str(path).replace("\\", "/").endswith("Agent-Tasks/my_task_123.json")


def test_resolve_research_ledger():
    path = resolve_ledger_path("research", "research_job")
    assert str(path).replace("\\", "/").endswith("Agent-Plans/research_job.json")


def test_resolve_writing_prefers_draft(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    draft_dir = tmp_path / "Agent-Drafts"
    draft_dir.mkdir()
    draft_file = draft_dir / "active_draft_state.json"
    draft_file.write_text('{"title": "T"}', encoding="utf-8")
    path = resolve_ledger_path("writing", "any_task")
    assert path.resolve() == draft_file.resolve()


def test_render_step_ledger_html_contains_steps():
    state = load_fixture_ledger("autonomous_in_progress.json")
    html = render_step_ledger_html(state)
    assert "Create project scaffold" in html
    assert "Implement core module" in html
    assert "IN_PROGRESS" in html.upper() or "in_progress" in html.lower()
