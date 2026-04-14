#Tools used primarily for coding

import subprocess
from pathlib import Path
from tools import is_safe_path
import os
import sys
import ast
import chromadb
import inspect
from chromadb.utils import embedding_functions
from tools import AGENT_CORE_DIR, check_syntax

# Initialize the local Vector Database
chroma_client = chromadb.PersistentClient(path=str(AGENT_CORE_DIR / "vector_db"))
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
tool_collection = chroma_client.get_or_create_collection(name="tool_registry", embedding_function=sentence_transformer_ef)

def _index_codebase(directory: str):
    """Hidden helper function to read and embed all .py files in a directory."""
    collection = chroma_client.get_or_create_collection(name="codebase", embedding_function=sentence_transformer_ef)
    try:
        chroma_client.delete_collection("codebase")
        collection = chroma_client.create_collection(name="codebase", embedding_function=sentence_transformer_ef)
    except:
        pass
    documents, metadatas, ids = [], [], []
    chunk_id = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                # ADD errors='ignore' HERE
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                chunks = content.split('\n\n')
                for chunk in chunks:
                    if len(chunk.strip()) > 10:
                        documents.append(chunk)
                        metadatas.append({"file": file_path})
                        ids.append(f"chunk_{chunk_id}")
                        chunk_id += 1
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
    return collection

def semantic_code_search(query: str, directory: str = "./") -> str:
    """Searches the codebase for specific logic by meaning."""
    try:
        collection = _index_codebase(directory)
        results = collection.query(query_texts=[query], n_results=2)
        if not results['documents'][0]:
            return f"❌ No relevant code found for '{query}'."
        output = f"🔍 Semantic Search Results for '{query}':\n\n"
        for i, doc in enumerate(results['documents'][0]):
            file_source = results['metadatas'][0][i]['file']
            output += f"--- Found in {file_source} ---\n```python\n{doc}\n```\n\n"
        return output.strip()
    except Exception as e:
        return f"❌ Error performing semantic search: {e}"

def run_python_script(file_path: str, args: str = "") -> str:
    """Executes a Python script and safely compresses tracebacks."""
    try:
        result = subprocess.run(
            [sys.executable, file_path] + args.split(),
            capture_output=True,
            text=True,
            timeout=15,
            cwd=os.path.dirname(os.path.abspath(file_path))
        )
        output, error = result.stdout, result.stderr
        if result.returncode != 0:
            if "Traceback (most recent call last):" in error:
                lines = error.strip().split('\n')
                if len(lines) > 6:
                    compressed_error = f"{lines[0]}\n... [INTERNAL TRACEBACK COMPRESSED] ...\n" + "\n".join(lines[-4:])
                else:
                    compressed_error = error
                return (f"❌ Error: Script crashed.\n\nTraceback:\n{compressed_error}\n\n"
                        f"SYSTEM HINT: Check your `project_plan.md` to see what you were working on, "
                        f"then use `replace_function` to fix this specific error.")
            return f"❌ Error executing script:\n{error}"
        return f"✅ Execution successful. Output:\n{output}"
    except subprocess.TimeoutExpired:
        return "✅ Execution successful (Process timed out after 15 seconds, normal for game loop)."
    except Exception as e:
        return f"❌ Error running script: {e}"
    
def replace_function(file_path: str, function_name: str, new_code: str) -> str:
    """Surgically replaces an entire function or class by name using AST parsing."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        lines = source.split('\n')
        target_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == function_name:
                    target_node = node
                    break
        if not target_node:
            return f"❌ Error: Function or Class '{function_name}' not found in {file_path}."
        
        start_line = target_node.lineno - 1
        if hasattr(target_node, 'decorator_list') and target_node.decorator_list:
            start_line = target_node.decorator_list[0].lineno - 1
        end_line = target_node.end_lineno
        
        new_lines = new_code.split('\n')
        updated_lines = lines[:start_line] + new_lines + lines[end_line:]
        new_content = '\n'.join(updated_lines)
        
        if file_path.endswith('.py'):
            is_valid, err_msg = check_syntax(new_content)
            if not is_valid:
                return f"❌ Error: Replacement NOT applied. Syntax error:\n{err_msg}"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return f"✅ Successfully replaced '{function_name}' in {file_path}."
    except FileNotFoundError:
        return f"❌ Error: File not found."
    except SyntaxError:
        return f"❌ Error: File has a syntax error, AST parsing failed. Use read_file to fix it."

def lint_python_file(file_path: str) -> str:
    """
    Lints a Python file using flake8 to catch syntax errors, undefined names, and other static analysis bugs.
    """
    try:
        path_obj = Path(file_path).expanduser()
        if not is_safe_path(path_obj):
            return f"❌ SECURITY BLOCK: Access to '{path_obj.name}' is strictly forbidden."
        if not path_obj.exists():
            return f"❌ Error: File not found: {file_path}"
        
        #Uses flake8 through python, and has increased max line length so the agent doesn't get warnings

        result = subprocess.run(
            [sys.executable, "-m", "flake8", str(path_obj), "--max-line-length=120"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            return f"✅ Linting passed: No static analysis or syntax errors found in {path_obj.name}."
            
        else:
            output = result.stdout.strip() or result.stderr.strip()
            #Handles cases where flake8 isn't installed without crashing the entire coding_tools script
            if "No module named flake8" in output:
                return "❌ Error: 'flake8' is not installed in the virtual environment. Please run 'pip install flake8'."
            
            error_msg = (
                f"❌ Flake8 found issues in {path_obj.name}:\n\n"
                f"{output}\n\n"
                f"SYSTEM HINT: Review the line numbers and error codes above, then use `replace_in_file` or `replace_function` to fix them."
            )
            return error_msg
    
    except Exception as e:
        return f"❌ Error running flake8: {e}"

    
CODING_TOOLS = {
    "_index_codebase": {"func": _index_codebase, "description": inspect.getdoc(_index_codebase)},
    "semantic_code_search": {"func": semantic_code_search, "description": inspect.getdoc(semantic_code_search)},
    "run_python_script": {"func": run_python_script, "description": inspect.getdoc(run_python_script)},
    "replace_function": {"func": replace_function, "description": inspect.getdoc(replace_function)},
    "lint_python_file": {"func": lint_python_file, "description": inspect.getdoc(lint_python_file)},
}