import os
import json
import inspect
from pathlib import Path

from workspace_paths import agent_data_path

DRAFT_DIR = agent_data_path("Agent-Drafts")
DRAFT_DIR.mkdir(parents=True, exist_ok=True)

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
    state_file = ACTIVE_DRAFT_FILE
    if not state_file.exists():
        return "❌ Error: No active document found. Use init_document first."

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state_data = json.load(f)
            
        sections = state_data.get("sections", [])
        
        # Check if the section already exists (Upsert Logic)
        section_exists = False
        for i, sec in enumerate(sections):
            if sec.get("header", "").strip() == section_header.strip():
                sections[i]["content"] = content
                section_exists = True
                break
                
        if not section_exists:
            sections.append({
                "header": section_header,
                "content": content
            })
            
        state_data["sections"] = sections
        
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=4)
            
        word_count = len(content.split())
        total_words = sum(len(s.get("content", "").split()) for s in sections)
        
        if section_exists:
            return f"✅ Section '{section_header}' successfully OVERWRITTEN ({word_count} words). Total document length: {total_words} words."
        else:
            return f"✅ Section '{section_header}' added ({word_count} words). Total document length: {total_words} words."
            
    except Exception as e:
        return f"❌ Error writing to draft state: {str(e)}"

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
    state_file = ACTIVE_DRAFT_FILE
    if not state_file.exists():
        return "❌ Error: No active document to compile. Use init_document first."

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state_data = json.load(f)
            
        # Strip redundant .md extensions if she provided them
        clean_file_name = file_name.replace(".md", "")
        
        # Ensure it saves to the correct directory
        save_path = Path("Agent-Drafts") / f"{clean_file_name}.md"
        
        # Compile the markdown
        markdown_content = f"# {state_data.get('title', 'Untitled Document')}\n\n"
        for sec in state_data.get("sections", []):
            markdown_content += f"## {sec.get('header', '')}\n\n{sec.get('content', '')}\n\n"
            
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        # Clear the buffer
        ACTIVE_DRAFT_FILE.unlink()
    
        return f"✅ SUCCESS: Final document compiled and saved to {save_path}"
    except Exception as e:
        return f"❌ Error compiling document: {str(e)}"

WRITING_TOOLS = {
    "init_document": {"func": init_document, "description": inspect.getdoc(init_document)},
    "write_section": {"func": write_section, "description": inspect.getdoc(write_section)},
    "read_outline": {"func": read_outline, "description": inspect.getdoc(read_outline)},
    "compile_final_document": {"func": compile_final_document, "description": inspect.getdoc(compile_final_document)},
}