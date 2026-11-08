#!/usr/bin/env python3
"""
Aquila AI - Live Recursive Evaluation and Trajectory Dissection Harness

Usage:
    # Single recipe test:
    python scripts/live_eval_harness.py --recipe fn_dev_implement --task "Create world clock script"

    # Suite test:
    python scripts/live_eval_harness.py --suite dev
    python scripts/live_eval_harness.py --suite research
    python scripts/live_eval_harness.py --suite all
"""

import argparse
import ast
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

SUITES = {
    "dev": [
        {
            "recipe": "code_smoke_file",
            "task": "Create a smoke test script smoke.py that prints 'smoke test ok' and verify",
        },
        {
            "recipe": "fn_dev_implement",
            "task": "Create an isolated python world clock script in the workspace virtual environment that prints UTC, New York, London, and Tokyo times, and verify execution",
        },
        {
            "recipe": "fn_dev_tdd",
            "task": "Create test_math_utils.py with pytest test cases for factorial and gcd, implement math_utils.py, and verify test suite passes",
        },
        {
            "recipe": "fn_dev_documentation",
            "task": "Analyze codebase architecture and generate comprehensive ARCHITECTURE.md document",
        },
        {
            "recipe": "fn_dev_dynamic",
            "task": "Implement a ping utility script that checks system health and verify execution",
        },
    ],
    "research": [
        {
            "recipe": "knowledge_smoke",
            "task": "Search knowledge base for architectural invariants and store summary fact",
        },
        {
            "recipe": "fn_research_full",
            "task": "Conduct comprehensive research on Context Condenser SAC strategy, record verified facts, and write research_report.md",
        },
        {
            "recipe": "fn_research_dynamic",
            "task": "Investigate GPU VRAM budgeting and tier configurations, record facts, and generate findings summary",
        },
        {
            "recipe": "fn_research_offline",
            "task": "Analyze local documentation and synthesize core system capabilities",
        },
        {
            "recipe": "fn_research_chat_light",
            "task": "Synthesize the main differences between llama.cpp CUDA and Ollama backends",
        },
    ],
    "writing": [
        {
            "recipe": "fn_writing_full",
            "task": "Generate outline, draft sections, and compile user guide manuscript into user_guide.md",
        },
        {
            "recipe": "fn_writing_dynamic",
            "task": "Draft technical release notes referencing codebase features into release_notes.md",
        },
        {
            "recipe": "fn_writing_sources",
            "task": "Draft a whitepaper on deterministic agent execution architectures with bibliography",
        },
    ],
    "learn": [
        {
            "recipe": "fn_learn_syllabus",
            "task": "Create a 4-week Modern C++20 syllabus with 3 quiz questions per module",
        },
        {
            "recipe": "fn_learn_syllabus_web",
            "task": "Create an AI agent architectures syllabus with interactive quiz questions",
        },
    ],
    "persona": [
        {
            "recipe": "fn_persona_build",
            "task": "Build an expert systems programming mentor persona named Ada with 800+ character depth and dialogue examples",
        },
        {
            "recipe": "fn_persona_lore",
            "task": "Load persona Ada, record worldbuilding lore facts for the Aquila universe, and complete recipe",
        },
    ],
}


def find_cli_binary(custom_path=None):
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))
    candidates.extend([
        Path("build/msvc-release-cuda/apps/aquila_cli/aquila_cli.exe"),
        Path("build/msvc-release-cuda/apps/aquila_cli/aquila.exe"),
        Path("build/msvc-release/apps/aquila_cli/aquila_cli.exe"),
        Path("build/msvc-release/apps/aquila_cli/aquila.exe"),
        Path("build/apps/aquila_cli/aquila_cli.exe"),
        Path("build/apps/aquila_cli/aquila.exe"),
    ])
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


