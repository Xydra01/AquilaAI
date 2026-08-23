"""Detect and trim degenerate repetition in streamed chat content."""
from __future__ import annotations

import os
import re
from collections import Counter

from agent.core.plan_validator import _collapse_comma_repetition, is_degenerate_description

_DEGEN_NOTE = (
    "\n\n*(System Note: Output stopped — repetitive generation detected.)*"
)

_PHRASE_SUFFIX_LEN = 32
_PHRASE_REPEAT_MIN = 3


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def guard_enabled() -> bool:
    """Master switch for the repetition guard.

    Set ``AQUILA_STREAM_GUARD=0`` (or false/no/off) to fully disable both the
    mid-stream stop and the end-of-stream tail trimming.
    """
    return os.getenv("AQUILA_STREAM_GUARD", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _min_check_chars() -> int:
    return max(80, _env_int("AQUILA_STREAM_MIN_CHECK_CHARS", 200))


def _line_repeat_threshold() -> int:
    return max(3, _env_int("AQUILA_STREAM_LINE_REPEAT_MIN", 4))


def _line_dominance_ratio() -> float:
    raw = os.getenv("AQUILA_STREAM_LINE_DOMINANCE", "0.30").strip()
    try:
        return max(0.15, min(0.9, float(raw)))
    except ValueError:
        return 0.30


def has_line_repetition_loop(text: str) -> bool:
    """True when the same non-trivial line repeats many times."""
    lines = [ln.strip() for ln in (text or "").splitlines() if len(ln.strip()) > 10]
    if len(lines) < _line_repeat_threshold():
        return False
    counts = Counter(lines)
    _line, top = counts.most_common(1)[0]
    if top >= max(5, _line_repeat_threshold() + 1):
        return True
    if len(lines) >= 12:
        unique_ratio = len(counts) / len(lines)
        if unique_ratio < (1.0 - _line_dominance_ratio()):
            return True
    return False


def has_phrase_repetition_loop(text: str) -> bool:
    """Detect repeated suffixes or consecutive duplicate lines early."""
    raw = text or ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if lines:
        line_counts = Counter(lines)
        _top_line, top_n = line_counts.most_common(1)[0]
        if top_n >= _PHRASE_REPEAT_MIN and len(_top_line) > 8:
            return True

    if len(raw) < _min_check_chars():
        return False
    run = 0
    last = None
    for ln in lines:
        if ln == last:
            run += 1
            if run >= _PHRASE_REPEAT_MIN:
                return True
        else:
            run = 1
            last = ln

    compact = re.sub(r"\s+", " ", raw).strip()
    if len(compact) < _min_check_chars():
        return False
    suffix_len = min(_PHRASE_SUFFIX_LEN, max(12, len(compact) // 8))
    tail = compact[-suffix_len:]
    if len(tail) < 12:
        return False
        
    # Only look for repetitions in the immediate vicinity of the tail to avoid 
    # false positives on common phrases scattered throughout a long document.
    window_size = max(suffix_len * 6, 200)
    search_window = compact[-window_size:]
    
    count = 0
    start = 0
    while True:
        idx = search_window.find(tail, start)
        if idx < 0:
            break
        count += 1
        start = idx + max(1, len(tail) // 2)
        if count >= max(4, _PHRASE_REPEAT_MIN + 1):
            return True
    return False


def has_markdown_fence_loop(text: str) -> bool:
    """Third opening fence without balance suggests a code-block loop."""
    raw = text or ""
    if len(raw) < _min_check_chars():
        return False
    opens = len(re.findall(r"```", raw))
    return opens >= 3 and opens % 2 == 1


def should_stop_stream(acc_content: str) -> bool:
    """Return True when accumulated streamed content looks degenerate."""
    if not guard_enabled():
        return False
    text = (acc_content or "").strip()
    if has_phrase_repetition_loop(text):
        return True
    if has_markdown_fence_loop(text):
        return True
    if len(text) < _min_check_chars():
        return False
    if is_degenerate_description(text):
        return True
    return has_line_repetition_loop(text)


def trim_degenerate_tail(text: str) -> str:
    """
    Remove repetitive tail from finished text; collapse comma-spam runs.
    Returns original text if no meaningful trim applies.
    """
    raw = text or ""
    if not guard_enabled():
        return raw
    if not raw.strip():
        return raw

    collapsed = _collapse_comma_repetition(raw)
    if collapsed != raw and len(raw) > 200 and len(collapsed) < len(raw) * 0.15:
        return collapsed.rstrip()

    lines = raw.splitlines()
    if len(lines) < _line_repeat_threshold():
        if is_degenerate_description(collapsed):
            return collapsed[:2000].rstrip() + "…"
        return raw

    counts = Counter(ln.strip() for ln in lines if ln.strip())
    if not counts:
        return raw

    _dominant, top_count = counts.most_common(1)[0]
    if top_count < _line_repeat_threshold() and not is_degenerate_description(raw):
        return raw

    kept: list[str] = []
    repeat_run = 0
    last_line = None
    for ln in lines:
        stripped = ln.strip()
        if stripped and stripped == last_line:
            repeat_run += 1
        else:
            repeat_run = 1 if stripped else 0
            last_line = stripped or last_line
        if repeat_run >= _line_repeat_threshold():
            break
        kept.append(ln)

    trimmed = "\n".join(kept).rstrip()
    if len(trimmed) < len(raw) * 0.5 and len(trimmed) > 80:
        return trimmed
    if is_degenerate_description(raw) and len(trimmed) > 80:
        return trimmed
    return raw


def stream_stop_note() -> str:
    return _DEGEN_NOTE
