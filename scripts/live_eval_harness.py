#!/usr/bin/env python3
"""
Aquila AI - Live Recursive Evaluation and Trajectory Dissection Harness
Usage:
    python scripts/live_eval_harness.py [--recipe fn_dev_implement] [--task "..."] [--backend llama] [--model <path>]
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_harness():
    parser = argparse.ArgumentParser(description="Aquila Live Evaluation & Thought Scrutiny Harness")
    parser.add_argument("--recipe", default="fn_dev_implement", help="Recipe ID to evaluate")
    parser.add_argument("--task", default="Create a world clock python script and verify execution", help="Task prompt")
    parser.add_argument("--workspace", default=".", help="Workspace directory")
    parser.add_argument("--backend", default="llama", choices=["llama", "ollama"], help="Inference backend")
    parser.add_argument("--model", default="D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf", help="Model path / name")
    parser.add_argument("--tier", default="gpu", choices=["cpu", "gpu"], help="Hardware tier")
    parser.add_argument("--report", default="eval_report.json", help="Output JSON dissection report")
    parser.add_argument("--bin", default="build/msvc-release/apps/aquila_cli/aquila.exe", help="Path to aquila CLI executable")
    args = parser.parse_args()

    bin_path = Path(args.bin).resolve()
    if not bin_path.exists():
        # Fallback search
        alt = Path("build/msvc-release/apps/aquila_cli/aquila.exe").resolve()
        if alt.exists():
            bin_path = alt
        else:
            print(f"[ERROR] Aquila CLI binary not found at {bin_path}", file=sys.stderr)
            sys.exit(1)

    cmd = [
        str(bin_path),
        "eval",
        "--live",
        "--recipe", args.recipe,
        "--task", args.task,
        "--workspace", str(Path(args.workspace).resolve()),
        "--backend", args.backend,
        "--model", args.model,
        "--tier", args.tier,
        "--report", args.report
    ]

    print("=" * 60)
    print("AQUILA LIVE RECURSIVE EVALUATION HARNESS")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)

    proc = subprocess.run(cmd)
    
    report_file = Path(args.report)
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report = json.load(f)
            
            print("\n" + "=" * 60)
            print("AUTOPSY SUMMARY & RECURSIVE RECOMMENDATIONS")
            print("=" * 60)
            print(f"Status:        {'PASSED' if report.get('success') else 'FAILED'}")
            print(f"Total Turns:   {report.get('turns_count', 0)}")
            metrics = report.get("metrics", {})
            print(f"Failed Calls:  {metrics.get('failed_actions', 0)}")
            print(f"Repetitions:   {metrics.get('repeated_actions', 0)}")
            print(f"Hallucinations:{metrics.get('hallucinated_modules', 0)}")

            trajectory = report.get("trajectory", [])
            print("\nTrajectory Breakdown:")
            for turn in trajectory:
                t_num = turn.get("turn")
                succ = "✓" if turn.get("success") else "✗"
                mod = turn.get("module")
                act = turn.get("action")
                thought = turn.get("thought", "")
                if len(thought) > 80:
                    thought = thought[:77] + "..."
                print(f"  Turn {t_num:02d} [{succ}] {mod}::{act} | Thought: {thought}")

            # Recursive advice
            print("\nRecursive Analysis & Adjustments:")
            if metrics.get("repeated_actions", 0) > 0:
                print("  [ADJUSTMENT] Model exhibited tool repetition. Check circuit breaker and corrective guidance.")
            if metrics.get("hallucinated_modules", 0) > 0:
                print("  [ADJUSTMENT] Model hallucinated unloaded modules. Verify GBNF schema enum constraint.")
            if not report.get("success"):
                print("  [ADJUSTMENT] Exit gate failed. Inspect exit hook or completion requirements in recipe.")
            else:
                print("  [SUCCESS] All milestones satisfied and exit gate verified!")
            print("=" * 60)
        except Exception as e:
            print(f"[WARN] Failed to parse report {report_file}: {e}")

    sys.exit(proc.returncode)


if __name__ == "__main__":
    run_harness()

