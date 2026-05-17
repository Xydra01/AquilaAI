import pytest
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tool_library import writing_tools

@pytest.fixture
def draft_workspace(tmp_path, monkeypatch):
    """
    Creates a sandboxed workspace for the Write Mode tools.
    Patches the internal DRAFT_DIR and ACTIVE_DRAFT_FILE paths.
    """
    draft_dir = tmp_path / "Agent-Drafts"
    draft_dir.mkdir()
    active_draft = draft_dir / "active_draft_state.json"
    
    monkeypatch.chdir(tmp_path)
    
    monkeypatch.setattr(writing_tools, "DRAFT_DIR", draft_dir)
    monkeypatch.setattr(writing_tools, "ACTIVE_DRAFT_FILE", active_draft)
    
    yield tmp_path

def test_init_document(draft_workspace):
    """TDD Goal: Ensure initializing a document creates a clean JSON buffer."""
    result = writing_tools.init_document("Test Book", "A book about testing.")
    
    assert "✅ Document 'Test Book' initialized" in result
    assert writing_tools.ACTIVE_DRAFT_FILE.exists()
    
    data = json.loads(writing_tools.ACTIVE_DRAFT_FILE.read_text(encoding="utf-8"))
    assert data["title"] == "Test Book"
    assert data["synopsis"] == "A book about testing."
    assert len(data["sections"]) == 0

def test_write_section_no_init(draft_workspace):
    """TDD Goal: Ensure the OS blocks writing if the document wasn't initialized."""
    result = writing_tools.write_section("Chapter 1", "Content here.")
    assert "❌ Error: No active document found" in result

def test_write_section_append(draft_workspace):
    """TDD Goal: Ensure sections are properly appended to the JSON array."""
    writing_tools.init_document("Test Book", "Synopsis")
    
    writing_tools.write_section("Chapter 1", "This is the first chapter.")
    writing_tools.write_section("Chapter 2", "This is the second chapter.")
    
    data = json.loads(writing_tools.ACTIVE_DRAFT_FILE.read_text(encoding="utf-8"))
    
    assert len(data["sections"]) == 2
    assert data["sections"][0]["header"] == "Chapter 1"
    assert data["sections"][1]["content"] == "This is the second chapter."

def test_compile_final_document(draft_workspace):
    """TDD Goal: Ensure the OS successfully compiles the JSON array into a single Markdown file."""
    writing_tools.init_document("My Great Book", "A book about things.")
    writing_tools.write_section("Chapter 1", "Once upon a time.")
    writing_tools.write_section("Chapter 2", "The End.")
    
    result = writing_tools.compile_final_document("final_story")
    
    assert "✅ SUCCESS" in result
    
    md_file = draft_workspace / "Agent-Drafts" / "final_story.md"
    assert md_file.exists()
    
    content = md_file.read_text(encoding="utf-8")
    assert "# My Great Book" in content
    assert "## Chapter 1\n\nOnce upon a time." in content
    assert "## Chapter 2\n\nThe End." in content
    
    assert not writing_tools.ACTIVE_DRAFT_FILE.exists()

def test_compile_no_init(draft_workspace):
    """TDD Goal: Ensure compiling fails safely if there is no active document."""
    result = writing_tools.compile_final_document("empty_doc")
    assert "❌ Error: No active document to compile" in result