class ArtifactUtilityVerifier:
    """Rigorous semantic and execution utility evaluation for generated artifacts."""

    @staticmethod
    def verify(recipe: str, task: str, workspace_dir: str) -> dict:
        ws = Path(workspace_dir).resolve()
        result = {
            "score": 100,
            "passed": True,
            "domain": "general",
            "findings": [],
            "deliverables": []
        }

        # Route by domain / recipe
        if any(dev_prefix in recipe for dev_prefix in ["code_", "dev_"]):
            ArtifactUtilityVerifier._verify_dev_deliverable(recipe, task, ws, result)
        elif "research" in recipe or "knowledge" in recipe:
            ArtifactUtilityVerifier._verify_research_deliverable(recipe, task, ws, result)
        elif "writing" in recipe:
            ArtifactUtilityVerifier._verify_writing_deliverable(recipe, task, ws, result)
        elif "learn" in recipe:
            ArtifactUtilityVerifier._verify_learn_deliverable(recipe, task, ws, result)
        elif "persona" in recipe:
            ArtifactUtilityVerifier._verify_persona_deliverable(recipe, task, ws, result)
        else:
            result["findings"].append("Generic recipe: verified execution exit gate.")

        result["score"] = max(0, min(100, result["score"]))
        if result["score"] < 60:
            result["passed"] = False
        return result

    @staticmethod
    def _verify_dev_deliverable(recipe, task, ws, result):
        result["domain"] = "dev"
        candidates = []
        for p in ws.rglob("*.py"):
            rel = str(p.relative_to(ws))
            if any(skip in rel for skip in [".venv", "build", "tests", "test_"]):
                continue
            candidates.append(p)

        if not candidates:
            smoke = ws / "harness_smoke.py"
            if smoke.exists():
                candidates.append(smoke)

        if not candidates:
            result["score"] = 0
            result["passed"] = False
            result["findings"].append("❌ No non-test Python implementation script found in workspace.")
            return

        target_script = max(candidates, key=lambda f: f.stat().st_mtime)
        result["deliverables"].append(str(target_script.relative_to(ws)))

        code = target_script.read_text(encoding="utf-8", errors="ignore")
        if len(code.strip()) < 25:
            result["score"] -= 60
            result["passed"] = False
            result["findings"].append(f"❌ Script {target_script.name} is too short or empty ({len(code)} bytes).")
            return

        try:
            tree = ast.parse(code)
            result["findings"].append(f"✓ AST validation passed for {target_script.name}.")
        except SyntaxError as e:
            result["score"] = 0
            result["passed"] = False
            result["findings"].append(f"❌ SyntaxError in {target_script.name}: {e}")
            return

        stub_tokens = ["pass", "TODO", "NotImplementedError"]
        for st in stub_tokens:
            if re.search(rf"\b{re.escape(st)}\b", code):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Pass) or (isinstance(node, ast.Raise) and "NotImplementedError" in ast.dump(node)):
                        result["score"] -= 40
                        result["passed"] = False
                        result["findings"].append(f"❌ Script contains unexpanded stub body ({st}).")
                        break

        py_exe = sys.executable
        venv_py = ws / ".venv" / "Scripts" / "python.exe"
        if venv_py.exists():
            py_exe = str(venv_py)

        try:
            exec_res = subprocess.run([py_exe, str(target_script)], cwd=str(ws), capture_output=True, text=True, timeout=30)
            if exec_res.returncode != 0:
                result["score"] -= 50
                result["passed"] = False
                result["findings"].append(f"❌ Script crashed with exit code {exec_res.returncode}:\n{exec_res.stderr[:300]}")
            else:
                stdout = exec_res.stdout.strip()
                if not stdout:
                    result["score"] -= 30
                    result["passed"] = False
                    result["findings"].append("❌ Script ran cleanly but produced zero stdout.")
                else:
                    preview = stdout[:80].replace("\n", " ")
                    result["findings"].append(f"✓ Script executed cleanly with exit code 0. Stdout preview: {preview}...")
                    if "world clock" in task.lower():
                        cities = ["UTC", "New York", "London", "Tokyo"]
                        missing = [c for c in cities if c.lower() not in stdout.lower()]
                        if missing:
                            result["score"] -= 20
                            result["findings"].append(f"⚠️ World clock output missing timezones: {', '.join(missing)}")
                        else:
                            result["findings"].append("✓ World clock output includes all requested timezones (UTC, New York, London, Tokyo).")
        except subprocess.TimeoutExpired:
            result["score"] -= 60
            result["passed"] = False
            result["findings"].append("❌ Script execution timed out after 30s.")
        except Exception as e:
            result["score"] -= 40
            result["findings"].append(f"⚠️ Could not execute script: {e}")

    @staticmethod
    def _verify_research_deliverable(recipe, task, ws, result):
        result["domain"] = "research"
        report_files = list(ws.glob("*.md"))
        valid_reports = [f for f in report_files if "report" in f.name.lower() or "research" in f.name.lower() or f.name == "research_report.md"]

        if not valid_reports:
            if report_files:
                valid_reports = report_files
            else:
                result["score"] -= 50
                result["passed"] = False
                result["findings"].append("❌ No research report markdown file found in workspace.")
                return

        target_report = max(valid_reports, key=lambda f: f.stat().st_mtime)
        result["deliverables"].append(str(target_report.relative_to(ws)))
        text = target_report.read_text(encoding="utf-8", errors="ignore")

        if len(text) < 350:
            result["score"] -= 40
            result["passed"] = False
            result["findings"].append(f"❌ Report is too shallow ({len(text)} chars, minimum 350 chars required).")
        else:
            result["findings"].append(f"✓ Report has substantive depth ({len(text)} chars).")

        headings = [line for line in text.splitlines() if line.startswith("#")]
        if len(headings) < 2:
            result["score"] -= 20
            result["passed"] = False
            result["findings"].append("❌ Report lacks structured markdown section headers.")
        else:
            result["findings"].append(f"✓ Report contains {len(headings)} structured section headers.")

        has_citations = ("[" in text and "]" in text)
        if not has_citations:
            result["score"] -= 30
            result["passed"] = False
            result["findings"].append("❌ Report lacks citations or grounded references ([1] or [Source]).")
        else:
            result["findings"].append("✓ Report contains grounded citation markers.")

        db_path = ws / ".aquila" / "knowledge.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM facts")
                count = cursor.fetchone()[0]
                conn.close()
                if count > 0:
                    result["findings"].append(f"✓ SQLite FactStore contains {count} recorded facts.")
                else:
                    result["score"] -= 20
                    result["findings"].append("⚠️ SQLite FactStore has 0 recorded facts.")
            except Exception as e:
                result["findings"].append(f"⚠️ SQLite check error: {e}")

    @staticmethod
    def _verify_writing_deliverable(recipe, task, ws, result):
        result["domain"] = "writing"
        drafts_dir = ws / "Agent-Drafts"
        candidates = list(drafts_dir.glob("*.md")) if drafts_dir.exists() else []
        if not candidates:
            candidates = [f for f in ws.glob("*.md") if f.name != "README.md"]

        if not candidates:
            result["score"] = 0
            result["passed"] = False
            result["findings"].append("❌ No manuscript found in Agent-Drafts/ or workspace.")
            return

        target_doc = max(candidates, key=lambda f: f.stat().st_mtime)
        result["deliverables"].append(str(target_doc.relative_to(ws)))
        text = target_doc.read_text(encoding="utf-8", errors="ignore")
        words = len(text.split())

        if words < 250:
            result["score"] -= 40
            result["passed"] = False
            result["findings"].append(f"❌ Manuscript is too short ({words} words, minimum 250 required).")
        else:
            result["findings"].append(f"✓ Manuscript meets word count requirements ({words} words).")

        placeholders = re.findall(r"\b(TODO|Lorem ipsum|TBD|placeholder)\b", text, re.IGNORECASE)
        if placeholders:
            result["score"] -= 40
            result["passed"] = False
            result["findings"].append(f"❌ Manuscript contains unexpanded placeholders: {set(placeholders)}.")
        else:
            result["findings"].append("✓ Zero placeholder tokens detected.")

    @staticmethod
    def _verify_learn_deliverable(recipe, task, ws, result):
        result["domain"] = "learn"
        syllabus_files = list(ws.rglob("syllabus.json"))
        if not syllabus_files:
            result["score"] = 0
            result["passed"] = False
            result["findings"].append("❌ No syllabus.json found in Agent-Learn/ hierarchy.")
            return

        target_syl = max(syllabus_files, key=lambda f: f.stat().st_mtime)
        result["deliverables"].append(str(target_syl.relative_to(ws)))
        try:
            with open(target_syl, "r", encoding="utf-8") as f:
                syl_data = json.load(f)
            nodes = syl_data.get("nodes", [])
            if len(nodes) < 8:
                result["score"] -= 40
                result["passed"] = False
                result["findings"].append(f"❌ Syllabus has only {len(nodes)} units (minimum 8 required).")
            else:
                result["findings"].append(f"✓ Syllabus contains {len(nodes)} learning units.")

            children = [n for n in nodes if n.get("parent_id")]
            if len(children) < 5:
                result["score"] -= 30
                result["passed"] = False
                result["findings"].append(f"❌ Syllabus has only {len(children)} sub-units (minimum 5 required).")
            else:
                result["findings"].append(f"✓ Hierarchical tree contains {len(children)} sub-units.")

            titles = [n.get("title", "").strip().lower() for n in nodes if n.get("title")]
            if len(set(titles)) < len(titles):
                result["score"] -= 30
                result["passed"] = False
                result["findings"].append("❌ Syllabus contains duplicate unit titles.")
            else:
                result["findings"].append("✓ All learning unit titles are unique and pedagogically distinct.")
        except Exception as e:
            result["score"] = 0
            result["passed"] = False
            result["findings"].append(f"❌ Failed to parse syllabus.json: {e}")

    @staticmethod
    def _verify_persona_deliverable(recipe, task, ws, result):
        result["domain"] = "persona"
        init_files = list(ws.rglob("initialization.md"))
        if not init_files:
            result["score"] = 0
            result["passed"] = False
            result["findings"].append("❌ No initialization.md persona bible found in Agent-Personas/.")
            return

        target_init = max(init_files, key=lambda f: f.stat().st_mtime)
        result["deliverables"].append(str(target_init.relative_to(ws)))
        text = target_init.read_text(encoding="utf-8", errors="ignore")

        if len(text) < 800:
            result["score"] -= 40
            result["passed"] = False
            result["findings"].append(f"❌ Persona bible is too brief ({len(text)} chars, minimum 800 chars required).")
        else:
            result["findings"].append(f"✓ Persona initialization meets depth requirements ({len(text)} chars).")

        headings = [line for line in text.splitlines() if line.startswith("#")]
        if len(headings) < 2:
            result["score"] -= 20
            result["passed"] = False
            result["findings"].append("❌ Persona initialization lacks structured lore headers.")
        else:
            result["findings"].append(f"✓ Persona initialization contains {len(headings)} structured sections.")

        leakage = re.findall(r"\b(as an AI language model|as an AI assistant|I am an artificial intelligence|I am an AI|I do not have feelings|I cannot fulfill this request)\b", text, re.IGNORECASE)
        if leakage:
            result["score"] -= 50
            result["passed"] = False
            result["findings"].append(f"❌ Assistant leakage detected: {set(leakage)}.")
        else:
            result["findings"].append("✓ Passed anti-assistant leakage screening (pure in-character immersion).")


