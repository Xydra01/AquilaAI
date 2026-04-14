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
        if sys.platform == "darwin":  # macOS
            safe_apps = {
                "chrome": "open -a 'Google Chrome'",
                "notepad": "open -e" # Opens TextEdit on Mac
            }
            cmd = safe_apps.get(process_name.lower())
            if not cmd:
                return f"❌ Cannot start '{process_name}'. Not in safe apps list."
            subprocess.Popen(cmd, shell=True)
        else:  # Default to Windows/Linux logic
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
    
OS_TOOLS = {
    "read_file_lines": {"func": read_file_lines, "description": inspect.getdoc(read_file_lines)},
    "search_in_file": {"func": search_in_file, "description": inspect.getdoc(search_in_file)},
    "manage_process": {"func": manage_process, "description": inspect.getdoc(manage_process)},
    "search_files": {"func": search_files, "description": inspect.getdoc(search_files)},
}