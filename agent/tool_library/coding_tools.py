#Tools used primarily for coding

import os
import time
import chromadb
import inspect
from functools import lru_cache
from pathlib import Path
from typing import Any

# Firewall Import
from agent.core import get_code_project_root, should_skip_dir
from agent.storage import get_vector_db_path

get_vector_db_path().mkdir(parents=True, exist_ok=True)

_index_cache: dict[str, dict[str, Any]] = {}
_last_index_meta: dict[str, Any] = {}


def pop_last_index_meta() -> dict[str, Any]:
    """Return and clear metadata from the most recent index_code_project call."""
    meta = dict(_last_index_meta)
    _last_index_meta.clear()
    return meta


@lru_cache(maxsize=1)
def _get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(get_vector_db_path()))


@lru_cache(maxsize=1)
def _get_embedding_function():
    """
    Lazily construct the embedding function.

    Uses Aquila's offline-safe helper (hash by default; ONNX only if already cached).
    SentenceTransformer was avoided — it downloads weights and fights Ollama for VRAM.
    """
    from agent.storage.embeddings import get_aquila_embedding_function

    return get_aquila_embedding_function()


def _project_mtime(root: Path) -> float:
    try:
        latest = root.stat().st_mtime
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
            for fname in filenames:
                try:
                    latest = max(latest, (Path(dirpath) / fname).stat().st_mtime)
                except OSError:
                    pass
        return latest
    except OSError:
        return 0.0


def index_code_project(root: Path, *, force: bool = False, extensions: tuple[str, ...] | None = None):
    """Index a code project into Chroma with session-scoped cache."""
    global _last_index_meta
    started = time.monotonic()
    resolved = root.resolve()
    cache_key = str(resolved)
    mtime = _project_mtime(resolved)

    if not force and cache_key in _index_cache:
        cached = _index_cache[cache_key]
        if cached.get("mtime") == mtime and cached.get("collection") is not None:
            _last_index_meta = {
                "index_wall_ms": 0.0,
                "chunk_count": cached.get("chunk_count", 0),
                "cache_hit": True,
            }
            return cached["collection"]

    if extensions is None:
        try:
            from agent.coding import index_extensions

            extensions = tuple(index_extensions())
        except ImportError:
            extensions = (".py",)

    chroma_client = _get_chroma_client()
    ef = _get_embedding_function()
    from agent.storage.embeddings import embedding_collection_tag

    coll_name = f"codebase_{embedding_collection_tag()}_{resolved.name}"
    try:
        chroma_client.delete_collection(coll_name)
    except Exception:
        pass
    collection = chroma_client.create_collection(name=coll_name, embedding_function=ef)

    documents, metadatas, ids = [], [], []
    chunk_id = 0
    for walk_root, dirs, files in os.walk(resolved):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        for file in files:
            if file.endswith(extensions):
                file_path = os.path.join(walk_root, file)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                chunks = content.split("\n\n")
                for chunk in chunks:
                    if len(chunk.strip()) > 10:
                        documents.append(chunk)
                        metadatas.append({"file": file_path})
                        ids.append(f"chunk_{chunk_id}")
                        chunk_id += 1
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)

    chunk_count = len(documents)
    wall_ms = round((time.monotonic() - started) * 1000, 1)
    _index_cache[cache_key] = {
        "mtime": mtime,
        "collection": collection,
        "chunk_count": chunk_count,
    }
    _last_index_meta = {
        "index_wall_ms": wall_ms,
        "chunk_count": chunk_count,
        "cache_hit": False,
    }
    return collection


def _index_codebase(directory: str, extensions: tuple[str, ...] | None = None):
    """Hidden helper — prefer index_code_project for code mode."""
    root = Path(directory).resolve()
    return index_code_project(root, extensions=extensions)


