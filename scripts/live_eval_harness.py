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
import json
import os
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
        Path("build/msvc-release/apps/aquila_cli/aquila_cli.exe"),
        Path("build/msvc-release/apps/aquila_cli/aquila.exe"),
        Path("build/apps/aquila_cli/aquila_cli.exe"),
        Path("build/apps/aquila_cli/aquila.exe"),
    ])
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


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

    return {
        "recipe": recipe,
        "task": task,
        "returncode": returncode,
        "elapsed_seconds": round(elapsed, 2),
        "report": report
    }


def dissect_and_print_autopsy(result):
    report = result.get("report", {})
    recipe = result.get("recipe", "unknown")
    success = report.get("success", False)
    turns = report.get("turns_count", 0)
    metrics = report.get("metrics", {})
    failed_acts = metrics.get("failed_actions", 0)
    repeats = metrics.get("repeated_actions", 0)
    halluc_mods = metrics.get("hallucinated_modules", 0)
    unexp_acts = metrics.get("unexposed_actions", 0)

    print("\n" + "-" * 70)
    print(f"AUTOPSY REPORT: {recipe}")
    print("-" * 70)
    print(f"Status:               {'PASSED ✓' if success else 'FAILED ✗'}")
    print(f"Exit Gate / Output:   {report.get('completion_output', '(none)')}")
    print(f"Elapsed Time:         {result.get('elapsed_seconds')}s")
    print(f"Total Turns:          {turns}")
    print(f"Metrics:              Fails: {failed_acts} | Repeats: {repeats} | Hallucinated Mods: {halluc_mods} | Unexposed Acts: {unexp_acts}")

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
    if success:
        print("  ✓ Task completed cleanly, satisfying exit gate and quality criteria.")
    else:
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
        print("\n" + "=" * 80)
        print("BATTERY EVALUATION MATRIX SUMMARY")
        print("=" * 80)
        print(f"{'Recipe':<25} {'Status':<10} {'Turns':<8} {'Fails':<8} {'Repeats':<10} {'Halluc':<8} {'Time':<8}")
        print("-" * 80)
        passed_count = 0
        for r in battery_results:
            rep = r.get("report", {})
            metrics = rep.get("metrics", {})
            succ = rep.get("success", False)
            if succ: passed_count += 1
            st_str = "PASSED" if succ else "FAILED"
            turns = rep.get("turns_count", 0)
            fails = metrics.get("failed_actions", 0)
            reps = metrics.get("repeated_actions", 0)
            hall = metrics.get("hallucinated_modules", 0)
            elapsed = f"{r.get('elapsed_seconds')}s"
            print(f"{r['recipe']:<25} {st_str:<10} {turns:<8} {fails:<8} {reps:<10} {hall:<8} {elapsed:<8}")

        print("-" * 80)
        total = len(battery_results)
        print(f"Summary: {passed_count}/{total} recipes PASSED ({(passed_count/total)*100:.1f}%)")
        print("=" * 80)

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
        sys.exit(0 if res.get("report", {}).get("success") else 1)


if __name__ == "__main__":
    main()
