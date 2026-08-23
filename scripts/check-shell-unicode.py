#!/usr/bin/env python3
"""
Scan Aquila for Unicode that breaks Windows PowerShell 5.1 / cmd / terminals.

Windows PowerShell 5.1 often reads .ps1 as the system ANSI code page (not UTF-8)
unless the file has a UTF-8 BOM. Fancy dashes and smart quotes then decode into
stray quote-like bytes and cause "string is missing the terminator" parse errors.

Examples:
  python scripts/check-shell-unicode.py
  python scripts/check-shell-unicode.py --fix-dry-run
  .\\scripts\\check-shell-unicode.ps1

Exit 1 if any CRITICAL/HIGH findings (default scope).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Characters that commonly break PS 5.1 / confuse cmd when UTF-8 is misread.
RISKY = {
    "\u2013": ("EN DASH", "-"),
    "\u2014": ("EM DASH", "-"),
    "\u2015": ("HORIZONTAL BAR", "-"),
    "\u2018": ("LEFT SINGLE QUOTE", "'"),
    "\u2019": ("RIGHT SINGLE QUOTE", "'"),
    "\u201a": ("SINGLE LOW-9 QUOTE", "'"),
    "\u201c": ("LEFT DOUBLE QUOTE", '"'),
    "\u201d": ("RIGHT DOUBLE QUOTE", '"'),
    "\u201e": ("DOUBLE LOW-9 QUOTE", '"'),
    "\u2026": ("ELLIPSIS", "..."),
    "\u00a0": ("NBSP", " "),
    "\u2022": ("BULLET", "*"),
    "\u2192": ("RIGHT ARROW", "->"),
    "\u2190": ("LEFT ARROW", "<-"),
    "\u2713": ("CHECK MARK", "[OK]"),
    "\u2714": ("HEAVY CHECK", "[OK]"),
    "\u274c": ("CROSS MARK", "[X]"),
    "\u26a0": ("WARNING SIGN", "WARNING"),
}

SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "ai-agent-env",
    "dist",
    "build",
    "vector_db",
    ".venv",
    "venv",
    "Agent-Logs",
    "Agent-Tasks",
    "Agent-Plans",
    "Agent-Research",
    "Agent-Drafts",
    "Agent-Code",
    "Agent-Instances",
    "llama-cpp-turboquant",
    "standalone_cnn_toolkit",
    "_internal",
}

# Prefer these roots (fast). Full-repo rglob is too slow on large Agent-* trees.
SCAN_ROOTS = (
    "packaging",
    "scripts",
)

SHELL_SUFFIXES = {".ps1", ".bat", ".cmd", ".iss"}
SOFT_SUFFIXES = {".sh"}


@dataclass(frozen=True)
class Hit:
    path: Path
    line: int
    col: int
    char: str
    name: str
    replacement: str
    severity: str  # CRITICAL | HIGH | WARN
    note: str = ""


def _has_utf8_bom(raw: bytes) -> bool:
    return raw.startswith(b"\xef\xbb\xbf")


def _severity_for(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in {".ps1", ".bat", ".cmd"}:
        return "CRITICAL"
    if suf == ".iss":
        return "HIGH"
    if suf == ".sh":
        return "WARN"
    return "WARN"


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def _iter_files(root: Path, *, include_soft: bool, full_tree: bool) -> list[Path]:
    allowed = set(SHELL_SUFFIXES)
    if include_soft:
        allowed |= SOFT_SUFFIXES
    out: list[Path] = []

    def consider(path: Path) -> None:
        if not path.is_file() or _should_skip(path):
            return
        if path.suffix.lower() in allowed:
            out.append(path)

    # Always include top-level launchers
    for path in root.iterdir():
        consider(path)

    if full_tree:
        for path in root.rglob("*"):
            consider(path)
    else:
        for rel in SCAN_ROOTS:
            base = root / rel
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                consider(path)

    # Deduplicate
    return sorted(set(out))


def scan_file(path: Path) -> list[Hit]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [
            Hit(
                path,
                0,
                0,
                "",
                "READ_ERROR",
                "",
                "CRITICAL",
                str(exc),
            )
        ]

    bom = _has_utf8_bom(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Legacy ANSI scripts - still scan as latin-1 for display
        text = raw.decode("latin-1", errors="replace")

    severity = _severity_for(path)
    hits: list[Hit] = []

    # PS1 without BOM + any non-ASCII is itself a footgun under PS 5.1
    if path.suffix.lower() == ".ps1" and not bom:
        non_ascii = [(i, ch) for i, ch in enumerate(text) if ord(ch) > 127]
        if non_ascii:
            # Prefer specific risky chars; if only other non-ascii, one summary hit
            pass

    for line_no, line in enumerate(text.splitlines(), start=1):
        for col, ch in enumerate(line, start=1):
            if ch in RISKY:
                name, repl = RISKY[ch]
                note = ""
                if path.suffix.lower() == ".ps1" and not bom:
                    note = "file has no UTF-8 BOM; PS 5.1 may mis-decode this"
                hits.append(
                    Hit(
                        path,
                        line_no,
                        col,
                        ch,
                        name,
                        repl,
                        severity,
                        note,
                    )
                )

    if path.suffix.lower() == ".ps1" and not bom and any(ord(c) > 127 for c in text):
        # If we already listed risky chars, still add a file-level reminder once
        if not any(h.name == "NO_UTF8_BOM" for h in hits):
            # Only add BOM warning when there is non-ASCII at all
            if any(ord(c) > 127 for c in text) and not hits:
                hits.append(
                    Hit(
                        path,
                        1,
                        1,
                        "",
                        "NO_UTF8_BOM",
                        "(add UTF-8 BOM or ASCII-only)",
                        "CRITICAL",
                        "non-ASCII content without UTF-8 BOM",
                    )
                )
            elif hits:
                # annotate first hit
                pass

    return hits


def ascii_safe_replace(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in RISKY:
            out.append(RISKY[ch][1])
        elif ord(ch) < 128:
            out.append(ch)
        else:
            # Leave other Unicode alone in --fix (could be intentional in .iss UI)
            # For shell scripts we still replace known risky only.
            out.append(ch)
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find shell-breaking Unicode in Aquila scripts"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also scan .sh (usually fine under Git Bash UTF-8)",
    )
    parser.add_argument(
        "--fix-dry-run",
        action="store_true",
        help="Print ASCII replacements without writing files",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite risky chars to ASCII in CRITICAL/HIGH files (.ps1/.bat/.cmd/.iss)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print summary + failures",
    )
    parser.add_argument(
        "--full-tree",
        action="store_true",
        help="Scan entire repo (slow). Default: packaging/ + scripts/ + top-level only",
    )
    args = parser.parse_args()

    files = _iter_files(
        REPO_ROOT, include_soft=args.all, full_tree=args.full_tree
    )
    all_hits: list[Hit] = []
    for path in files:
        all_hits.extend(scan_file(path))

    critical = [h for h in all_hits if h.severity == "CRITICAL"]
    high = [h for h in all_hits if h.severity == "HIGH"]
    warn = [h for h in all_hits if h.severity == "WARN"]

    def show(hits: list[Hit]) -> None:
        for h in hits:
            rel = h.path.relative_to(REPO_ROOT)
            loc = f"{rel}:{h.line}:{h.col}" if h.line else str(rel)
            glyph = f"U+{ord(h.char):04X}" if h.char else ""
            extra = f" ({h.note})" if h.note else ""
            line = (
                f"  {h.severity:8} {loc}  {h.name} {glyph}  "
                f"-> {h.replacement!r}{extra}"
            )
            if not args.quiet or h.severity in ("CRITICAL", "HIGH"):
                try:
                    print(line)
                except UnicodeEncodeError:
                    print(line.encode("ascii", errors="replace").decode("ascii"))

    print(f"Scanned {len(files)} shell/installer files under {REPO_ROOT}")
    if all_hits:
        print()
        show(critical + high + (warn if args.all else []))
    else:
        print("No risky Unicode found in scoped files.")

    if args.fix or args.fix_dry_run:
        # Group by file for CRITICAL/HIGH only
        by_file: dict[Path, list[Hit]] = {}
        for h in critical + high:
            by_file.setdefault(h.path, []).append(h)
        for path, hits in sorted(by_file.items(), key=lambda kv: str(kv[0])):
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            fixed = ascii_safe_replace(text)
            # Keep / add UTF-8 BOM for .ps1 after fix so future Unicode is safer
            if path.suffix.lower() == ".ps1":
                out_bytes = ("\ufeff" + fixed).encode("utf-8")
                bom_note = " (UTF-8 BOM added)"
            else:
                out_bytes = fixed.encode("utf-8")
                bom_note = ""
            rel = path.relative_to(REPO_ROOT)
            if args.fix_dry_run:
                print(f"\nDRY-RUN would rewrite {rel} ({len(hits)} hit(s)){bom_note}")
            else:
                path.write_bytes(out_bytes)
                print(f"\nFixed {rel} ({len(hits)} hit(s)){bom_note}")

        if args.fix and not args.fix_dry_run:
            # Re-scan so exit code reflects post-fix state
            all_hits = []
            for path in files:
                all_hits.extend(scan_file(path))
            critical = [h for h in all_hits if h.severity == "CRITICAL"]
            high = [h for h in all_hits if h.severity == "HIGH"]
            warn = [h for h in all_hits if h.severity == "WARN"]

    print()
    print(
        f"Summary: {len(critical)} critical, {len(high)} high, "
        f"{len(warn)} warn (soft)"
    )
    if critical or high:
        print(
            "\nTip: re-run with --fix to ASCII-sanitize CRITICAL/HIGH files, "
            "or --fix-dry-run to preview."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
