# Tools that help Aquila function and complete tasks
import inspect
from rich.console import Console
from memory_singleton import aquila_memory

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
    CRITICAL RESEARCH TOOL: Use this to save facts, URLs, outlines, and data you find.
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
    "read_all_research_notes": {"func": read_all_research_notes, "description": inspect.getdoc(read_all_research_notes)}
}