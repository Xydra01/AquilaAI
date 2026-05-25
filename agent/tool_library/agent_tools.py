# Tools that help Aquila function and complete tasks
import inspect
from rich.console import Console
from memory_singleton import get_active_memory
from context_budget import get_context_profile

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


def save_research_note(task_name: str, gathered_data: str) -> str:
    """
    CRITICAL RESEARCH TOOL: Use this to save facts, URLs, outlines, and data you find.
    Instead of trying to hold information in your head, save it to your SQLite scratchpad.
    Large payloads are split into multiple scratchpad rows (no silent truncation).
    """
    data = gathered_data or ""
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
    from explore_agent import get_explore_runtime

    rt = get_explore_runtime()
    if rt.get("client") and rt.get("executor"):
        try:
            from explore_agent import run_brief

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


def summarize_sources(task_name: str, max_chars: int = 2000) -> str:
    """
    Return a capped summary of scratchpad notes for synthesize steps.
    USE WHEN: research synthesize step before final_report.
    """
    from tool_result import format_tool_result

    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = 2000
    notes = get_active_memory().get_scratchpad_notes(task_name) or ""
    if len(notes) > max_chars:
        notes = notes[:max_chars] + "\n... [truncated]"
    return format_tool_result("OK", "Sources / notes summary", notes)


def checkpoint_step(task_name: str, summary: str) -> str:
    """
    Save an explicit checkpoint for the current plan step (scratchpad).
    USE WHEN: mid-step milestone before continuing tools.
    The OS also auto-checkpoints on step advance.
    """
    return save_research_note(task_name, f"[checkpoint]\n{summary or ''}")


def save_task_deliverable_tool(
    task_name: str,
    content: str,
    deliverable_type: str = "creation",
) -> str:
    """
    Write a task deliverable file under Agent-Creations or Agent-Research.
    deliverable_type: creation | research
    """
    from main import save_task_deliverable

    mode = "research" if (deliverable_type or "").strip().lower() == "research" else "task"
    path = save_task_deliverable(task_name, mode, content or "", None)
    if path:
        return f"✅ Deliverable saved: {path}"
    return "❌ Failed to save deliverable."


def read_all_research_notes(task_name: str) -> str:
    """
    Retrieves all the research notes you have saved for the current task.
    Use this right before you write your final report so you have all your gathered facts.
    """
    return get_active_memory().get_scratchpad_notes(task_name)

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