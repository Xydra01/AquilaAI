# Tools that help Aquila function and complete tasks
import inspect
from rich.console import Console
from agent.storage import get_active_memory
from agent.policies import get_context_profile

# --- NEW: QT THREADING BRIDGE ---
USER_INPUT_CALLBACK = None

def ask_user(question: str) -> str:
    """
    Interrupts the autonomous loop to ask the human user a question.
    Use this when you are stuck, need clarification, or require a strategic decision to proceed.
    """
    console = Console()
    console.print(f"\n[bold yellow]⚠️ Agent is asking the user: {question}[/bold yellow]")
    
    if USER_INPUT_CALLBACK:
        return USER_INPUT_CALLBACK(question)
        
    return "❌ SYSTEM ERROR: User input callback not connected. You must proceed autonomously."

def query_past_experience(keyword: str) -> str:
    """Searches the ChromaDB vector database for past solved tasks."""
    return get_active_memory().recall_experiences(keyword)

def store_fact(topic: str, fact: str) -> str:
    """
    CRITICAL: Use this tool to permanently remember user preferences, lore corrections, or absolute rules.
    Args:
        topic: A 1-2 word category (e.g., 'lore', 'coding_style', 'formatting').
        fact: The specific rule to remember.
    """
    return get_active_memory().store_fact(topic, fact)

MAX_SCRATCHPAD_NOTE_BYTES = 8 * 1024


def _scratchpad_byte_limit() -> int:
    return max(MAX_SCRATCHPAD_NOTE_BYTES, get_context_profile().scratchpad_bytes)


def _utf8_byte_chunks(text: str, max_bytes: int) -> list[str]:
    """Split text into UTF-8-safe pieces each at most max_bytes."""
    if max_bytes <= 0:
        return [text or ""]
    encoded = (text or "").encode("utf-8")
    if len(encoded) <= max_bytes:
        return [text or ""]
    chunks: list[str] = []
    pos = 0
    total = len(encoded)
    while pos < total:
        end = min(pos + max_bytes, total)
        piece = encoded[pos:end]
        while piece:
            try:
                chunks.append(piece.decode("utf-8"))
                pos += len(piece)
                break
            except UnicodeDecodeError:
                piece = piece[:-1]
        else:
            break
    return chunks

def _note_similarity(new_text: str, existing_text: str) -> float:
    """Jaccard similarity on word sets. Fast, no dependencies."""
    import re
    new_words = set(re.findall(r'\b\w+\b', new_text.lower()))
    existing_words = set(re.findall(r'\b\w+\b', existing_text.lower()))
    if not new_words or not existing_words:
        return 0.0
    intersection = new_words & existing_words
    union = new_words | existing_words
    return len(intersection) / len(union) if union else 0.0


def save_research_note(gathered_data: str, task_name: str | None = None) -> str:
    """
    CRITICAL RESEARCH TOOL: Use this to save facts, URLs, outlines, and data you find.
    Instead of trying to hold information in your head, save it to your SQLite scratchpad.
    Large payloads are split into multiple scratchpad rows (no silent truncation).

    The OS binds notes to the active task id — do not pass task_name in JSON.
    """
    from agent.core import resolve_task_id

    task_name = resolve_task_id(task_name)
    data = gathered_data or ""
    
    # --- NEW: Deduplication check ---
    existing_notes = get_active_memory().get_scratchpad_notes(task_name) or ""
    if existing_notes.strip() and data.strip():
        similarity = _note_similarity(data, existing_notes)
        if similarity > 0.85:
            return (
                "❌ OS BLOCK: This note is ≥85% similar to existing scratchpad content. "
                "Add NEW facts not already saved, or use a different tool. "
                f"(similarity: {similarity:.0%})"
            )
    # --- END NEW ---
    
    limit = _scratchpad_byte_limit()
    chunks = _utf8_byte_chunks(data, limit)
    memory = get_active_memory()
    if len(chunks) <= 1:
        return memory.save_scratchpad_note(task_name, chunks[0] if chunks else "")

    total_bytes = len(data.encode("utf-8"))
    saved = 0
    last_result = ""
    for index, chunk in enumerate(chunks, start=1):
        header = f"[scratchpad chunk {index}/{len(chunks)}]\n"
        payload = header + chunk
        if len(payload.encode("utf-8")) > limit:
            payload = chunk
        last_result = memory.save_scratchpad_note(task_name, payload)
        saved += 1
    return (
        f"✅ Saved {saved} scratchpad chunks for task: {task_name} "
        f"({total_bytes} bytes total; {limit} bytes max per chunk). "
        "Use read_all_research_notes to read them in order."
    )