def run_single_eval(bin_path, recipe, task, workspace, backend, model, tier, report_path):
    cmd = [
        str(bin_path),
        "eval",
        "--live",
        "--recipe", recipe,
        "--task", task,
        "--workspace", str(Path(workspace).resolve()),
        "--backend", backend,
        "--model", model,
        "--tier", tier,
        "--report", str(Path(report_path).resolve())
    ]

    print("\n" + "=" * 70)
    print(f"RUNNING LIVE EVAL: {recipe}")
    print(f"Task: {task}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 70)

    start_time = time.time()
    rep_path_obj = Path(report_path)
    if rep_path_obj.exists():
        try:
            rep_path_obj.unlink()
        except Exception:
            pass

    try:
        proc = subprocess.run(cmd, timeout=600)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] Evaluation timed out after 600s for recipe {recipe}", file=sys.stderr)
        returncode = -1
    elapsed = time.time() - start_time

    report = {}
    report_file = Path(report_path)
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception as e:
            print(f"[WARN] Failed to parse report file {report_file}: {e}")

    # Evaluate substantive artifact utility
    utility = ArtifactUtilityVerifier.verify(recipe, task, workspace)
    overall_passed = (returncode == 0 and report.get("success", False) and utility.get("passed", False))

    return {
        "recipe": recipe,
        "task": task,
        "returncode": returncode,
        "elapsed_seconds": round(elapsed, 2),
        "report": report,
        "utility": utility,
        "overall_passed": overall_passed
    }


