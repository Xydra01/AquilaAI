from pathlib import Path
import os
import ast
import difflib
import inspect
import re
from dotenv import load_dotenv


"""Security firewall"""
FORBIDDEN_FILES = ['.env', 'state.json', '.gitignore']
FORBIDDEN_EXTS = ['.pem', '.key']

"""env and root path loading"""
AGENT_ROOT_DIR = Path.cwd().resolve()
AGENT_CORE_DIR = Path(__file__).parent.resolve()

root_env = Path(__file__).parent.parent / ".env"
agent_env = Path(__file__).parent / ".env"

if root_env.exists():
    load_dotenv(dotenv_path=root_env)
elif agent_env.exists():
    load_dotenv(dotenv_path=agent_env)


# ==========================================
# TOOL DEFINITIONS
# ==========================================

def is_safe_path(path_obj: Path) -> bool:
    """Checks if a file is safe for the LLM to read."""
    if path_obj.name in FORBIDDEN_FILES:
        return False
    if path_obj.suffix in FORBIDDEN_EXTS:
        return False
    return True

def check_syntax(code_string: str):
    """Checks Python code for syntax errors without executing it."""
    try:
        ast.parse(code_string)
        return True, None
    except SyntaxError as e:
        return False, f"SyntaxError on line {e.lineno}: {e.msg}\nCode snippet:\n{e.text}"    
    
