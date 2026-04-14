#Tools that help Aquila function and complete tasks

from pathlib import Path
import os
import inspect
from memory import LongTermMemory
from rich.console import Console

ltm = LongTermMemory()

def update_task_ledger(status_update: str, check_off_step: str = None) -> str:
    """A dedicated tool for the agent to easily update its task ledger without exact string matching."""
    # Find the newest .md file in Agent-Tasks
    tasks_dir = Path("Agent-Tasks")
    if not tasks_dir.exists(): return "❌ No active tasks found."
    
    md_files = list(tasks_dir.glob("*.md"))
    if not md_files: return "❌ No active tasks found."
    
    # Assuming the most recently modified file is the active one
    active_file = max(md_files, key=os.path.getmtime)
    
    with open(active_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    updated = False
    for i, line in enumerate(lines):
        # Update the status line
        if line.startswith("## 📍 Current Status"):
            if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                lines[i+1] = f"{status_update}\n"
            else:
                lines.insert(i+1, f"{status_update}\n")
                
        # Check off the step if requested
        if check_off_step and check_off_step.lower() in line.lower() and "- [ ]" in line:
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            updated = True
            
    with open(active_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
    msg = f"✅ Updated Current Status in {active_file.name}."
    if check_off_step:
        msg += f" Marked step containing '{check_off_step}' as complete." if updated else f" ⚠️ Could not find unchecked step containing '{check_off_step}'."
    return msg


def set_current_status(status_message: str) -> str:
    """Updates the 'Current Status' section of the active task ledger."""
    tasks_dir = Path("Agent-Tasks")
    md_files = list(tasks_dir.glob("*.md"))
    if not md_files: return "❌ No active task ledger found."
    active_file = max(md_files, key=os.path.getmtime)
    
    with open(active_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if line.startswith("## 📍 Current Status"):
            # Replace the line immediately after the header
            if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                lines[i+1] = f"{status_message}\n\n"
            else:
                lines.insert(i+1, f"{status_message}\n\n")
            
            with open(active_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return f"✅ Status updated to: {status_message}"
            
    return "❌ Error: Could not find '## 📍 Current Status' header in ledger."

def mark_step_complete(step_keyword: str) -> str:
    """Checks off a step in the To-Do list based on a keyword match."""
    tasks_dir = Path("Agent-Tasks")
    md_files = list(tasks_dir.glob("*.md"))
    if not md_files: return "❌ No active task ledger found."
    active_file = max(md_files, key=os.path.getmtime)
    
    with open(active_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if "- [ ]" in line and step_keyword.lower() in line.lower():
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            with open(active_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            return f"✅ Marked step complete: {lines[i]}"
            
    return f"❌ Error: Could not find an unchecked step containing '{step_keyword}'."

def query_past_experience(keyword: str) -> str:
    """Searches SQLite memory for past solved tasks."""
    return ltm.search_experiences(keyword)

def ask_user(question: str) -> str:
    """
    Pauses your autonomous loop to ask the user a direct, clarifying question. 
    Use this if you are genuinely stuck, need a decision made, or need a specific file path.
    """
    from rich.console import Console
    console = Console()
    
    console.print(f"\n[bold green]🙋 Aquila has a question for you:[/bold green]")
    console.print(f"{question}")
    
    # Physically pause the python script and wait for human input
    answer = input("\nYour response: ")
    
    return f"The user responded with: {answer}"

def append_to_ledger(new_text: str) -> str:
    """
    Appends new text, notes, or '- [ ]' steps to the bottom of your Task Ledger.
    Use this when you need to add new tasks to your plan without overwriting the file.
    """
    tasks_dir = Path("Agent-Tasks")
    if not tasks_dir.exists(): return "❌ No active tasks found."
    
    md_files = list(tasks_dir.glob("*.md"))
    if not md_files: return "❌ No active task ledger found."
    
    active_file = max(md_files, key=os.path.getmtime)
    
    with open(active_file, 'a', encoding='utf-8') as f:
        f.write(f"\n{new_text}\n")
        
    return f"✅ Successfully appended new steps/notes to your task ledger."

AGENT_TOOLS = {
    "update_task_ledger": {"func": update_task_ledger, "description": inspect.getdoc(update_task_ledger)},
    "set_current_status": {"func": set_current_status, "description": inspect.getdoc(set_current_status)},
    "mark_step_complete": {"func": mark_step_complete, "description": inspect.getdoc(mark_step_complete)},
    "query_past_experience": {"func": query_past_experience, "description": inspect.getdoc(query_past_experience)},
    "ask_user": {"func": ask_user, "description": inspect.getdoc(ask_user)},
    "append_to_ledger": {"func": append_to_ledger, "description": inspect.getdoc(append_to_ledger)},
}
