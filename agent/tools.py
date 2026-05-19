from pathlib import Path
import os
import ast
import difflib
import inspect
import re
from dotenv import load_dotenv

"""Security firewall"""
FORBIDDEN_FILES = ['.env', 'state.json', '.gitignore', 'chroma.sqlite3']
FORBIDDEN_EXTS = ['.pem', '.key', '.log', '.db', '.sqlite3']
FORBIDDEN_DIRS = [
    'Agent-Logs',
    'vector_db',
    '__pycache__',
    '.git',
    '.venv',
    'venv',
    'node_modules',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.tox',
    '.nox',
    'dist',
    'build',
    '.eggs',
    'htmlcov',
    'site-packages',
    'ai-agent-env',
    '.cursor',
    '.idea',
    '.vscode',
]


def should_skip_dir(dirname: str) -> bool:
    """Skip dependency/build/cache dirs when walking a codebase (not Aquila internals only)."""
    if dirname in FORBIDDEN_DIRS:
        return True
    if dirname.endswith('.egg-info'):
        return True
    return False


def is_ignored_code_path(path: str) -> bool:
    """True if a project-relative path lies under an ignored directory."""
    if not path:
        return False
    parts = Path(str(path).replace('\\', '/')).parts
    return any(should_skip_dir(p) for p in parts)

"""env and root path loading"""
AGENT_ROOT_DIR = Path.cwd().resolve()
AGENT_CORE_DIR = Path(__file__).parent.resolve()

root_env = Path(__file__).parent.parent / ".env"
agent_env = Path(__file__).parent / ".env"

if root_env.exists():
    load_dotenv(dotenv_path=root_env)
elif agent_env.exists():
    load_dotenv(dotenv_path=agent_env)

def get_code_project_root() -> Path | None:
    """Active Code Mode project directory, if any."""
    try:
        from tool_library.code_canvas_tools import get_active_project_scope

        scope = get_active_project_scope()
        if scope:
            return Path(scope["root"]).resolve()
    except Exception:
        pass
    return None


def resolve_tool_path(file_path: str, *, for_write: bool = False) -> Path:
    """
    Resolve a path for filesystem tools. When a code project is open, relative paths
    are under CODE_PROJECT_ROOT (may be outside process cwd for in-place repos).
    """
    norm = normalize_workspace_path(file_path or ".")
    p = Path(norm)
    if p.is_absolute():
        return p.resolve()
    code_root = get_code_project_root()
    if code_root:
        return (code_root / norm).resolve()
    return (Path.cwd() / norm).resolve()


def normalize_workspace_path(file_path: str) -> str:
    """Fix doubled path segments and coerce absolute paths to workspace-relative."""
    if not file_path:
        return file_path
    p = str(file_path).replace("\\", "/").strip()
    while "/agent/agent/" in p or p.startswith("agent/agent/"):
        p = p.replace("/agent/agent/", "/agent/", 1)
        if p.startswith("agent/agent/"):
            p = "agent/" + p[len("agent/agent/") :]
    try:
        path_obj = Path(p)
        if path_obj.is_absolute():
            cwd = Path.cwd().resolve()
            resolved = path_obj.resolve()
            try:
                p = resolved.relative_to(cwd).as_posix()
            except ValueError:
                p = resolved.as_posix()
    except OSError:
        pass
    return p