def subagent_explore(user_request: str, mode: str = "code") -> str:
    """
    Request OS exploration brief (when runtime is wired) or fall back to recon tools.
    USE WHEN: first episode of explore step; otherwise use get_directory_tree + read_code_outline.
    """
    from agent.core import get_explore_runtime

    rt = get_explore_runtime()
    if rt.get("client") and rt.get("executor"):
        try:
            from agent.core import run_brief

            brief = run_brief(
                client=rt["client"],
                executor=rt["executor"],
                user_request=user_request or rt.get("user_request", ""),
                mode=mode or "code",
                instance_id=rt.get("instance_id", "default"),
                memory=rt.get("memory") or get_active_memory(),
                console=rt.get("console") or Console(),
            )
            return brief.to_markdown()
        except Exception as e:
            return f"❌ subagent_explore failed: {e}"
    return (
        "OS: Run get_directory_tree(path='.', max_depth=2) then read_code_outline() "
        "for exploration."
    )


def summarize_sources(max_chars: int = 2000, task_name: str | None = None) -> str:
    """
    Return a capped summary of scratchpad notes for synthesize steps.
    USE WHEN: research synthesize step before final_report.

    The OS binds reads to the active task id — do not pass task_name in JSON.
    """
    from agent.core import resolve_task_id
    from agent.core import format_tool_result

    task_name = resolve_task_id(task_name)
    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = 2000
    notes = get_active_memory().get_scratchpad_notes(task_name) or ""
    if len(notes) > max_chars:
        notes = notes[:max_chars] + "\n... [truncated]"
    return format_tool_result("OK", "Sources / notes summary", notes)


def checkpoint_step(summary: str, task_name: str | None = None) -> str:
    """
    Save an explicit checkpoint for the current plan step (scratchpad).
    USE WHEN: mid-step milestone before continuing tools.
    The OS also auto-checkpoints on step advance.
    """
    return save_research_note(f"[checkpoint]\n{summary or ''}", task_name=task_name)


def save_task_deliverable_tool(
    content: str,
    deliverable_type: str = "creation",
    task_name: str | None = None,
) -> str:
    """
    Write a task deliverable file under Agent-Creations or Agent-Research.
    deliverable_type: creation | research

    The OS binds the file to the active task id — do not pass task_name in JSON.
    """
    from agent.core import save_task_deliverable
    from agent.core import resolve_task_id

    task_name = resolve_task_id(task_name)
    mode = "research" if (deliverable_type or "").strip().lower() == "research" else "task"
    path = save_task_deliverable(task_name, mode, content or "", None)
    if path:
        return f"✅ Deliverable saved: {path}"
    return "❌ Failed to save deliverable."


def read_all_research_notes(
    max_chars: int | None = None,
    tail: bool = True,
    task_name: str | None = None,
) -> str:
    """
    Retrieve research notes from the scratchpad for the current task.

    Guardrail: by default this returns a capped view to prevent prompt blowups on 32k.
    Use max_chars to explicitly request a larger window when needed.

    The OS binds reads to the active task id — do not pass task_name in JSON.
    """
    from agent.policies import get_context_profile
    from agent.core import resolve_task_id

    task_name = resolve_task_id(task_name)
    notes = get_active_memory().get_scratchpad_notes(task_name) or ""
    if not notes.strip() or "No research notes found" in notes:
        return notes

    profile = get_context_profile()
    default_cap = max(4000, int(profile.scratchpad_bytes * 2))
    cap = default_cap
    if max_chars is not None:
        try:
            cap = int(max_chars)
        except (TypeError, ValueError):
            cap = default_cap
    cap = max(1000, cap)

    if len(notes) <= cap:
        return notes

    slice_text = notes[-cap:] if tail else notes[:cap]
    marker = (
        f"\n... [truncated to {cap} chars; call read_all_research_notes(max_chars=...) "
        "for more]"
    )
    return slice_text + marker

AGENT_TOOLS = {
    "query_past_experience": {"func": query_past_experience, "description": inspect.getdoc(query_past_experience)},
    "ask_user": {"func": ask_user, "description": inspect.getdoc(ask_user)},
    "store_fact": {"func": store_fact, "description": inspect.getdoc(store_fact)},
    "save_research_note": {"func": save_research_note, "description": inspect.getdoc(save_research_note)},
    "read_all_research_notes": {"func": read_all_research_notes, "description": inspect.getdoc(read_all_research_notes)},
    "subagent_explore": {"func": subagent_explore, "description": inspect.getdoc(subagent_explore)},
    "summarize_sources": {"func": summarize_sources, "description": inspect.getdoc(summarize_sources)},
    "checkpoint_step": {"func": checkpoint_step, "description": inspect.getdoc(checkpoint_step)},
    "save_task_deliverable": {
        "func": save_task_deliverable_tool,
        "description": inspect.getdoc(save_task_deliverable_tool),
    },
}
