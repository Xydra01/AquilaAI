"""
Language detection, linting, and test execution for Aquila Code Mode.
Python: full flake8 + pytest. JS/TS/Rust/Go: basic lint when CLI available.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LanguageSpec:
    name: str
    extensions: tuple[str, ...]


@dataclass
class LintResult:
    ok: bool
    status: str  # ok | warn | error | unknown
    message: str
    line: int | None = None


@dataclass
class TestResult:
    ok: bool
    passed: int
    failed: int
    message: str
    summary: str


EXTENSION_MAP: dict[str, LanguageSpec] = {
    ".py": LanguageSpec("python", (".py",)),
    ".pyw": LanguageSpec("python", (".pyw",)),
    ".js": LanguageSpec("javascript", (".js", ".mjs", ".cjs")),
    ".mjs": LanguageSpec("javascript", (".mjs",)),
    ".cjs": LanguageSpec("javascript", (".cjs",)),
    ".ts": LanguageSpec("typescript", (".ts", ".tsx")),
    ".tsx": LanguageSpec("typescript", (".tsx",)),
    ".rs": LanguageSpec("rust", (".rs",)),
    ".go": LanguageSpec("go", (".go",)),
}


def index_extensions() -> set[str]:
    exts: set[str] = set()
    for spec in EXTENSION_MAP.values():
        exts.update(spec.extensions)
    return exts


def get_language(path: str) -> LanguageSpec | None:
    ext = Path(path).suffix.lower()
    return EXTENSION_MAP.get(ext)


def _run_cmd(cmd: list[str], cwd: str | None = None, timeout: int = 90) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=timeout,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return result.returncode, out.strip()
    except FileNotFoundError:
        return 127, f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except Exception as e:
        return 1, str(e)


def run_linter(file_path: str, content: str | None = None) -> LintResult:
    """Run language-appropriate linter on a file (or in-memory content written to temp)."""
    path = Path(file_path)
    spec = get_language(str(path))
    if not spec:
        return LintResult(True, "unknown", f"No linter configured for {path.suffix}")

    if spec.name == "python":
        return _lint_python(path, content)
    if spec.name == "javascript":
        return _lint_eslint(path, content)
    if spec.name == "typescript":
        return _lint_typescript(path, content)
    if spec.name == "rust":
        return _lint_rust(path)
    if spec.name == "go":
        return _lint_go(path)
    return LintResult(True, "unknown", "Unsupported language")


def _lint_python(path: Path, content: str | None) -> LintResult:
    target = path
    temp_path = None
    if content is not None:
        import ast

        try:
            ast.parse(content)
        except SyntaxError as e:
            return LintResult(False, "error", f"SyntaxError line {e.lineno}: {e.msg}", e.lineno)

    if content is not None and not path.exists():
        temp_path = path.with_suffix(path.suffix + ".aquila_lint")
        temp_path.write_text(content, encoding="utf-8")
        target = temp_path

    code, out = _run_cmd(
        [sys.executable, "-m", "flake8", str(target), "--max-line-length=120"],
        timeout=60,
    )
    if temp_path and temp_path.exists():
        temp_path.unlink(missing_ok=True)

    if code == 127 and "No module named flake8" in out:
        return LintResult(True, "unknown", "flake8 not installed; syntax OK via ast only.")
    if code == 0:
        return LintResult(True, "ok", "flake8: no issues")
    if code == 127:
        return LintResult(True, "unknown", out)
    first_line = out.split("\n")[0] if out else "lint failed"
    line_no = None
    m = re.search(r":(\d+):", first_line)
    if m:
        line_no = int(m.group(1))
    return LintResult(False, "error", first_line[:500], line_no)


def _lint_eslint(path: Path, content: str | None) -> LintResult:
    if content is not None and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    code, out = _run_cmd(["npx", "eslint", str(path), "--format", "compact"], timeout=90)
    if code == 127:
        return LintResult(True, "unknown", "eslint not available (install Node.js + eslint)")
    if code == 0:
        return LintResult(True, "ok", "eslint: no issues")
    return LintResult(False, "error", out[:500] or "eslint reported issues")


def _lint_typescript(path: Path, content: str | None) -> LintResult:
    if content is not None and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    code, out = _run_cmd(["npx", "tsc", "--noEmit", str(path)], timeout=120)
    if code == 127:
        return LintResult(True, "unknown", "tsc not available (install TypeScript)")
    if code == 0:
        return LintResult(True, "ok", "tsc: no issues")
    return LintResult(False, "error", out[:500] or "TypeScript check failed")


def _lint_rust(path: Path) -> LintResult:
    if not path.exists():
        return LintResult(True, "unknown", "File not on disk yet")
    manifest = path
    while manifest.parent != manifest:
        if (manifest / "Cargo.toml").exists():
            break
        manifest = manifest.parent
    if not (manifest / "Cargo.toml").exists():
        return LintResult(True, "unknown", "No Cargo.toml found; skip rust lint")
    code, out = _run_cmd(["cargo", "clippy", "--quiet"], cwd=str(manifest.parent), timeout=180)
    if code == 127:
        return LintResult(True, "unknown", "cargo not installed")
    if code == 0:
        return LintResult(True, "ok", "cargo clippy: no issues")
    return LintResult(False, "error", out[:500] or "clippy reported issues")


def _lint_go(path: Path) -> LintResult:
    if not path.exists():
        return LintResult(True, "unknown", "File not on disk yet")
    code, out = _run_cmd(["go", "vet", str(path)], timeout=60)
    if code == 127:
        return LintResult(True, "unknown", "go not installed")
    if code == 0:
        return LintResult(True, "ok", "go vet: no issues")
    return LintResult(False, "error", out[:500] or "go vet reported issues")


def run_tests(target: str = ".", extra_args: str = "") -> TestResult:
    """Run pytest (Python only in v1)."""
    cmd = [sys.executable, "-m", "pytest", target, "-q", "--tb=short"]
    if extra_args:
        cmd.extend(extra_args.split())
    code, out = _run_cmd(cmd, timeout=180)
    if code == 127 and "No module named pytest" in out:
        return TestResult(False, 0, 0, "pytest not installed", out)

    passed = failed = 0
    summary_match = re.search(r"(\d+) passed", out)
    fail_match = re.search(r"(\d+) failed", out)
    if summary_match:
        passed = int(summary_match.group(1))
    if fail_match:
        failed = int(fail_match.group(1))

    # pytest exit 0 = pass, 1 = failures, 2 = interrupted, 5 = no tests
    ok = code == 0
    if code == 5:
        return TestResult(False, 0, 0, "No tests collected", out[:2000])
    snippet = out[-2000:] if len(out) > 2000 else out
    return TestResult(ok, passed, failed, "pytest finished", snippet)
