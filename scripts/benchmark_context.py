#!/usr/bin/env python3
"""
Context soak benchmark for Ollama + Aquila models.

Run with TurboQuant serve up and target model installed:
  set OLLAMA_MODEL=aquila-tq-64k
  python scripts/benchmark_context.py

Steps approximate context fill via repeated filler text; records latency per step.
VRAM must be observed manually (Task Manager / nvidia-smi).
"""
from __future__ import annotations

import os
import sys
import time

import requests

BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "aquila")
# Rough chars per token for filler estimation
CHARS_PER_TOKEN = 4
STEPS = [
    ("8k", 8_000),
    ("16k", 16_000),
    ("32k", 32_000),
    ("48k", 48_000),
    ("64k", 64_000),
]


def filler(target_tokens: int) -> str:
    line = "The quick brown fox jumps over the lazy dog. "
    need = max(1, target_tokens * CHARS_PER_TOKEN // len(line))
    return (line * need)[: target_tokens * CHARS_PER_TOKEN]


def chat(user_content: str, num_ctx: int | None) -> tuple[float, str]:
    payload: dict = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Reply with exactly: pong"},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "temperature": 0.1,
    }
    if num_ctx is not None:
        payload["options"] = {"num_ctx": num_ctx}
    start = time.perf_counter()
    r = requests.post(f"{BASE}/v1/chat/completions", json=payload, timeout=(10, 600))
    elapsed = time.perf_counter() - start
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return elapsed, content.strip()[:80]


def main() -> int:
    print(f"Ollama: {BASE}")
    print(f"Model:  {MODEL}")
    print("Watch GPU VRAM during this run.\n")

    try:
        tags = requests.get(f"{BASE}/api/tags", timeout=5).json()
        names = [m.get("name", "") for m in tags.get("models", [])]
        if not any(MODEL in n for n in names):
            print(f"WARNING: model '{MODEL}' not in tags. Install with ollama create.", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: cannot reach Ollama: {e}", file=sys.stderr)
        return 1

    results: list[tuple[str, float, bool]] = []
    for label, tokens in STEPS:
        try:
            elapsed, snippet = chat(filler(tokens), num_ctx=tokens * 2)
            ok = "pong" in snippet.lower()
            results.append((label, elapsed, ok))
            print(f"  {label:>4} (~{tokens} tok filler)  {elapsed:6.1f}s  reply={snippet!r}")
        except Exception as e:
            print(f"  {label:>4} FAILED: {e}")
            results.append((label, -1.0, False))
            break

    print("\nSummary (record stable max in docs/ollama-turboquant.md):")
    for label, elapsed, ok in results:
        status = "ok" if ok and elapsed >= 0 else "fail"
        print(f"  {label}: {status} ({elapsed:.1f}s)" if elapsed >= 0 else f"  {label}: fail")

    return 0 if results and results[-1][1] >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
