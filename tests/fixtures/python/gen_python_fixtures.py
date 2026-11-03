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


if __name__ == "__main__":
    main()