def dissect_and_print_autopsy(result):
    report = result.get("report", {})
    utility = result.get("utility", {})
    recipe = result.get("recipe", "unknown")
    engine_success = report.get("success", False)
    utility_success = utility.get("passed", False)
    overall_passed = result.get("overall_passed", False)
    turns = report.get("turns_count", 0)
    metrics = report.get("metrics", {})
    failed_acts = metrics.get("failed_actions", 0)
    repeats = metrics.get("repeated_actions", 0)
    halluc_mods = metrics.get("hallucinated_modules", 0)
    unexp_acts = metrics.get("unexposed_actions", 0)
    score = utility.get("score", 0)

    print("\n" + "-" * 70)
    print(f"AUTOPSY REPORT: {recipe}")
    print("-" * 70)
    if overall_passed:
        status_label = "PASSED ✓ (Engine & Utility Verified)"
    elif engine_success and not utility_success:
        status_label = "FAILED ✗ (Soft Utility Error)"
    else:
        status_label = "FAILED ✗ (Engine Execution)"

    print(f"Status:               {status_label}")
    print(f"Exit Gate / Output:   {report.get('completion_output', '(none)')}")
    print(f"Elapsed Time:         {result.get('elapsed_seconds')}s")
    print(f"Total Turns:          {turns}")
    print(f"Engine Metrics:       Fails: {failed_acts} | Repeats: {repeats} | Hallucinated Mods: {halluc_mods} | Unexposed Acts: {unexp_acts}")
    print(f"Artifact Utility:     Score: {score}/100 ({'SATISFIED' if utility_success else 'DEFICIENT'}) | Domain: {utility.get('domain', 'general')}")
    if utility.get("deliverables"):
        print(f"Deliverables:         {', '.join(utility.get('deliverables', []))}")

    if utility.get("findings"):
        print("\nSubstance & Utility Assessment:")
        for finding in utility["findings"]:
            print(f"  {finding}")

    trajectory = report.get("trajectory", [])
    if trajectory:
        print("\nTurn-by-Turn Dissection:")
        for t in trajectory:
            t_num = t.get("turn", 0)
            st = "✓" if t.get("success") else "✗"
            mod = t.get("module", "")
            act = t.get("action", "")
            thought = t.get("thought", "").strip()
            if len(thought) > 75:
                thought = thought[:72] + "..."
            flags = []
            if t.get("repeated"): flags.append("REPEAT")
            if t.get("unloaded_module"): flags.append("UNLOADED_MOD")
            if t.get("unexposed_action"): flags.append("UNEXPOSED_ACT")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  [{t_num:02d}] {st} {mod}::{act}{flag_str} | Thought: {thought}")

    # Recursive Guidance Diagnosis
    print("\nDiagnosis & Recursive Adjustments:")
    if overall_passed:
        print("  ✓ Task completed cleanly, satisfying exit gate and quality criteria.")
    else:
        if engine_success and not utility_success:
            print("  ⚠️ Soft utility failure: Deliverable lacked required substance, depth, or functional execution.")
        if halluc_mods > 0:
            print("  ⚠️ Model hallucinated unloaded modules. Enforce module enum constraint.")
        if repeats >= 2:
            print("  ⚠️ Repetition detected. Trigger corrective guidance or tighten loop breaker.")
        if failed_acts > 0:
            print("  ⚠️ Tool action failed. Check tool argument schema and execution environment.")
        if not report.get("completion_output"):
            print("  ⚠️ Exit gate refused or was not invoked before turn limit.")
    print("-" * 70)