def write_file(file_path: str, content: str) -> str:
    """Creates a new file or completely overwrites an existing one."""
    
    # 1. Clean up LLM Markdown artifacts (strip ```python ... ```)
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n", "", content)
        if content.endswith("```"):
            content = content[:-3].strip()
            
    target_path = Path(file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 2. Python AST Auto-Healer for Token Cut-offs
    if target_path.suffix == '.py':
        try:
            ast.parse(content)
        except SyntaxError as e:
            err_msg = str(e).lower()
            original_content = content
            healed = False
            
            # Heal A: Unterminated Strings / Docstrings
            if "unterminated" in err_msg and "string" in err_msg:
                for quote in ['"""', "'''"]:
                    try:
                        ast.parse(original_content + f"\n{quote}\n")
                        content = original_content + f"\n{quote}\n"
                        healed = True
                        break
                    except SyntaxError:
                        pass
            
            # Heal B: Missing Parentheses or Brackets
            elif "eof" in err_msg or "never closed" in err_msg:
                for char in [')', ']', '}', '\n"""\n', "\n'''\n"]:
                    try:
                        ast.parse(original_content + f"\n{char}")
                        content = original_content + f"\n{char}"
                        healed = True
                        break
                    except SyntaxError:
                        pass
                        
            # Heal C: Missing Indentations (e.g. cut off right after a 'try:' or 'def:')
            elif "expected an indented block" in err_msg:
                try:
                    ast.parse(original_content + "\n    pass\n")
                    content = original_content + "\n    pass\n"
                    healed = True
                except SyntaxError:
                    pass
            
            if not healed:
                return f"❌ Error: File NOT saved. Unrecoverable syntax error: {str(e)}"
            else:
                print(f"🔧 [bold green]Python Auto-Healed a syntax cut-off in {target_path.name}[/bold green]")

    # 3. Write the clean, healed file
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    return f"✅ Successfully created/overwrote {file_path}."

def read_file(file_path: str) -> str:
    """Reads the contents of a file, capping it for context safety."""
    path_obj = Path(file_path).expanduser()
    
    # --- SECURITY FIREWALL ---
    if not is_safe_path(path_obj):
        return f"❌ SECURITY BLOCK: Access to '{path_obj.name}' is strictly forbidden by the system admin."
        
    if os.path.isdir(file_path):
        return f"❌ Error: '{file_path}' is a directory, not a file."
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if len(content) > 1500:
            preview = content[:1500]
            return (f"{preview}\n\n"
                    f"... [FILE TRUNCATED DUE TO LENGTH ({len(content)} chars)]\n"
                    f"⚠️ WARNING: File is too large. Use `search_tool_library` to find tools like `search_in_file` or `read_file_lines` to read the rest safely.")
        return content
    except FileNotFoundError:
        return f"❌ Error: File {file_path} not found."
    except Exception as e:
        return f"❌ Error reading file: {e}"
    

def list_directory(path="."):
    """Lists all files and folders in a specific directory."""
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return f"Error: Directory '{target}' does not exist."
        items = []
        for item in target.iterdir():
            if item.is_dir():
                items.append(f"[DIR]  {item.name}/")
            else:
                items.append(f"[FILE] {item.name} ({item.stat().st_size} bytes)")
        return f"Contents of {target}:\n" + "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {e}"


def replace_in_file(file_path: str, target_text: str, replacement_text: str) -> str:
    """Replaces exact target text with replacement text in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if target_text not in content:
            lines = content.split('\n')
            target_lines = target_text.split('\n')
            hint = ""
            if len(target_lines) > 0:
                matches = difflib.get_close_matches(target_lines[0], lines, n=3, cutoff=0.6)
                if matches:
                    hint = f"\nHint: The exact text was not found. Closest matches for the first line:\n" + "\n".join(matches)
            return f"❌ Error: The exact target text was not found. {hint}"
        
        new_content = content.replace(target_text, replacement_text)
        if file_path.endswith('.py'):
            is_valid, err_msg = check_syntax(new_content)
            if not is_valid:
                return f"❌ Error: Replacement NOT applied. It causes a syntax error:\n{err_msg}"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return f"✅ Successfully replaced text in {file_path}."
    except FileNotFoundError:
        return f"❌ Error: File {file_path} not found."
   

def search_tool_library(keyword: str) -> str:
    """
    Search the agent's massive offline tool library for a specific capability.
    """
    # Clean up the LLM's input and split it into individual words
    # e.g., "web_search or internet" -> ["web_search", "or", "internet"]
    search_terms = [term.strip().lower() for term in keyword.replace(',', ' ').split() if len(term) > 2]
    
    found_tools = []
    
    for name, info in ALL_TOOLS.items():
        # Combine name and description into one searchable block
        tool_text = (name + " " + info['description']).lower()
        
        # If ANY of the search terms are in the tool's text, it's a match!
        if any(term in tool_text for term in search_terms):
            sig = inspect.signature(info['func'])
            template = f"### 🛠️ ACTION: {name}"
            
            for param in sig.parameters:
                if param == 'kwargs': continue
                template += f"\n**{param}**: ..."
                
            found_tools.append(f"TOOL: {name}\nDESC: {info['description']}\nFORMAT:\n{template}")
            
    if not found_tools:
        return f"❌ No tools found matching '{keyword}'. Try a different search term."
        
    return "✅ FOUND TOOLS:\n\n" + "\n\n".join(found_tools) + "\n\nTo use a tool, simply output its exact ACTION format in your next response."

def finish_task(message_to_user: str) -> str:
    """
    CRITICAL: Use this tool ONLY when all steps are complete. 
    Use the 'message_to_user' argument to converse directly with the user, provide short answers, or summarize your findings.
    """
    return f"TASK_COMPLETED_SUCCESSFULLY: {message_to_user}"


# SURVIVAL TOOL REGISTRY
from tool_library import ALL_TOOLS


SURVIVAL_TOOLS = {
    "read_file": {"func": read_file, "description": inspect.getdoc(read_file)},
    "write_file": {"func": write_file, "description": inspect.getdoc(write_file)},
    "replace_in_file": {"func": replace_in_file, "description": inspect.getdoc(replace_in_file)},
    "list_directory": {"func": list_directory, "description": inspect.getdoc(list_directory)},
    "finish_task": {"func": finish_task, "description": inspect.getdoc(finish_task)},
    "search_tool_library": {"func": search_tool_library, "description": inspect.getdoc(search_tool_library)}
}