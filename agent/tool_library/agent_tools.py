#Tools that help Aquila function and complete tasks

import inspect
from memory import DualMemorySystem
from rich.console import Console

aquila_memory = DualMemorySystem()

def ask_user(question: str) -> str:
    """
    DEPRECATED IN WEB UI MODE (For now).
    """
    console = Console()
    console.print(f"\n[bold red]⚠️ Agent attempted to use ask_user to ask: {question}[/bold red]")
    
    return (
        "❌ SYSTEM ERROR: You are operating in a headless Web UI. The `ask_user` tool is strictly blocked because it freezes the server.\n"
        "If you absolutely need the user's input or a decision to proceed, you MUST use the `finish_task` tool, put your question in the `message_to_user` argument, and shut down."
    )

def query_past_experience(keyword: str) -> str:
    """Searches the ChromaDB vector database for past solved tasks."""
    return aquila_memory.recall_experiences(keyword)

def store_fact(topic: str, fact: str) -> str:
    """
    CRITICAL: Use this tool to permanently remember user preferences, lore corrections, or absolute rules.
    Args:
        topic: A 1-2 word category (e.g., 'lore', 'coding_style', 'formatting').
        fact: The specific rule to remember.
    """
    return aquila_memory.store_fact(topic, fact)

def save_research_note(task_name: str, gathered_data: str) -> str:
    """
    CRITICAL RESEARCH TOOL: Use this to save facts, URLs, and data you find on the web.
    Instead of trying to hold information in your head, save it to your SQLite scratchpad.
    """
    return aquila_memory.save_scratchpad_note(task_name, gathered_data)

def read_all_research_notes(task_name: str) -> str:
    """
    Retrieves all the research notes you have saved for the current task.
    Use this right before you write your final report so you have all your gathered facts.
    """
    return aquila_memory.get_scratchpad_notes(task_name)

AGENT_TOOLS = {
    "query_past_experience": {"func": query_past_experience, "description": inspect.getdoc(query_past_experience)},
    "ask_user": {"func": ask_user, "description": inspect.getdoc(ask_user)},
    "store_fact": {"func": store_fact, "description": inspect.getdoc(store_fact)},
    "save_research_note": {"func": save_research_note, "description": inspect.getdoc(save_research_note)},
    "read_all_research_notes": {"func": read_all_research_notes, "description": inspect.getdoc(read_all_research_notes)},
}