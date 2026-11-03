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
SOURCES = ("agent/parser/ollama_messages.py", "agent/core/run_state.py")
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

    gen_payload_fixtures(py_ref)


if __name__ == "__main__":
    main()