def main():
    parser = argparse.ArgumentParser(description="Aquila Live Evaluation & Thought Scrutiny Harness")
    parser.add_argument("--suite", choices=["dev", "research", "writing", "learn", "persona", "all"],
                        help="Run an entire recipe test suite battery")
    parser.add_argument("--recipe", default="fn_dev_implement", help="Single recipe ID to evaluate")
    parser.add_argument("--task", default="",
                        help="Task prompt for single recipe eval (defaults to suite catalog task)")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    parser.add_argument("--backend", default="llama", choices=["llama", "ollama"], help="Inference backend")
    parser.add_argument("--model", default="D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
                        help="Model path (GGUF) or model name")
    parser.add_argument("--tier", default="gpu", choices=["cpu", "gpu"], help="Hardware tier profile")
    parser.add_argument("--report", default="eval_report.json", help="Path for output JSON dissection report")
    parser.add_argument("--bin", help="Explicit path to aquila_cli executable")
    args = parser.parse_args()

    bin_path = find_cli_binary(args.bin)
    if not bin_path:
        print("[ERROR] Could not find aquila_cli binary. Please build the project first.", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("AQUILA AI - RECURSIVE LIVE EVALUATION HARNESS")
    print(f"Binary:   {bin_path}")
    print(f"Backend:  {args.backend} ({args.model})")
    print(f"Tier:     {args.tier}")
    print("=" * 70)

    if args.suite:
        suites_to_run = list(SUITES.keys()) if args.suite == "all" else [args.suite]
        battery_results = []
        reports_dir = Path("eval_reports")
        reports_dir.mkdir(exist_ok=True)

        for s_name in suites_to_run:
            print(f"\n>>> EXECUTING SUITE: {s_name.upper()} ({len(SUITES[s_name])} recipes) <<<")
            for item in SUITES[s_name]:
                rec = item["recipe"]
                tsk = item["task"]
                rep_path = reports_dir / f"eval_{rec}.json"
                res = run_single_eval(bin_path, rec, tsk, args.workspace, args.backend, args.model, args.tier, str(rep_path))
                dissect_and_print_autopsy(res)
                battery_results.append(res)

        # Summary Table
        print("\n" + "=" * 90)
        print("BATTERY EVALUATION MATRIX SUMMARY")
        print("=" * 90)
        print(f"{'Recipe':<24} {'Status':<10} {'Utility':<10} {'Score':<8} {'Turns':<8} {'Fails':<8} {'Repeats':<8} {'Time':<8}")
        print("-" * 90)
        passed_count = 0
        for r in battery_results:
            rep = r.get("report", {})
            ut = r.get("utility", {})
            metrics = rep.get("metrics", {})
            overall = r.get("overall_passed", False)
            if overall: passed_count += 1
            st_str = "PASSED" if overall else "FAILED"
            ut_str = "SATISFIED" if ut.get("passed") else "DEFICIENT"
            score_str = f"{ut.get('score', 0)}/100"
            turns = rep.get("turns_count", 0)
            fails = metrics.get("failed_actions", 0)
            reps = metrics.get("repeated_actions", 0)
            elapsed = f"{r.get('elapsed_seconds')}s"
            print(f"{r['recipe']:<24} {st_str:<10} {ut_str:<10} {score_str:<8} {turns:<8} {fails:<8} {reps:<8} {elapsed:<8}")

        print("-" * 90)
        total = len(battery_results)
        print(f"Summary: {passed_count}/{total} recipes PASSED ({(passed_count/total)*100:.1f}%)")
        print("=" * 90)

        summary_file = Path("eval_battery_summary.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "suite": args.suite,
                "passed": passed_count,
                "total": total,
                "results": battery_results
            }, f, indent=2)
        print(f"Cumulative summary report written to {summary_file}")
        sys.exit(0 if passed_count == total else 1)

    else:
        task = args.task
        if not task:
            for suite_list in SUITES.values():
                for item in suite_list:
                    if item["recipe"] == args.recipe:
                        task = item["task"]
                        break
                if task:
                    break
        if not task:
            task = "Execute recipe autonomously to completion"
        res = run_single_eval(bin_path, args.recipe, task, args.workspace, args.backend, args.model, args.tier, args.report)
        dissect_and_print_autopsy(res)
        sys.exit(0 if res.get("overall_passed") else 1)


if __name__ == "__main__":
    main()
