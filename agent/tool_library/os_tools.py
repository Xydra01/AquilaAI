#Tools that interact directly with the OS

from pathlib import Path
import subprocess
import shutil
import psutil
import inspect
from tools import is_safe_path


def read_file_lines(file_path: str, start_line: int, end_line: int):
    """Reads specific lines from a file."""
    try:
        path_obj = Path(file_path).expanduser()
        if not is_safe_path(path_obj):
            return f"SECURITY BLOCK: Access to '{path_obj.name}' is strictly forbidden."
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

def search_in_file(file_path: str, keyword: str = None, **kwargs) -> str:
    """Searches for a keyword in a file."""
    actual_keyword = keyword or kwargs.get('search_text', '')
    
    if not actual_keyword:
        return "❌ Error: You must provide a 'keyword' to search for."
    try:
        path_obj = Path(file_path).expanduser()
        if not is_safe_path(path_obj):
            return f"SECURITY BLOCK: Access to '{path_obj.name}' is forbidden."
        if not path_obj.exists():
            return f"File not found: {file_path}"
        
        matches = []
        with open(path_obj, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if actual_keyword.lower() in line.lower():
                    matches.append(f"{i+1}: {line.strip()}")
                    
        if not matches:
            return f"Keyword '{actual_keyword}' not found in {file_path}."
        if len(matches) > 50:
            return f"Found {len(matches)} matches. Showing first 50:\n\n" + "\n".join(matches[:50])
        return f"Found {len(matches)} matches:\n\n" + "\n".join(matches)
    except Exception as e:
        return f"Error searching in file: {e}"
    
# os_tools.py - Surgical Change: Platform-Aware Process Management
import sys

def manage_process(action: str, process_name: str) -> str:
    """Safely starts or stops a specific background process on the host machine."""
    print(f"\n[bold red]⚠️ AquilaAI wants to {action.upper()} the process: {process_name}[/bold red]")
    approval = input("Allow? (y/n): ")
    if approval.lower() != 'y':
        return "❌ Action denied by User."

    if action == "stop":
        killed = 0
        for proc in psutil.process_iter(['pid', 'name']):
            if process_name.lower() in proc.info['name'].lower():
                psutil.Process(proc.info['pid']).terminate()
                killed += 1
        return f"✅ Stopped {killed} instances of {process_name}."
        
    elif action == "start":
        # Check platform to determine the correct execution command
        if sys.platform == "darwin":  # macOS logic
            safe_apps = {
                "chrome": "open -a 'Google Chrome'",
                "notepad": "open -e" # Opens TextEdit on Mac
            }
            cmd = safe_apps.get(process_name.lower())
            if not cmd:
                return f"❌ Cannot start '{process_name}'. Not in safe apps list."
            subprocess.Popen(cmd, shell=True)
        else: # Windows/Linux logic
            safe_apps = {
                "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "notepad": "notepad.exe"
            }
            path = safe_apps.get(process_name.lower())
            if not path:
                return f"❌ Cannot start '{process_name}'. Not in safe apps list."
            subprocess.Popen(path)
            
        return f"✅ Started {process_name}."
    
def search_files(pattern, path="."):
    """Recursively searches for files matching a pattern."""
    try:
        target = Path(path).expanduser().resolve()
        matches = list(target.rglob(pattern))
        if not matches:
            return f"No files matching '{pattern}' found in {target}"
        results = [str(m.relative_to(target)) for m in matches[:50]] 
        if len(matches) > 50:
            results.append(f"... and {len(matches) - 50} more.")
        return f"Found {len(matches)} matches for '{pattern}':\n" + "\n".join(results)
    except Exception as e:
        return f"Error searching files: {e}"
    
def delete_file(file_path: str) -> str:
    """Deletes a file from the file system."""
    try:
        path_obj = Path(file_path).expanduser().resolve()
        
        if not is_safe_path(path_obj):
            return f"❌ SECURITY BLOCK: You are forbidden from deleting '{path_obj.name}'."
        if not path_obj.exists():
            return f"❌ Error: File not found at {file_path}"
        if path_obj.is_dir():
            return f"❌ Error: '{file_path}' is a directory, not a file."
            
        path_obj.unlink()
        return f"✅ Successfully deleted {file_path}"
    except Exception as e:
        return f"❌ Error deleting file: {e}"

def rename_file(old_path: str, new_name: str) -> str:
    """Renames a file in its current directory."""
    try:
        old_path_obj = Path(old_path).expanduser().resolve()
        
        if not is_safe_path(old_path_obj):
            return f"❌ SECURITY BLOCK: Cannot rename forbidden file '{old_path_obj.name}'."
        if not old_path_obj.exists():
            return f"❌ Error: File not found at {old_path}"
            
        # Construct the new path in the same parent directory
        new_path_obj = old_path_obj.parent / new_name
        
        if not is_safe_path(new_path_obj):
            return f"❌ SECURITY BLOCK: New name '{new_name}' uses a forbidden extension or name."
        if new_path_obj.exists():
            return f"❌ Error: A file named '{new_name}' already exists here."

        old_path_obj.rename(new_path_obj)
        return f"✅ Successfully renamed to {new_name}"
    except Exception as e:
        return f"❌ Error renaming file: {e}"
    
def move_file(source_path: str, dest_dir: str) -> str:
    """Moves a file to a new directory."""
    try:
        src_obj = Path(source_path).expanduser().resolve()
        dest_obj = Path(dest_dir).expanduser().resolve()
        
        if not is_safe_path(src_obj):
            return f"❌ SECURITY BLOCK: Cannot move forbidden file '{src_obj.name}'."
        if not src_obj.exists():
            return f"❌ Error: Source file not found at {source_path}"
            
        # Ensure destination directory exists
        dest_obj.mkdir(parents=True, exist_ok=True) 
        target_path = dest_obj / src_obj.name
        
        if target_path.exists():
            return f"❌ Error: A file with this name already exists at destination {target_path}"
            
        shutil.move(str(src_obj), str(target_path))
        return f"✅ Successfully moved {src_obj.name} to {dest_dir}"
    except Exception as e:
        return f"❌ Error moving file: {e}"
    
def create_directory(dir_path: str) -> str:
    """Creates a new directory and any necessary parent directories."""
    try:
        path_obj = Path(dir_path).expanduser().resolve()
        if path_obj.exists():
            return f"⚠️ Directory already exists: {dir_path}"
            
        path_obj.mkdir(parents=True, exist_ok=True)
        return f"✅ Successfully created directory: {dir_path}"
    except Exception as e:
        return f"❌ Error creating directory: {e}"
    
def get_env_variables(keys_to_check: str = "") -> str:
    """
    Checks the currently loaded environment variables. 
    If keys_to_check is provided (comma separated), returns their values safely masked.
    If left empty, returns a list of all available environment variable names.
    """
    try:
        import os
        env_vars = dict(os.environ)
        
        # If the agent wants to check specific keys (e.g. "TAVILY_API_KEY, SMTP_PORT")
        if keys_to_check:
            requested_keys = [k.strip() for k in keys_to_check.split(",")]
            results = []
            for k in requested_keys:
                if k in env_vars:
                    val = env_vars[k]
                    # Mask sensitive keys so they don't leak into the context window
                    if any(secret in k.upper() for secret in ['KEY', 'TOKEN', 'SECRET', 'PASSWORD']):
                        val = f"{val[:4]}...{val[-4:]}" if len(val) > 8 else "****"
                    results.append(f"{k} = {val}")
                else:
                    results.append(f"{k} = NOT SET")
            return "✅ Environment Check:\\n" + "\\n".join(results)
            
        # If no keys provided, just list all the names loaded in memory
        # We filter out the massive Windows-specific ones so we don't nuke the context window
        ignore_sys = ['PATH', 'PSMODULEPATH', 'COMMONPROGRAMFILES']
        safe_keys = [k for k in env_vars.keys() if k not in ignore_sys]
        
        return "✅ Available Environment Variables (Names Only):\\n" + ", ".join(sorted(safe_keys))
        
    except Exception as e:
        return f"❌ Error reading env variables: {e}"

OS_TOOLS = {
    "read_file_lines": {"func": read_file_lines, "description": inspect.getdoc(read_file_lines)},
    "search_in_file": {"func": search_in_file, "description": inspect.getdoc(search_in_file)},
    "manage_process": {"func": manage_process, "description": inspect.getdoc(manage_process)},
    "search_files": {"func": search_files, "description": inspect.getdoc(search_files)},
    "delete_file": {"func": delete_file, "description": inspect.getdoc(delete_file)},
    "rename_file": {"func": rename_file, "description": inspect.getdoc(rename_file)},
    "move_file": {"func": move_file, "description": inspect.getdoc(move_file)},
    "create_directory": {"func": create_directory, "description": inspect.getdoc(create_directory)},
    "get_env_variables": {"func": get_env_variables, "description": inspect.getdoc(get_env_variables)},
}