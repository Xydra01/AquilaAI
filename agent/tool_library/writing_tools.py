import os
import json
import inspect
from pathlib import Path

DRAFT_DIR = Path("Agent-Drafts")
DRAFT_DIR.mkdir(exist_ok=True)

ACTIVE_DRAFT_FILE = DRAFT_DIR / "active_draft_state.json"

def init_document(title: str, synopsis: str) -> str:
    """Initializes a new living document buffer. ALWAYS use this first when starting a writing task."""
    draft_state = {
        "title": title,
        "synopsis": synopsis,
        "sections": [],
        "word_count": 0
    }
    with open(ACTIVE_DRAFT_FILE, "w", encoding="utf-8") as f:
        json.dump(draft_state, f, indent=4)
    return f"✅ Document '{title}' initialized. You may now begin writing sections."

def write_section(section_header: str, content: str) -> str:
    """Appends a new chunk/section of text to the active document."""
    if not ACTIVE_DRAFT_FILE.exists():
        return "❌ Error: No active document found. Use init_document first."
        
    with open(ACTIVE_DRAFT_FILE, "r", encoding="utf-8") as f:
        draft_state = json.load(f)
        
    draft_state["sections"].append({
        "header": section_header,
        "content": content
    })
    
    # Update word count
    words = len(content.split())
    draft_state["word_count"] += words
    
    with open(ACTIVE_DRAFT_FILE, "w", encoding="utf-8") as f:
        json.dump(draft_state, f, indent=4)
        
    return f"✅ Section '{section_header}' added ({words} words). Total document length: {draft_state['word_count']} words."

def read_outline() -> str:
    """Reads the current document outline (headers only) so you know what you have written so far."""
    if not ACTIVE_DRAFT_FILE.exists():
        return "❌ Error: No active document found."
        
    with open(ACTIVE_DRAFT_FILE, "r", encoding="utf-8") as f:
        draft_state = json.load(f)
        
    if not draft_state["sections"]:
        return f"Document '{draft_state['title']}' is currently empty."
        
    outline = f"OUTLINE FOR: {draft_state['title']}\n"
    for i, sec in enumerate(draft_state["sections"]):
        outline += f"{i+1}. {sec['header']}\n"
        
    return outline

def compile_final_document(file_name: str) -> str:
    """Compiles all written sections into a final Markdown file and saves it to the disk."""
    if not ACTIVE_DRAFT_FILE.exists():
        return "❌ Error: No active document to compile."
        
    with open(ACTIVE_DRAFT_FILE, "r", encoding="utf-8") as f:
        draft_state = json.load(f)
        
    final_text = f"# {draft_state['title']}\n\n"
    for sec in draft_state["sections"]:
        final_text += f"## {sec['header']}\n\n{sec['content']}\n\n"
        
    output_path = DRAFT_DIR / f"{file_name}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)
        
    # Clear the buffer
    ACTIVE_DRAFT_FILE.unlink()
    
    return f"✅ SUCCESS: Final document compiled and saved to {output_path}"

WRITING_TOOLS = {
    "init_document": {"func": init_document, "description": inspect.getdoc(init_document)},
    "write_section": {"func": write_section, "description": inspect.getdoc(write_section)},
    "read_outline": {"func": read_outline, "description": inspect.getdoc(read_outline)},
    "compile_final_document": {"func": compile_final_document, "description": inspect.getdoc(compile_final_document)},
}