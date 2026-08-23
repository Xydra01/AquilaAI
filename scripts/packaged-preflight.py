#!/usr/bin/env python3
"""
Packaged-install preflight — catch installer/wizard bugs *before* PyInstaller.

Runs in seconds against the source tree (no compile). Use this whenever you
change setup wizard, Docker/search bundle, hardware profiles, or packaging
assets.

Examples:
  python scripts/packaged-preflight.py
  python scripts/packaged-preflight.py --quick
  .\\scripts\\packaged-preflight.ps1
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO_ROOT / "agent"

# Keep packaging-critical modules in sync with packaging/aquila.spec datas + wizard.
PACKAGING_ASSETS = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "searxng-settings.yml",
    REPO_ROOT / "modelfiles" / "Modelfile",
    REPO_ROOT / "modelfiles" / "Modelfile.lite",
    REPO_ROOT / "modelfiles" / "Modelfile.cpu",
    REPO_ROOT / "packaging" / "aquila.spec",
    REPO_ROOT / "packaging" / "aquila.iss",
    REPO_ROOT / "packaging" / "build-windows.ps1",
)

CRITICAL_IMPORTS = (
    "agent.gui.gui",
    "agent.gui.gui_pages.setup_wizard",
    "agent.gui.gui_pages.settings_page",
    "agent.aquila_runtime.setup_gate",
    "agent.aquila_runtime.search_bundle",
    "agent.aquila_runtime.docker_desktop",
    "agent.aquila_runtime.hardware_profile",
    "agent.aquila_runtime.model_setup",
    "agent.aquila_runtime.ollama_bundle",
    "agent.research.search_config",
)

# Hard-fail AST scan (NameErrors here have crashed packaged installs).
AST_SCAN_STRICT = (
    AGENT_DIR / "gui" / "gui_pages" / "setup_wizard.py",
)
# Advisory only — closures/lambdas create false positives in the heuristic.
AST_SCAN_SOFT = (
    AGENT_DIR / "gui" / "gui_pages" / "settings_page.py",
    AGENT_DIR / "aquila_runtime" / "search_bundle.py",
    AGENT_DIR / "aquila_runtime" / "docker_desktop.py",
    AGENT_DIR / "aquila_runtime" / "setup_gate.py",
    AGENT_DIR / "research" / "search_config.py",
)

PACKAGED_PYTEST = (
    "agent/tests/test_setup_wizard_search.py",
    "agent/tests/test_platform_paths.py",
    "agent/tests/test_hardware_profile.py",
    "agent/tests/test_model_setup.py",
    "agent/tests/test_setup_complete.py",
    "agent/tests/test_search_config.py",
    "agent/tests/test_cpu_timeouts.py",
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(CheckResult(name, ok, detail))

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if not r.ok]


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def check_assets(report: Report) -> None:
    print("\n== Packaging assets ==")
    missing = [str(p.relative_to(REPO_ROOT)) for p in PACKAGING_ASSETS if not p.is_file()]
    if missing:
        report.add("assets", False, ", ".join(missing))
        _fail("missing: " + ", ".join(missing))
    else:
        report.add("assets", True)
        _ok(f"{len(PACKAGING_ASSETS)} required files present")

    # Spec datas must match files we ship
    spec = (REPO_ROOT / "packaging" / "aquila.spec").read_text(encoding="utf-8")
    for token in ("docker-compose.yml", "searxng-settings.yml", "modelfiles"):
        if token not in spec:
            report.add(f"spec:{token}", False, "not referenced in aquila.spec")
            _fail(f"aquila.spec missing reference to {token}")
        else:
            report.add(f"spec:{token}", True)
            _ok(f"aquila.spec references {token}")


def check_imports(report: Report) -> None:
    print("\n== Critical imports ==")
    sys.path.insert(0, str(REPO_ROOT))
    for mod in CRITICAL_IMPORTS:
        try:
            __import__(mod)
            report.add(f"import:{mod}", True)
            _ok(mod)
        except Exception as exc:
            report.add(f"import:{mod}", False, f"{type(exc).__name__}: {exc}")
            _fail(f"{mod} — {type(exc).__name__}: {exc}")


def _undefined_names(path: Path) -> list[str]:
    """
    Heuristic: names loaded in a function/method that are not local, global,
    or imported at module level — catches the docker_status NameError class of bugs.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    module_bound: set[str] = {
        "True",
        "False",
        "None",
        "print",
        "len",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "min",
        "max",
        "sum",
        "any",
        "all",
        "open",
        "Exception",
        "BaseException",
        "isinstance",
        "issubclass",
        "getattr",
        "setattr",
        "hasattr",
        "super",
        "property",
        "staticmethod",
        "classmethod",
        "object",
        "type",
        "ValueError",
        "TypeError",
        "KeyError",
        "RuntimeError",
        "OSError",
        "ImportError",
        "PermissionError",
        "FileNotFoundError",
        "NotImplementedError",
        "AttributeError",
        "StopIteration",
        "__name__",
        "__file__",
        "__package__",
    }

    def bind_import(node: ast.AST, into: set[str]) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                into.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                into.add(alias.asname or alias.name)

    def bind_assign_target(target: ast.AST, into: set[str]) -> None:
        if isinstance(target, ast.Name):
            into.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                bind_assign_target(elt, into)
        elif isinstance(target, ast.Starred):
            bind_assign_target(target.value, into)

    def collect_bindings(root: ast.AST, into: set[str]) -> None:
        for node in ast.walk(root):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bind_import(node, into)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    bind_assign_target(t, into)
            elif isinstance(node, ast.AnnAssign) and node.target:
                bind_assign_target(node.target, into)
            elif isinstance(node, ast.For):
                bind_assign_target(node.target, into)
            elif isinstance(node, ast.With):
                for item in node.items:
                    if item.optional_vars:
                        bind_assign_target(item.optional_vars, into)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                into.add(node.name)
            elif isinstance(node, ast.Lambda):
                for arg in list(node.args.posonlyargs) + list(node.args.args) + list(
                    node.args.kwonlyargs
                ):
                    into.add(arg.arg)
                if node.args.vararg:
                    into.add(node.args.vararg.arg)
                if node.args.kwarg:
                    into.add(node.args.kwarg.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                into.add(node.name)
            elif isinstance(node, ast.NamedExpr):
                bind_assign_target(node.target, into)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bind_import(node, module_bound)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                bind_assign_target(t, module_bound)
        elif isinstance(node, ast.AnnAssign) and node.target:
            bind_assign_target(node.target, module_bound)

    problems: list[str] = []

    def scan_function(fn: ast.AST, class_bound: set[str] | None = None) -> None:
        assert isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        local = set(module_bound)
        if class_bound:
            local |= class_bound
        local.add(fn.name)
        for arg in list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs):
            local.add(arg.arg)
        if fn.args.vararg:
            local.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            local.add(fn.args.kwarg.arg)

        collect_bindings(fn, local)

        nested_funcs = [
            n
            for n in ast.walk(fn)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn
        ]
        nested_nodes: set[ast.AST] = set()
        for nf in nested_funcs:
            for n in ast.walk(nf):
                nested_nodes.add(n)

        for node in ast.walk(fn):
            if node in nested_nodes:
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in ("self", "cls"):
                    continue
                if node.id not in local:
                    problems.append(f"{fn.name}: undefined name '{node.id}'")

        for nf in nested_funcs:
            scan_function(nf, class_bound=local)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scan_function(node)
        elif isinstance(node, ast.ClassDef):
            class_bound = {node.name}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    class_bound.add(item.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scan_function(item, class_bound=class_bound)

    seen: set[str] = set()
    out: list[str] = []
    for p in problems:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def check_ast_names(report: Report) -> None:
    print("\n== Static name checks (wizard / packaged paths) ==")
    for path, strict in (
        *((p, True) for p in AST_SCAN_STRICT),
        *((p, False) for p in AST_SCAN_SOFT),
    ):
        rel = path.relative_to(REPO_ROOT)
        if not path.is_file():
            report.add(f"ast:{rel}", False, "file missing")
            _fail(f"{rel} missing")
            continue
        try:
            problems = _undefined_names(path)
        except SyntaxError as exc:
            report.add(f"ast:{rel}", False, str(exc))
            _fail(f"{rel} syntax error: {exc}")
            continue
        if problems:
            detail = "; ".join(problems[:8])
            if strict:
                report.add(f"ast:{rel}", False, detail)
                _fail(f"{rel}: {detail}")
            else:
                report.add(f"ast:{rel}:soft", True, detail)
                print(f"  WARN  {rel}: {detail}")
        else:
            report.add(f"ast:{rel}", True)
            _ok(str(rel))


def check_wizard_pages(report: Report) -> None:
    print("\n== Setup wizard page construction (offscreen Qt) ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["AQUILA_SHOW_SETUP_WIZARD"] = "1"
    sys.path.insert(0, str(REPO_ROOT))

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        report.add("wizard:qt", False, str(exc))
        _fail(f"PySide6 unavailable: {exc}")
        return

    app = QApplication.instance() or QApplication([])

    from unittest.mock import patch

    from agent.aquila_runtime.hardware_profile import detect_hardware_profile
    from agent.aquila_runtime.virtualization import VirtualizationStatus
    from agent.gui.gui_pages import setup_wizard as sw

    profile = detect_hardware_profile()
    pages = [
        ("WelcomePage", lambda: sw.WelcomePage()),
        ("HardwarePage", lambda: sw.HardwarePage(profile)),
        ("OllamaPage", lambda: sw.OllamaPage()),
        ("ModelPage", lambda: sw.ModelPage(profile)),
        ("DonePage", lambda: sw.DonePage()),
    ]

    for name, factory in pages:
        try:
            factory()
            report.add(f"wizard:{name}", True)
            _ok(name)
        except Exception as exc:
            report.add(f"wizard:{name}", False, f"{type(exc).__name__}: {exc}")
            _fail(f"{name} — {type(exc).__name__}: {exc}")

    # SearchPage is where docker_status NameError lived — force all docker states.
    docker_states = [
        {"available": False, "running": False, "message": "missing"},
        {"available": True, "running": False, "message": "installed, not running"},
        {"available": True, "running": True, "message": "running"},
    ]
    virt = VirtualizationStatus(enabled=True, message="ok", detail="")
    for state in docker_states:
        label = f"SearchPage:{state.get('running') and 'running' or state.get('available') and 'available' or 'missing'}"
        try:
            with (
                patch.object(sw, "detect_virtualization_status", return_value=virt),
                patch.object(sw, "docker_status", return_value=state),
            ):
                page = sw.SearchPage()
                # Touch validate path lightly when checkbox absent/unchecked
                assert hasattr(page, "try_docker")
            report.add(f"wizard:{label}", True)
            _ok(label)
        except Exception as exc:
            report.add(f"wizard:{label}", False, f"{type(exc).__name__}: {exc}")
            _fail(f"{label} — {type(exc).__name__}: {exc}")

    # Simulate docker_status raising (should not crash)
    try:
        with (
            patch.object(sw, "detect_virtualization_status", return_value=virt),
            patch.object(sw, "docker_status", side_effect=RuntimeError("boom")),
        ):
            sw.SearchPage()
        report.add("wizard:SearchPage:docker_raises", True)
        _ok("SearchPage survives docker_status exception")
    except Exception as exc:
        report.add(
            "wizard:SearchPage:docker_raises",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        _fail(f"SearchPage docker raise — {type(exc).__name__}: {exc}")

    _ = app  # keep app alive for duration of checks


def check_search_bundle(report: Report) -> None:
    print("\n== Search bundle (dev-tree sources) ==")
    sys.path.insert(0, str(REPO_ROOT))
    from agent.aquila_runtime import search_bundle as sb

    for name in sb._SEARCH_FILES:
        src = sb._bundled_search_file(name)
        if src and src.is_file():
            report.add(f"bundle:{name}", True)
            _ok(f"{name} → {src}")
        else:
            report.add(f"bundle:{name}", False, "not found in bundle or repo root")
            _fail(f"{name} not resolvable from search_bundle")


def check_pytest(report: Report) -> None:
    print("\n== Packaged pytest subset ==")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *PACKAGED_PYTEST,
        "-q",
        "--tb=line",
    ]
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["AQUILA_WARMUP_ON_START"] = "0"
    env["AQUILA_SKIP_WARMUP"] = "1"
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (proc.stdout or "")[-800:]
    if proc.returncode == 0:
        report.add("pytest", True, tail.strip().splitlines()[-1] if tail.strip() else "ok")
        _ok(tail.strip().splitlines()[-1] if tail.strip() else "pytest ok")
    else:
        detail = (proc.stdout or "") + "\n" + (proc.stderr or "")
        report.add("pytest", False, detail[-1200:])
        _fail("pytest failed")
        print(detail[-1200:])


def check_shell_unicode(report: Report) -> None:
    print("\n== Shell Unicode (PowerShell / cmd footguns) ==")
    script = REPO_ROOT / "scripts" / "check-shell-unicode.py"
    if not script.is_file():
        report.add("unicode-scan", False, "scripts/check-shell-unicode.py missing")
        _fail("check-shell-unicode.py missing")
        return
    proc = subprocess.run(
        [sys.executable, str(script), "--quiet"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        report.add("unicode-scan", True)
        _ok(out.splitlines()[-1] if out else "no risky Unicode in shell scripts")
    else:
        report.add("unicode-scan", False, out[-800:])
        _fail("risky Unicode in .ps1/.bat/.cmd/.iss - run scripts/check-shell-unicode.ps1")
        if out:
            print(out[-800:])


def main() -> int:
    parser = argparse.ArgumentParser(description="Aquila packaged-install preflight")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip pytest (assets + imports + AST + wizard only)",
    )
    args = parser.parse_args()

    print("Aquila packaged preflight")
    print(f"Repo: {REPO_ROOT}")
    print(f"Python: {sys.executable}")

    report = Report()
    check_assets(report)
    check_imports(report)
    check_ast_names(report)
    check_search_bundle(report)
    check_wizard_pages(report)
    check_shell_unicode(report)
    if not args.quick:
        check_pytest(report)

    failed = report.failed
    print("\n== Summary ==")
    print(f"{len(report.results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
        print(
            "\nFix the failures above before running packaging/build-windows.ps1 "
            "(avoids a long compile for bugs we can catch in seconds)."
        )
        return 1
    print("\nPreflight clean — safe to compile when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