def is_safe_path(path_obj: Path) -> bool:
    """Checks if a file is safe for the LLM to read."""
    if path_obj.name in FORBIDDEN_FILES:
        return False
    if path_obj.suffix in FORBIDDEN_EXTS:
        return False
    if any(should_skip_dir(part) for part in path_obj.parts):
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
    code_root = get_code_project_root()
    if code_root:
        target = resolve_tool_path(file_path, for_write=True)
        try:
            target.relative_to(code_root)
        except ValueError:
            return (
                f"❌ CODE MODE: Cannot write outside the open project ({code_root}). "
                "Use create_buffer_file for source/docs, then sync_project_to_disk — "
                "or write_project_markdown for ARCHITECTURE.md / README updates."
            )
        file_path = str(target)
    else:
        file_path = normalize_workspace_path(file_path)
    if not is_safe_path(Path(file_path)):
        return f"❌ SECURITY BLOCK: Access to '{file_path}' is strictly forbidden by the system admin. Do not attempt to modify this file."
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n", "", content)
        if content.endswith("```"):
            content = content[:-3].strip()
            
    target_path = Path(file_path)
    
    if "Agent-Tasks" in target_path.parts:
        return ("❌ SECURITY BLOCK: You are not allowed to directly edit files in Agent-Tasks. "
                "The Python OS handles task states dynamically via JSON. "
                "Focus on completing your active objective and use `mark_objective_complete`.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    if target_path.suffix == '.py':
        import subprocess
        import sys
        
        try:
            ast.parse(content)
            result = subprocess.run(
                [sys.executable, "-m", "flake8", str(target_path), "--max-line-length=120"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                lint_errors = result.stdout.strip() or result.stderr.strip()
                if "No module named flake8" not in lint_errors:
                    return (f"✅ Successfully saved {file_path}.\n\n"
                            f"⚠️ LINTER WARNINGS:\n{lint_errors}\n\n"
                            f"SYSTEM HINT: Fix these logic errors using `replace_in_file` before running the script.")
        except SyntaxError as e:
            error_line = e.text.rstrip() if e.text else ""
            pointer = ""
            if e.offset and e.text:
                leading_whitespace = e.text[:e.offset - 1]
                pointer_spacing = "".join("\t" if char == "\t" else " " for char in leading_whitespace)
                pointer = f"{pointer_spacing}^"
            
            return (f"✅ File saved as {file_path}, BUT IT HAS A SYNTAX ERROR:\n\n"
                    f"Line {e.lineno}: {e.msg}\n"
                    f"```python\n{error_line}\n{pointer}\n```\n"
                    f"SYSTEM HINT: Do NOT rewrite the whole file. Use `replace_in_file` to fix this specific line.")
                    
    return f"✅ Successfully created/overwrote {file_path}."

def read_file(file_path: str) -> str:
    """Reads the contents of a file, capping it for context safety."""
    path_obj = resolve_tool_path(file_path)
    file_path = str(path_obj)
    
    if not is_safe_path(path_obj):
        return f"❌ SECURITY BLOCK: Access to '{path_obj.name}' is strictly forbidden by the system admin. Do not attempt to read this file again."
        
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
        target = resolve_tool_path(path or ".")
        if not target.exists():
            return f"Error: Directory '{target}' does not exist."
        items = []
        for item in target.iterdir():
            if should_skip_dir(item.name):
                continue
            if item.is_dir():
                items.append(f"[DIR]  {item.name}/")
            else:
                items.append(f"[FILE] {item.name} ({item.stat().st_size} bytes)")
        return f"Contents of {target}:\n" + "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {e}"

def replace_in_file(file_path: str, target_text: str, replacement_text: str) -> str:
    """Replaces exact target text with replacement text in a file."""
    file_path = normalize_workspace_path(file_path)
    if not is_safe_path(Path(file_path)):
        return f"❌ SECURITY BLOCK: Access to '{file_path}' is strictly forbidden by the system admin. Do not attempt to modify this file."

    full_path = AGENT_ROOT_DIR / file_path
    
    if not full_path.exists():
        return f"❌ Error: File {file_path} not found."
    
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
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        if file_path.endswith('.py'):
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return (f"✅ Replaced text, BUT the file still has a syntax error on line {e.lineno}: {e.msg}\n"
                        f"SYSTEM HINT: Use `replace_in_file` again to fix the remaining syntax errors.")
                        
        return f"✅ Successfully replaced text in {file_path}."
    except FileNotFoundError:
        return f"❌ Error: File {file_path} not found."
    
def read_file_lines(file_path: str, start_line: int, end_line: int):
    """Reads specific lines from a file."""
    try:
        path_obj = resolve_tool_path(file_path)
        if not is_safe_path(path_obj):
            return f"SECURITY BLOCK: Access to '{path_obj.name}' is strictly forbidden. Do not attempt to read this file again."
        if not path_obj.exists():
            return f"File not found: {file_path}"
        
        start = max(1, int(start_line))
        end = int(end_line)
        with open(path_obj, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        if start > total_lines:
            return f"Error: start_line exceeds total lines."
        end = min(total_lines, end)
        
        output_lines = [f"{i+1}: {lines[i].rstrip()}" for i in range(start - 1, end)]
        return f"Lines {start} to {end} of {file_path}:\n\n" + "\n".join(output_lines)
    except Exception as e:
        return f"Error reading file lines: {e}"
   
def search_tool_library(keyword: str) -> str:
    """
    Search the agent's massive offline tool library for a specific capability.
    """
    try:
        from tool_library import ALL_TOOLS
    except ImportError:
        ALL_TOOLS = {}
        
    search_terms = [term.strip().lower() for term in keyword.replace(',', ' ').split() if len(term) > 2]
    found_tools = []
    
    for name, info in ALL_TOOLS.items():
        tool_text = (name + " " + info.get('description', '')).lower()
        
        if any(term in tool_text for term in search_terms):
            sig = inspect.signature(info['func'])
            template = f"### 🛠️ ACTION: {name}"
            
            for param in sig.parameters:
                if param == 'kwargs': continue
                template += f"\n**{param}**: ..."
                
            found_tools.append(f"TOOL: {name}\nDESC: {info.get('description', '')}\nFORMAT:\n{template}")
            
    if not found_tools:
        return f"❌ No tools found matching '{keyword}'. Try a different search term."
        
    return "✅ FOUND TOOLS:\n\n" + "\n\n".join(found_tools) + "\n\nTo use a tool, simply output its exact ACTION format in your next response."

def mark_objective_complete(summary_of_work: str) -> str:
    """
    Call this tool the EXACT moment you have fully completed your current specific objective.
    The OS will record your summary and advance you to the next step.
    """
    return f"TRIGGER_STEP_ADVANCE: {summary_of_work}"

def finish_task(message_to_user: str) -> str:
    """
    CRITICAL: Use this tool ONLY when all steps are complete. 
    Use the 'message_to_user' argument to converse directly with the user, provide short answers, or summarize your findings.
    """
    return f"TASK_COMPLETED_SUCCESSFULLY: {message_to_user}"

def get_directory_tree(path: str = ".", max_depth: int = 3) -> str:
    """
    Generates a visual tree structure of a directory. 
    Automatically ignores massive bloat folders like .git, venv, and __pycache__.
    Use this to understand project architecture in one single tool call instead of listing directories manually.
    """
    import os
    from pathlib import Path

    try:
        max_depth = int(max_depth)
    except ValueError:
        max_depth = 3

    ignore_dirs = {'.git', '__pycache__', 'node_modules', 'venv', 'env', 'ai-agent-env', '.pytest_cache', 'vector_db'}
    
    target_path = Path(path).expanduser().resolve()
    if not target_path.exists():
        return f"❌ Error: Directory '{target_path}' does not exist."
    
    tree_str = f"Directory Tree for: {target_path.name}/\n"
    
    def walk_dir(current_path, current_depth, prefix=""):
        nonlocal tree_str
        
        if len(tree_str) > 5000:
            return
            
        if current_depth > max_depth:
            tree_str += f"{prefix}└── ... [MAX DEPTH REACHED]\n"
            return
            
        try:
            items = sorted(list(current_path.iterdir()), key=lambda x: (not x.is_dir(), x.name))
        except PermissionError:
            tree_str += f"{prefix}└── [PERMISSION DENIED]\n"
            return
            
        items = [item for item in items if not (item.is_dir() and item.name in ignore_dirs)]
        
        for i, item in enumerate(items):
            if len(tree_str) > 5000:
                tree_str += f"{prefix}└── ... [TRUNCATED DUE TO MASSIVE SIZE]\n"
                break
                
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            
            if item.is_dir():
                tree_str += f"{prefix}{connector}📁 {item.name}/\n"
                extension_prefix = "    " if is_last else "│   "
                walk_dir(item, current_depth + 1, prefix + extension_prefix)
            else:
                tree_str += f"{prefix}{connector}📄 {item.name}\n"

    walk_dir(target_path, 1)
    
   
    if len(tree_str) > 5000:
        tree_str = tree_str[:5000] + "\n\n... [TREE TRUNCATED FOR SAFETY. DO NOT USE LARGE MAX_DEPTH HERE]"
        
    return tree_str

SURVIVAL_TOOLS = {
    "read_file": {"func": read_file, "description": inspect.getdoc(read_file)},
    "read_file_lines": {"func": read_file_lines, "description": inspect.getdoc(read_file_lines)},
    "write_file": {"func": write_file, "description": inspect.getdoc(write_file)},
    "replace_in_file": {"func": replace_in_file, "description": inspect.getdoc(replace_in_file)},
    "list_directory": {"func": list_directory, "description": inspect.getdoc(list_directory)},
    "mark_objective_complete": {"func": mark_objective_complete, "description": inspect.getdoc(mark_objective_complete)},
    "finish_task": {"func": finish_task, "description": inspect.getdoc(finish_task)},
    "get_directory_tree": {"func": get_directory_tree, "description": inspect.getdoc(get_directory_tree)},
    "search_tool_library": {"func": search_tool_library, "description": inspect.getdoc(search_tool_library)}
}