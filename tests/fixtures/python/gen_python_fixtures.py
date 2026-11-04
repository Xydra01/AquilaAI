"""Generate *.python.json parity fixtures from the pinned Python reference.

The C++ tests require to_canonical_string(parse(F)) == bytes(F) for each output,
i.e. C++ serializes these values exactly as Python does.

Usage (from the Aquila-cpp root):
    python tests/fixtures/python/gen_python_fixtures.py [--py-ref PATH]

The reference is found via --py-ref, AQUILA_PY_REF, or ../agent-projects.
Importing the `agent` package connects to Ollama (RECON_MAP H4), so the two
sources are loaded without it: ollama_messages.py by file path, and only the
ChecklistItemState class body from run_state.py.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PINNED_SHA = "759212af3ae379f0c514e105dc97dd557cdaa0c0"
SOURCES = ("agent/parser/ollama_messages.py", "agent/core/run_state.py",
           "agent/policies/context_manager.py")
OUT_DIR = Path(__file__).resolve().parent


def resolve_py_ref(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    if os.environ.get("AQUILA_PY_REF"):
        return Path(os.environ["AQUILA_PY_REF"]).resolve()
    return (Path(__file__).resolve().parents[3] / ".." / "agent-projects").resolve()


def check_pinned(py_ref: Path) -> None:
    head = subprocess.run(["git", "-C", str(py_ref), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if head != PINNED_SHA:
        sys.exit(f"Python reference HEAD is {head}, expected pinned {PINNED_SHA}")
    dirty = subprocess.run(["git", "-C", str(py_ref), "diff", "--quiet", PINNED_SHA, "--", *SOURCES])
    if dirty.returncode != 0:
        sys.exit(f"{SOURCES} differ from {PINNED_SHA} in {py_ref}")


def load_ollama_messages(py_ref: Path):
    spec = importlib.util.spec_from_file_location(
        "ollama_messages_ref", py_ref / "agent/parser/ollama_messages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_checklist_item_state(py_ref: Path):
    source = (py_ref / "agent/core/run_state.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ChecklistItemState")
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias("annotations")], level=0),
                              node], type_ignores=[])
    ast.fix_missing_locations(module)
    # dataclass() resolves string annotations through sys.modules[cls.__module__].
    ref_module = types.ModuleType("run_state_ref")
    ref_module.__dict__.update({"dataclass": dataclass, "Any": Any})
    sys.modules[ref_module.__name__] = ref_module
    exec(compile(module, "run_state.py:ChecklistItemState", "exec"), ref_module.__dict__)
    return ref_module.ChecklistItemState


def load_context_manager_funcs(py_ref: Path):
    """AST-extract the two pure context-manager functions without importing the
    `agent` package. context_manager.py imports agent.storage / .context_budget at
    module load, which would probe Ollama (H4); but estimate_messages_tokens and
    _keep_recent_turns have no agent imports (they use only builtins), so exec just
    those two function defs in an isolated namespace, mirroring
    load_checklist_item_state()."""
    source = (py_ref / "agent/policies/context_manager.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"estimate_messages_tokens", "_keep_recent_turns"}
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    if {n.name for n in defs} != wanted:
        sys.exit(f"could not locate {wanted} in context_manager.py @ {PINNED_SHA[:9]}")
    module = ast.Module(body=[ast.ImportFrom(module="__future__",
                                             names=[ast.alias("annotations")], level=0),
                              *defs], type_ignores=[])
    ast.fix_missing_locations(module)
    ns: dict[str, Any] = {}
    exec(compile(module, "context_manager.py:funcs", "exec"), ns)
    return ns["estimate_messages_tokens"], ns["_keep_recent_turns"]


# estimate_messages_tokens: each case is a list of OpenAI-style messages. The C++
# Message type carries plain-string content, so cover string-content messages that
# map cleanly to Message{role, content}; the point is the char/4 estimate agreeing.
ESTIMATE_CASES = [
    ("empty_list", []),
    ("single_empty", [{"role": "user", "content": ""}]),
    ("single_short", [{"role": "user", "content": "hi"}]),
    ("single_exact4", [{"role": "user", "content": "abcd"}]),
    ("single_medium", [{"role": "system", "content": "You are Aquila, a coding agent."}]),
    ("multi_small", [{"role": "system", "content": "sys"},
                     {"role": "user", "content": "do it"},
                     {"role": "assistant", "content": "ok"}]),
    ("multi_mixed_len", [{"role": "system", "content": "You are a careful assistant."},
                         {"role": "user", "content": "Create a file named harness_smoke.py"},
                         {"role": "assistant", "content": "Tool Outputs: wrote file"},
                         {"role": "user", "content": "now run the smoke test please"}]),
    ("unicode", [{"role": "user", "content": "naïve ✓ café ✓"}]),
    ("longish", [{"role": "user", "content": "x" * 400},
                 {"role": "assistant", "content": "y" * 123}]),
]

# _keep_recent_turns: a "tool-output turn" is a user message whose string content
# contains "Tool Outputs:". Cover the branches: fewer than K matches, exactly K,
# more than K, zero matches (history[-keep*2:] / list(history) fallback), keep=0.
def _tool(n: int) -> dict:
    return {"role": "user", "content": f"Tool Outputs: result {n}"}


def _chat(n: int) -> dict:
    return {"role": "assistant", "content": f"thinking {n}"}


KEEP_RECENT_CASES = [
    ("empty_history", [], 3),
    ("keep_zero", [_tool(1), _tool(2)], 0),
    ("fewer_than_k", [_tool(1), _chat(1), _tool(2)], 5),
    ("exactly_k", [_tool(1), _chat(1), _tool(2), _chat(2), _tool(3)], 3),
    ("more_than_k", [_tool(1), _chat(1), _tool(2), _tool(3), _chat(2), _tool(4)], 2),
    ("none_match_short", [_chat(1), _chat(2)], 2),
    ("none_match_fallback", [_chat(1), _chat(2), _chat(3), _chat(4), _chat(5)], 2),
    ("single_tool", [{"role": "user", "content": "hello"}, _tool(1)], 4),
]


def gen_context_oracle(py_ref: Path) -> None:
    """Oracle cases from the real context_manager token estimate and tail-keep."""
    estimate_messages_tokens, _keep_recent_turns = load_context_manager_funcs(py_ref)
    out_dir = OUT_DIR / "context"
    out_dir.mkdir(exist_ok=True)

    for name, messages in ESTIMATE_CASES:
        write_json(out_dir / f"messages_estimate_{name}.json",
                   {"case": name, "messages": messages,
                    "expected_tokens": estimate_messages_tokens(messages)})

    for name, history, keep in KEEP_RECENT_CASES:
        write_json(out_dir / f"keep_recent_{name}.json",
                   {"case": name, "history": history, "keep": keep,
                    "expected": _keep_recent_turns(history, keep)})

    print(f"wrote context/messages_estimate_*.json: {len(ESTIMATE_CASES)} cases, "
          f"context/keep_recent_*.json: {len(KEEP_RECENT_CASES)} cases")


def pinned_sources(py_ref: Path) -> dict[str, str]:
    """Non-test agent/*.py files read from git objects at PINNED_SHA (not the worktree)."""
    names = subprocess.run(
        ["git", "-C", str(py_ref), "ls-tree", "-r", "--name-only", PINNED_SHA, "agent"],
        capture_output=True, text=True, check=True).stdout.split()
    names = [n for n in names if n.endswith(".py") and not n.startswith("agent/tests/")]
    batch = subprocess.run(["git", "-C", str(py_ref), "cat-file", "--batch"],
                           input="".join(f"{PINNED_SHA}:{n}\n" for n in names).encode(),
                           capture_output=True, check=True).stdout
    out: dict[str, str] = {}
    pos = 0
    for name in names:
        header_end = batch.index(b"\n", pos)
        size = int(batch[pos:header_end].split()[2])
        out[name] = batch[header_end + 1:header_end + 1 + size].decode("utf-8")
        pos = header_end + 1 + size + 1
    return out


def collect_error_codes(sources: dict[str, str]) -> list[str]:
    """String literals Python uses as capability error codes:
    CapabilityResult.failure("x", ...), CapabilityError("x", ...),
    error_code="x" keywords, and `error_code = "x"` assignments."""
    codes: set[str] = set()

    def literal(node: ast.AST | None) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            codes.add(node.value)

    for text in sources.values():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call):
                f = node.func
                is_failure = (isinstance(f, ast.Attribute) and f.attr == "failure"
                              and isinstance(f.value, ast.Name) and f.value.id == "CapabilityResult")
                is_error = ((isinstance(f, ast.Name) and f.id == "CapabilityError")
                            or (isinstance(f, ast.Attribute) and f.attr == "CapabilityError"))
                if (is_failure or is_error) and node.args:
                    literal(node.args[0])
                for kw in node.keywords:
                    if kw.arg == "error_code":
                        literal(kw.value)
            elif isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "error_code" for t in node.targets):
                    literal(node.value)
    return sorted(codes)


ACT_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "tools": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": ["read_file", "write_file"]},
                           "arguments": {"type": "object"}},
            "required": ["name", "arguments"]}},
        "final_report": {"type": "string"},
    },
    "required": ["reasoning", "tools"],
}
PLAN_SCHEMA = {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "string"}}},
               "required": ["steps"]}

# Every env var _build_native_chat_payload (and the helpers it calls) reads.
PAYLOAD_ENV = ("AQUILA_ACT_NUM_PREDICT", "AQUILA_ACT_NUM_PREDICT_MICRO", "AQUILA_CHAT_NUM_PREDICT",
               "AQUILA_CHAT_NUM_PREDICT_THINK", "AQUILA_PLAN_NUM_PREDICT", "AQUILA_REPEAT_PENALTY",
               "AQUILA_TQ_REPEAT_PENALTY", "AQUILA_REPEAT_LAST_N", "OLLAMA_KEEP_ALIVE")

# (case, model, num_ctx, env, call kwargs, explicit C++ GenerationParams equivalent)
PAYLOAD_CASES = [
    ("act_code_agent", "aquila:latest", 8192, {"AQUILA_ACT_NUM_PREDICT": "1024"},
     dict(messages=[{"role": "system", "content": "You are Aquila."},
                    {"role": "user", "content": "Create hello.py"}],
          temperature=0.2, stream=False, format_spec=ACT_SCHEMA, plain_chat=False,
          keep_alive=None, think=False, surface="act"),
     {"temperature": 0.2, "num_ctx": 8192, "max_tokens": 1024, "repeat_penalty": 1.15,
      "repeat_last_n": 64, "think": False, "constraint": {"kind": "json_schema", "schema": ACT_SCHEMA}}),
    ("chat_think_stream", "aquila:latest", None, {},
     dict(messages=[{"role": "user", "content": "Explain KV caches."}],
          temperature=0.6, stream=True, format_spec=None, plain_chat=True,
          keep_alive="5m", think=True, surface="chat"),
     {"temperature": 0.6, "max_tokens": 4096, "repeat_penalty": 1.15, "repeat_last_n": 64,
      "think": True, "keep_alive": "5m"}),
    ("json_object", "aquila:latest", 4096, {},
     dict(messages=[{"role": "user", "content": "Return {}"}],
          temperature=0.1, stream=False, format_spec="json_object", plain_chat=False,
          keep_alive=None, think=None, surface="chat"),
     {"temperature": 0.1, "num_ctx": 4096, "repeat_penalty": 1.15, "repeat_last_n": 64,
      "constraint": {"kind": "json"}}),
    ("turboquant_model", "aquila-tq-32k", None, {},
     dict(messages=[{"role": "user", "content": "hi"}],
          temperature=0.3, stream=False, format_spec=None, plain_chat=True,
          keep_alive=None, think=None, surface="chat"),
     {"temperature": 0.3, "max_tokens": 2048, "repeat_penalty": 1.3, "repeat_last_n": 64}),
    ("multimodal_no_penalty", "aquila:latest", None, {"AQUILA_REPEAT_PENALTY": "1.0"},
     dict(messages=[{"role": "user", "content": [
              {"type": "text", "text": "What is this? naïve ✓"},
              {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aGVsbG8="}}]}],
          temperature=0.4, stream=False, format_spec=None, plain_chat=True,
          keep_alive=None, think=False, surface="chat"),
     {"temperature": 0.4, "max_tokens": 2048, "think": False}),
    ("plan_surface", "aquila:latest", 32768, {"AQUILA_PLAN_NUM_PREDICT": "3000"},
     dict(messages=[{"role": "user", "content": "Plan the refactor."}],
          temperature=0.3, stream=False, format_spec=PLAN_SCHEMA, plain_chat=False,
          keep_alive=None, think=False, surface="plan"),
     {"temperature": 0.3, "num_ctx": 32768, "max_tokens": 3000, "repeat_penalty": 1.15,
      "repeat_last_n": 64, "think": False, "constraint": {"kind": "json_schema", "schema": PLAN_SCHEMA}}),
    ("keep_alive_env", "aquila:latest", None, {"OLLAMA_KEEP_ALIVE": "30m"},
     dict(messages=[{"role": "user", "content": "hi"}],
          temperature=0.0, stream=True, format_spec=None, plain_chat=True,
          keep_alive=None, think=None, surface="chat"),
     {"temperature": 0.0, "max_tokens": 2048, "repeat_penalty": 1.15, "repeat_last_n": 64,
      "keep_alive": "30m"}),
]


def gen_payload_fixtures(py_ref: Path) -> None:
    """Payloads from the real OllamaClient._build_native_chat_payload at PINNED_SHA."""
    dirty = subprocess.run(["git", "-C", str(py_ref), "diff", "--quiet", PINNED_SHA, "--", "agent"])
    untracked = subprocess.run(["git", "-C", str(py_ref), "ls-files", "--others", "--exclude-standard",
                                "agent"], capture_output=True, text=True, check=True).stdout.strip()
    if dirty.returncode != 0 or untracked:
        sys.exit(f"agent/ in {py_ref} differs from {PINNED_SHA}; payload fixtures need the pinned tree")

    # Importing agent.core.main probes Ollama (H4); point it at a closed port.
    os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["AQUILA_DATA_ROOT"] = tempfile.mkdtemp(prefix="aquila-fixtures-")
    os.environ["AQUILA_SKIP_MIGRATE"] = "1"
    sys.path[:0] = [str(py_ref), str(py_ref / "agent")]
    import agent.core.main as py_main  # noqa: E402

    # Importing also applies the user's runtime settings, which re-point the
    # client at the real server. Building a payload does no I/O, but pin the
    # closed port anyway so nothing here can reach a live Ollama.
    client = py_main.client
    client.base_url = "http://127.0.0.1:9"
    out_dir = OUT_DIR / "payloads"
    out_dir.mkdir(exist_ok=True)
    for case, model, num_ctx, env, kwargs, params in PAYLOAD_CASES:
        for name in PAYLOAD_ENV:
            os.environ.pop(name, None)
        os.environ.update(env)
        client.model_name = model
        client.num_ctx = num_ctx
        call = dict(kwargs)
        payload = client._build_native_chat_payload(call.pop("messages"), call.pop("temperature"),
                                                    call.pop("stream"), call.pop("format_spec"), **call)
        doc = {"case": case, "model": model, "stream": kwargs["stream"], "params": params,
               "messages": payload["messages"], "python_payload": payload}
        with (out_dir / f"{case}.json").open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        print(f"wrote payloads/{case}.json")


SEARCH_REPLACE_CASES = [
    ("unique", "a = 1\nb = 2\nc = 3\n", "b = 2", "b = 20"),
    ("multiline", "x\ny\nz\n", "y\nz", "Y\nZ\nW"),
    ("delete", "keep\ndrop me\nkeep too\n", "drop me\n", ""),
    ("unicode", "naïve ✓\nend\n", "naïve ✓", "café ✓"),
    ("no_match", "a = 1\n", "b = 2", "x"),
    ("ambiguous", "dup\ndup\n", "dup", "x"),
    ("empty_search", "a\n", "", "x"),
]

PATCH_CASES = [
    ("change_line", "one\ntwo\nthree\n", "@@ -1,3 +1,3 @@\n one\n-two\n+TWO\n three\n"),
    ("insert_lines", "a\nb\n", "@@ -1,2 +1,4 @@\n a\n+a1\n+a2\n b\n"),
    ("delete_line", "a\nb\nc\n", "@@ -1,3 +1,2 @@\n a\n-b\n c\n"),
    ("middle_of_file", "1\n2\n3\n4\n5\n6\n7\n8\n", "@@ -4,3 +4,3 @@\n 4\n-5\n+five\n 6\n"),
    ("with_headers", "x\ny\n", "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n-x\n+X\n y\n"),
]

SYMBOL_SOURCES = {
    "app": (Path(__file__).resolve().parents[1] / "workspace" / "sample_repo" / "py" / "app.py"),
    "inline": "class A:\n    class B:\n        def m(self):\n            pass\n\ndef top():\n    def inner():\n        return 1\n    return inner\n\nasync def run():\n    pass\n",
    "decorated": "import dataclasses\n\n@dataclasses.dataclass\nclass P:\n    x: int\n\n@staticmethod\ndef s():\n    return 1\n",
}

SAFE_PATH_CASES = [
    # agent/tests/test_security.py
    "my_script.py", "Agent-Tasks/task_123.json", "Agent-Creations/final_report.md", "src/utils/helpers.py",
    ".env", "state.json", "chroma.sqlite3", "some/nested/folder/.env", "keys/aws_secret.pem", "database.sqlite3",
    "server.log", "Agent-Tasks/crash_dump.db", "Agent-Logs/session_1.txt", "vector_db/data.bin", ".git/config",
    "__pycache__/main.cpython-310.pyc",
    # extra cases
    ".gitignore", "src/.env.local", "home/id_rsa", "keys/deploy.key", "build/out.o", "node_modules/x/index.js",
    ".vscode/settings.json", "README.md", "naïve/ünïcode.txt",
]

PYTEST_SCENARIOS = {
    "all_pass": {"test_a.py": "def test_one():\n    assert 1\n\ndef test_two():\n    assert 2\n"},
    "mixed": {"test_m.py": "def test_ok():\n    assert True\n\ndef test_ok2():\n    assert True\n\n"
                           "def test_bad():\n    assert 1 == 2, 'one is not two'\n"},
    "many": {"test_x.py": "import pytest\n\ndef test_p1():\n    pass\n\ndef test_p2():\n    pass\n\n"
                          "def test_f1():\n    assert [1] == [2]\n\ndef test_f2():\n    raise ValueError('boom')\n\n"
                          "def test_f3():\n    assert 'a' in 'b'\n\n@pytest.mark.skip\ndef test_s():\n    pass\n\n"
                          "@pytest.mark.xfail\ndef test_x():\n    assert False\n"},
    "collection_error": {"test_broken.py": "def test_x(:\n    pass\n"},
    "no_tests": {"test_empty.py": "x = 1\n"},
}


def gen_workspace_oracle(py_ref: Path) -> None:
    """Oracle cases from the real Python Code Canvas / firewall / pytest runner."""
    from agent.core.tools import is_safe_path  # noqa: E402
    from agent.tool_library import code_agent_tools, code_canvas_tools  # noqa: E402
    from agent.coding import language_registry  # noqa: E402

    data_root = Path(tempfile.mkdtemp(prefix="aquila-ws-oracle-"))
    os.environ["AQUILA_DATA_ROOT"] = str(data_root)  # imports may have re-read .env
    os.environ["AQUILA_DIFF_REVIEW"] = "0"
    out_dir = OUT_DIR / "workspace"
    out_dir.mkdir(exist_ok=True)

    code_canvas_tools.init_code_project("oracle")
    root = code_canvas_tools._project_root(code_canvas_tools._load_state())
    root.mkdir(parents=True, exist_ok=True)

    def category(msg: str) -> str:
        if msg.startswith("✅"):
            return "ok"
        if "old_string is required" in msg:
            return "empty_search"
        if "not found" in msg:
            return "no_match"
        if "times in" in msg:
            return "ambiguous"
        return "other: " + msg[:80]

    sr = []
    for name, content, old, new in SEARCH_REPLACE_CASES:
        f = root / f"{name}.txt"
        f.write_bytes(content.encode("utf-8"))
        msg = code_agent_tools.search_replace(f"{name}.txt", old, new)
        # write_text() turns \n into \r\n on Windows; compare text, not line endings.
        result = f.read_text(encoding="utf-8")
        sr.append({"case": name, "content": content, "search": old, "replace": new,
                   "category": category(msg), "result_text": result})
    write_json(out_dir / "search_replace.json", sr)

    patches = []
    for name, content, patch in PATCH_CASES:
        path = f"{name}.txt"
        code_canvas_tools.create_buffer_file(path, content)
        msg = code_canvas_tools.apply_unified_patch(path, patch)
        entry = next(e for e in code_canvas_tools._load_state()["files"] if e["path"] == path)
        patches.append({"case": name, "content": content, "patch": patch, "ok": msg.startswith("✅"),
                        "result": entry["content"]})
    write_json(out_dir / "unified_patch.json", patches)

    symbols = []
    for name, src in SYMBOL_SOURCES.items():
        text = src.read_text(encoding="utf-8") if isinstance(src, Path) else src
        symbols.append({"case": name, "source": text, "names": code_canvas_tools._python_symbols(text)})
    write_json(out_dir / "python_symbols.json", symbols)

    write_json(out_dir / "is_safe_path.json",
               [{"path": p, "python_safe": bool(is_safe_path(Path(p)))} for p in SAFE_PATH_CASES])

    logs_dir = Path(__file__).resolve().parents[1] / "logs"
    logs_dir.mkdir(exist_ok=True)
    counts = []
    for name, files in PYTEST_SCENARIOS.items():
        scen = Path(tempfile.mkdtemp(prefix=f"aquila-pytest-{name}-"))
        for fname, text in files.items():
            (scen / fname).write_text(text, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-m", "pytest", ".", "-q", "--tb=short", "-p", "no:cacheprovider"],
                              cwd=scen, capture_output=True, text=True, timeout=120)
        output = (proc.stdout + proc.stderr).strip()
        output = output.replace(str(scen), "<tmp>")
        with (logs_dir / f"pytest_{name}.txt").open("w", encoding="utf-8", newline="\n") as f:
            f.write(output + "\n")
        original = language_registry._run_cmd
        language_registry._run_cmd = lambda cmd, timeout=90, cwd=None, _o=output, _c=proc.returncode: (_c, _o)
        try:
            res = language_registry.run_tests(".")
        finally:
            language_registry._run_cmd = original
        counts.append({"case": name, "exit_code": proc.returncode, "log": f"pytest_{name}.txt",
                       "python_passed": res.passed, "python_failed": res.failed, "python_ok": res.ok})
    write_json(out_dir / "pytest_counts.json", counts)
    print(f"wrote workspace/*.json: {len(sr)} search_replace, {len(patches)} patches, {len(symbols)} symbol sets, "
          f"{len(SAFE_PATH_CASES)} safe-path verdicts, {len(counts)} pytest runs")


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write(name: str, value: Any) -> None:
    path = OUT_DIR / f"{name}.python.json"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--py-ref")
    py_ref = resolve_py_ref(parser.parse_args().py_ref)
    check_pinned(py_ref)
    print(f"python reference: {py_ref} @ {PINNED_SHA[:9]}")

    adapt = load_ollama_messages(py_ref).adapt_messages_openai_to_native
    native = adapt([
        {"role": "system", "content": "You are Aquila. naïve ✓"},
        {"role": "user", "content": [
            {"type": "text", "text": "Describe "},
            {"type": "text", "text": "these"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aGVsbG8="}},
            {"type": "image_url", "image_url": {"url": "d29ybGQ="}},
        ]},
        {"role": "assistant", "content": "Line 1\nLine 2\t\"q\""},
    ])
    write("message_system", native[0])
    write("message_user_multimodal", native[1])
    write("message_assistant_escapes", native[2])

    item_cls = load_checklist_item_state(py_ref)
    write("checklist_item_pending", item_cls(id="c1", text="Analyze interface").to_dict())
    write("checklist_item_done", item_cls(id="c2", text="Apply edits", status="done").to_dict())
    write("checklist_item_skipped", item_cls(id="c3", text="Benchmark ✓", status="skipped").to_dict())

    sources = pinned_sources(py_ref)
    codes = collect_error_codes(sources)
    codes_path = OUT_DIR / "codes" / "error_codes.json"
    codes_path.parent.mkdir(exist_ok=True)
    with codes_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(codes, indent=2) + "\n")
    print(f"wrote codes/error_codes.json: {len(codes)} codes from {len(sources)} files")

    gen_context_oracle(py_ref)
    gen_payload_fixtures(py_ref)
    gen_workspace_oracle(py_ref)


if __name__ == "__main__":
    main()
