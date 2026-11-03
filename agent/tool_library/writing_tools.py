import os
import json
import inspect
import re
from pathlib import Path

from agent.storage import agent_data_path

DRAFT_DIR = agent_data_path("Agent-Drafts")
DRAFT_DIR.mkdir(parents=True, exist_ok=True)

ACTIVE_DRAFT_FILE = DRAFT_DIR / "active_draft_state.json"

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_LEADING_NUM_RE = re.compile(r"^\d+[\.\)]\s+")


def normalize_section_header(header: str) -> str:
    """Plain section title — strip markdown # and trailing punctuation."""
    text = (header or "").strip()
    text = _HEADING_RE.sub("", text).strip()
    text = text.strip("#").strip()
    return text or "Untitled Section"


def _heading_core(text: str) -> str:
    """Comparable core of a heading (ignore #, numbering, case, punctuation)."""
    text = _HEADING_RE.sub("", (text or "").strip()).strip()
    text = _LEADING_NUM_RE.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().lower()


def strip_redundant_leading_heading(content: str, section_header: str) -> str:
    """
    Remove a leading markdown heading that duplicates the section header.

    Compile emits `## {header}` itself, so bodies must not repeat the title as # / ##.
    """
    text = (content or "").lstrip("\n")
    if not text:
        return text
    lines = text.splitlines()
    if not lines:
        return text
    first = lines[0].strip()
    if not _HEADING_RE.match(first):
        return text
    header_core = _heading_core(section_header)
    first_core = _heading_core(first)
    if not header_core or not first_core:
        return text
    # Exact or containment match (e.g. "1. Intro" vs "# Intro")
    if (
        header_core == first_core
        or header_core in first_core
        or first_core in header_core
    ):
        rest = "\n".join(lines[1:]).lstrip("\n")
        return rest
    return text


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
    """Appends a new chunk/section of text to the active document.
    
    Args:
        section_header: Plain section title only (e.g. '1. Executive Summary'). No markdown #.
        content: Markdown body only. Do NOT repeat the section title as a leading # / ## heading.
    """
    state_file = ACTIVE_DRAFT_FILE
    if not state_file.exists():
        return "❌ Error: No active document found. Use init_document first."

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state_data = json.load(f)

        header = normalize_section_header(section_header)
        body = strip_redundant_leading_heading(content, header)
            
        sections = state_data.get("sections", [])
        
        # Check if the section already exists (Upsert Logic)
        section_exists = False
        for i, sec in enumerate(sections):
            existing = normalize_section_header(sec.get("header", ""))
            if existing == header:
                sections[i]["header"] = header
                sections[i]["content"] = body
                section_exists = True
                break
                
        if not section_exists:
            sections.append({
                "header": header,
                "content": body,
            })
            
        state_data["sections"] = sections
        
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=4)
            
        word_count = len(body.split())
        total_words = sum(len(str(s.get("content", "")).split()) for s in sections)
        
        if section_exists:
            return f"✅ Section '{header}' successfully OVERWRITTEN ({word_count} words). Total document length: {total_words} words."
        else:
            return f"✅ Section '{header}' added ({word_count} words). Total document length: {total_words} words."
            
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
        save_path = DRAFT_DIR / f"{clean_file_name}.md"
        
        # Compile the markdown — one H1 for the doc, one H2 per section; never duplicate titles.
        title = (state_data.get("title") or "Untitled Document").strip()
        markdown_content = f"# {title}\n\n"
        for sec in state_data.get("sections", []):
            header = normalize_section_header(str(sec.get("header", "")))
            body = strip_redundant_leading_heading(str(sec.get("content", "")), header)
            markdown_content += f"## {header}\n\n"
            if body.strip():
                markdown_content += f"{body.rstrip()}\n\n"
            
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