def semantic_code_search(query: str, directory: str = "") -> str:
    """Searches the codebase for specific logic by meaning."""
    root = get_code_project_root()
    if not root and (not directory or directory in (".", "./")):
        try:
            from tool_library.code_canvas_tools import get_active_project_scope

            scope = get_active_project_scope()
            if scope:
                root = Path(scope["root"])
        except ImportError:
            pass
    if not root:
        root = Path(directory or ".").resolve()
    elif directory and directory not in (".", "./"):
        root = Path(directory).resolve()
    try:
        collection = index_code_project(root)
        results = collection.query(query_texts=[query], n_results=2)
        if not results["documents"] or not results["documents"][0]:
            return f"❌ No relevant code found for '{query}'."
        output = f"🔍 Semantic Search Results for '{query}':\n\n"
        for i, doc in enumerate(results["documents"][0]):
            file_source = results["metadatas"][0][i]["file"]
            output += f"--- Found in {file_source} ---\n```python\n{doc}\n```\n\n"
        return output.strip()
    except Exception as e:
        return f"❌ Error performing semantic search: {e}"

def replace_function(file_path: str, function_name: str, new_code: str) -> str:
    """
    Replaces a specific function in a file with new code.
    Uses text-based indentation tracking so it works even if the file contains fatal syntax errors!
    """
    from pathlib import Path

    path_obj = Path(file_path)
    if not path_obj.is_file():
        return f"❌ Error: File '{file_path}' does not exist."

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1

    search_str = f"def {function_name}("
    for i, line in enumerate(lines):
        if line.strip().startswith(search_str):
            start_idx = i
            break

    if start_idx == -1:
        return f"❌ Error: Could not find function '{function_name}' in {file_path}. Check spelling."

    def_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if line.strip() == "":
            continue
        curr_indent = len(line) - len(line.lstrip())
        if curr_indent <= def_indent:
            end_idx = i
            break
            
    if end_idx == -1:
        end_idx = len(lines)

    if not new_code.endswith("\n"):
        new_code += "\n"
        
    new_lines = lines[:start_idx] + [new_code] + lines[end_idx:]

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    test_result = test_python_script(file_path)

    return f"✅ Successfully replaced function '{function_name}'.\n\n[AUTO-TEST TRIGGERED]:\n{test_result}"

def test_python_script(file_path: str, args: list = None) -> str:
    """Lints and executes a python script."""
    import subprocess
    import sys
    from pathlib import Path

    path_obj = Path(file_path)
    if not path_obj.is_file():
        return f"❌ Error: File '{file_path}' does not exist."

    lint_result = subprocess.run(
        [sys.executable, "-m", "flake8", str(path_obj), "--select=E9,F"],
        capture_output=True, text=True
    )
    
    if lint_result.returncode != 0:
        with open(path_obj, "r", encoding="utf-8") as f:
            code = "".join([f"{i+1}: {line}" for i, line in enumerate(f.readlines())])
        return f"❌ LINTING FAILED. Here is the current file content so you can fix it:\n\n{code}\n\n--- ERRORS ---\n{lint_result.stdout}\n{lint_result.stderr}"

    cmd = [sys.executable, str(path_obj)]
    if args:
        cmd.extend(args)

    try:
        run_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = f"✅ LINTING PASSED.\n\n--- EXECUTION OUTPUT ---\n{run_result.stdout}"
        if run_result.stderr:
            output += f"\n--- ERRORS ---\n{run_result.stderr}"
        return output
    except Exception as e:
        return f"❌ Error executing script: {e}"

    
CODING_TOOLS = {
    "_index_codebase": {"func": _index_codebase, "description": inspect.getdoc(_index_codebase)},
    "semantic_code_search": {"func": semantic_code_search, "description": inspect.getdoc(semantic_code_search)},
    "replace_function": {"func": replace_function, "description": inspect.getdoc(replace_function)},
    "test_python_script": {"func": test_python_script, "description": inspect.getdoc(test_python_script)},
}
