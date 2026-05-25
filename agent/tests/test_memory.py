import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory import DualMemorySystem

@pytest.fixture
def safe_memory(tmp_path):
    """
    Creates a sandboxed DualMemorySystem that writes to a temporary folder
    instead of overwriting Aquila's real SQLite and ChromaDB databases.
    """
    db_dir = tmp_path / "Agent-Memory"
    db_dir.mkdir()
    chroma_dir = tmp_path / "vector_db"
    mem = DualMemorySystem(storage_dir=str(db_dir), chroma_path=chroma_dir)
    yield mem

def test_empty_episodic_memory(safe_memory):
    """TDD Goal: Ensure safe fallbacks when the database is completely empty."""
    results = safe_memory.recall_experiences("How do I build a calculator?")
    assert "No past experiences" in results or "No relevant past experiences" in results

def test_chroma_episodic_memory(safe_memory):
    """TDD Goal: Verify semantic search successfully embeds and recalls past tasks."""
    
    safe_memory.store_experience("Build_Calculator", "Created a python calculator with add and subtract functions.")
    safe_memory.store_experience("Write_Essay", "Drafted a historical essay about the Roman Empire.")
    
    results = safe_memory.recall_experiences("math operations", n_results=1)
    
    assert "calculator" in results.lower()
    assert "rome" not in results.lower()

def test_tool_indexing(safe_memory):
    """TDD Goal: Verify that the tool roster successfully embeds into its own collection."""
    mock_tools = {
        "fake_scraper": {"description": "Scrapes a webpage for text."},
        "fake_writer": {"description": "Writes text to a file."}
    }
    
    safe_memory.index_tools(mock_tools)
    
    assert safe_memory.tool_collection.count() == 2