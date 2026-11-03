"""Per-task artifact folders: plan, ledger, walkthrough, reflection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.storage import agent_data_path

PLAN_REVIEW_SENTINEL = "__AQUILA_AWAITING_PLAN_APPROVAL__"


def extract_plan_review_result(text: str) -> str | None:
    """Return the plan-review sentinel line if present anywhere in a worker result."""
    if not text:
        return None
    if text.startswith(PLAN_REVIEW_SENTINEL):
        return text.splitlines()[0].strip()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(PLAN_REVIEW_SENTINEL):
            return stripped
    return None


def task_bundle_dir(task_name: str, mode: str) -> Path:
    """Root folder for all artifacts for one task."""
    if mode == "research":
        base = agent_data_path("Agent-Plans")
    else:
        base = agent_data_path("Agent-Tasks")
    root = base / task_name
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    return root


def legacy_ledger_path(task_name: str, mode: str) -> Path:
    if mode == "research":
        return agent_data_path("Agent-Plans", f"{task_name}.json")
    return agent_data_path("Agent-Tasks", f"{task_name}.json")


def resolve_ledger_file(task_name: str, mode: str) -> str:
    """
    Resolve the active ledger path.

    Back-compat: if a legacy flat file exists (`Agent-Plans/<name>.json` or
    `Agent-Tasks/<name>.json`), keep using it as the source of truth so older
    tests/tools that read that path still work.
    """
    legacy = legacy_ledger_path(task_name, mode)
    if legacy.exists():
        return str(legacy)
    bundle = task_bundle_dir(task_name, mode)
    ledger = bundle / "ledger.json"
    return str(ledger)


def plan_json_path(task_name: str, mode: str) -> Path:
    return task_bundle_dir(task_name, mode) / "plan.json"


def plan_md_path(task_name: str, mode: str) -> Path:
    return task_bundle_dir(task_name, mode) / "plan.md"


def implementation_plan_md_path(task_name: str, mode: str) -> Path:
    return task_bundle_dir(task_name, mode) / "implementation_plan.md"


def walkthrough_md_path(task_name: str, mode: str) -> Path:
    return task_bundle_dir(task_name, mode) / "walkthrough.md"


def reflection_json_path(task_name: str, mode: str) -> Path:
    return task_bundle_dir(task_name, mode) / "reflection.json"


def run_state_path(task_name: str, mode: str) -> Path:
    return task_bundle_dir(task_name, mode) / "run_state.json"


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_plan_dict(task_name: str, mode: str) -> dict[str, Any]:
    path = plan_json_path(task_name, mode)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    ledger = resolve_ledger_file(task_name, mode)
    if Path(ledger).exists():
        return json.loads(Path(ledger).read_text(encoding="utf-8"))
    return {}


def write_plan_artifact(
    task_name: str,
    mode: str,
    plan: dict[str, Any],
    *,
    user_request: str = "",
) -> tuple[str, str]:
    """Persist plan.json and rendered plan.md. Returns (json_path, md_path)."""
    bundle = task_bundle_dir(task_name, mode)
    plan = dict(plan)
    if user_request and not plan.get("user_goal"):
        if mode in ("learn_syllabus_build", "character_build", "writing"):
            from agent.core.plan_descriptions import short_topic_for_plan

            title = short_topic_for_plan(user_request)
            if mode == "learn_syllabus_build":
                plan["user_goal"] = f"Build a learning syllabus for course '{title}'."
            elif mode == "character_build":
                plan["user_goal"] = f"Build a roleplay persona: {title}."
            else:
                plan["user_goal"] = f"Write: {title}."
        else:
            plan["user_goal"] = user_request.strip()[:2000]
    elif plan.get("user_goal") and mode in ("learn_syllabus_build", "character_build", "writing"):
        goal = str(plan["user_goal"])
        if any(
            tok in goal.lower()
            for tok in (
                "write_syllabus_file",
                "web_search",
                "save_research_note",
                "course_id=",
                "steps: ingest",
            )
        ):
            from agent.core.plan_descriptions import short_topic_for_plan

            title = short_topic_for_plan(goal or user_request)
            if mode == "learn_syllabus_build":
                plan["user_goal"] = f"Build a learning syllabus for course '{title}'."
            elif mode == "character_build":
                plan["user_goal"] = f"Build a roleplay persona: {title}."
            else:
                plan["user_goal"] = f"Write: {title}."
    if "approval_status" not in plan:
        plan["approval_status"] = "draft"
    if "plan_version" not in plan:
        plan["plan_version"] = 1

    from agent.core.implementation_plan import (
        ensure_implementation_block,
        render_implementation_plan_markdown,
        should_write_living_plan,
    )

    if should_write_living_plan(plan, mode):
        ensure_implementation_block(plan, mode, user_request=user_request)

    json_path = bundle / "plan.json"
    json_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    md_path = bundle / "plan.md"
    md_path.write_text(render_plan_markdown(plan), encoding="utf-8")

    if should_write_living_plan(plan, mode):
        impl_md = render_implementation_plan_markdown(plan, mode=mode)
        if impl_md.strip():
            (bundle / "implementation_plan.md").write_text(impl_md, encoding="utf-8")

    ledger_path = bundle / "ledger.json"
    ledger_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    legacy = legacy_ledger_path(task_name, mode)
    legacy.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    return str(json_path), str(md_path)


def render_plan_markdown(plan: dict[str, Any]) -> str:
    lines: list[str] = ["# Task Plan", ""]
    goal = (plan.get("user_goal") or "").strip()
    if goal:
        lines.extend(["## Goal", goal, ""])
    approach = (plan.get("approach_summary") or "").strip()
    if approach:
        lines.extend(["## Approach", approach, ""])
    recipe = (plan.get("capability_recipe") or "").strip()
    if recipe:
        lines.extend(["## Capability recipe", f"`{recipe}`", ""])
    milestones = plan.get("milestones") or []
    if milestones:
        lines.append("## Milestones")
        for m in milestones:
            if isinstance(m, dict):
                label = m.get("label", m.get("id", "milestone"))
                crit = m.get("success_criteria", "")
                status = m.get("status", "pending")
                lines.append(f"- **{label}** ({status})")
                if crit:
                    lines.append(f"  - Success: {crit}")
        lines.append("")
    assumptions = plan.get("assumptions") or []
    if assumptions:
        lines.extend(["## Assumptions", *[f"- {a}" for a in assumptions], ""])
    risks = plan.get("risks") or []
    if risks:
        lines.extend(["## Risks", *[f"- {r}" for r in risks], ""])
    lines.append("## Steps")
    for i, step in enumerate(plan.get("steps") or [], 1):
        if not isinstance(step, dict):
            continue
        kind = step.get("step_kind", "work")
        desc = step.get("description", "")
        status = step.get("status", "pending")
        cap_id = step.get("capability_id", "")
        cap_suffix = f" · `{cap_id}`" if cap_id else ""
        lines.append(f"{i}. **[{kind}]** {desc}{cap_suffix} _({status})_")
    version = plan.get("plan_version", 1)
    approval = plan.get("approval_status", "draft")
    lines.extend(["", f"_Plan v{version} · status: {approval}_"])
    return "\n".join(lines)


def render_walkthrough_markdown(wt: dict[str, Any], *, task_name: str = "") -> str:
    lines: list[str] = [f"# Walkthrough: {task_name}" if task_name else "# Walkthrough", ""]
    summary = (wt.get("summary") or "").strip()
    if summary:
        lines.extend(["## Summary", summary, ""])
    what = wt.get("what_we_did") or []
    if what:
        lines.append("## What we did")
        lines.extend(f"- {x}" for x in what)
        lines.append("")
    why = (wt.get("why_those_choices") or "").strip()
    if why:
        lines.extend(["## Why those choices", why, ""])
    verify = wt.get("how_to_verify") or []
    if verify:
        lines.append("## How to verify")
        lines.extend(f"- {x}" for x in verify)
        lines.append("")
    files = wt.get("files_changed") or []
    if files:
        lines.append("## Files changed")
        lines.extend(f"- `{f}`" for f in files)
        lines.append("")
    open_q = wt.get("open_questions") or []
    if open_q:
        lines.append("## Open questions")
        lines.extend(f"- {q}" for q in open_q)
        lines.append("")
    lessons = wt.get("lessons_learned") or []
    if lessons:
        lines.append("## Lessons learned")
        lines.extend(f"- {l}" for l in lessons)
        lines.append("")
    return "\n".join(lines)


def write_walkthrough_artifact(
    task_name: str,
    mode: str,
    walkthrough: dict[str, Any],
) -> tuple[str, str]:
    bundle = task_bundle_dir(task_name, mode)
    refl_path = bundle / "reflection.json"
    refl_path.write_text(json.dumps(walkthrough, indent=2), encoding="utf-8")
    md_path = bundle / "walkthrough.md"
    md_path.write_text(
        render_walkthrough_markdown(walkthrough, task_name=task_name),
        encoding="utf-8",
    )
    return str(md_path), str(refl_path)


def approve_plan(task_name: str, mode: str) -> dict[str, Any]:
    plan = read_plan_dict(task_name, mode)
    plan["approval_status"] = "approved"
    plan["status"] = "in_progress"
    write_plan_artifact(task_name, mode, plan)
    return plan


def plan_needs_review(
    plan: dict[str, Any],
    *,
    micro_plan: bool = False,
    user_request: str = "",
    mode: str = "",
) -> bool:
    from agent.core.loop_settings import plan_auto_approve_micro_enabled, plan_review_enabled

    mode_norm = (mode or plan.get("mode") or "").strip().lower()
    if mode_norm == "code":
        return False  # DEAD: code uses code_agent — never plan review
    if not plan_review_enabled():
        return False
    if micro_plan and plan_auto_approve_micro_enabled():
        return False
    if micro_plan:
        try:
            from agent.core.code_scaffolds import is_habit_tracker_goal

            goal = (user_request or plan.get("user_goal") or "").strip()
            if is_habit_tracker_goal(goal):
                return False
        except Exception:
            pass
    if (plan.get("approval_status") or "").lower() == "approved":
        return False
    return True


def enrich_plan_from_ledger(
    plan_json: str,
    *,
    user_request: str,
    mode: str,
    offline_research: bool = False,
    capability_research: bool = False,
) -> dict[str, Any]:
    """Parse ledger JSON and add artifact metadata + default milestones."""
    from agent.parser.structured_schema import MilestoneModel, TaskPlanModel
    from agent.core.loop_objectives import milestone_hints_for_mode

    try:
        raw = json.loads(plan_json)
    except json.JSONDecodeError:
        raw = {"steps": [], "status": "in_progress", "current_step_index": 0}

    try:
        model = TaskPlanModel.model_validate(raw)
        data = model.model_dump(mode="python")
    except Exception:
        data = raw if isinstance(raw, dict) else {}

    if not data.get("user_goal"):
        if mode in ("learn_syllabus_build", "character_build", "writing"):
            from agent.core.plan_descriptions import short_topic_for_plan

            title = short_topic_for_plan(user_request)
            if mode == "learn_syllabus_build":
                data["user_goal"] = f"Build a learning syllabus for course '{title}'."
            elif mode == "character_build":
                data["user_goal"] = f"Build a roleplay persona: {title}."
            else:
                data["user_goal"] = f"Write: {title}."
        else:
            data["user_goal"] = user_request.strip()[:2000]
    elif mode in ("learn_syllabus_build", "character_build", "writing"):
        goal = str(data.get("user_goal") or "")
        if any(
            tok in goal.lower()
            for tok in (
                "write_syllabus_file",
                "web_search",
                "save_research_note",
                "course_id=",
                "steps: ingest",
            )
        ):
            from agent.core.plan_descriptions import short_topic_for_plan

            title = short_topic_for_plan(goal or user_request)
            if mode == "learn_syllabus_build":
                data["user_goal"] = f"Build a learning syllabus for course '{title}'."
            elif mode == "character_build":
                data["user_goal"] = f"Build a roleplay persona: {title}."
            else:
                data["user_goal"] = f"Write: {title}."
    if not data.get("approach_summary"):
        steps = data.get("steps") or []
        kinds = [s.get("step_kind", "") for s in steps if isinstance(s, dict)]
        data["approach_summary"] = (
            f"Execute a {mode} task in {len(steps)} phase(s): "
            + " → ".join(kinds[:6])
            + ("." if steps else " Single-phase work then finalize.")
        )

    offline = bool(offline_research or data.get("offline_research"))
    if offline and mode == "research":
        data["offline_research"] = True

    hints = milestone_hints_for_mode(
        mode,
        offline=offline,
        capability=capability_research,
    )
    cap_act = capability_research or mode in (
        "research",
        "character_build",
        "learn_syllabus_build",
        "writing",
        "code",
    )
    prefix = "Capabilities" if cap_act else "Tools"
    if hints and mode == "research" and offline:
        data["milestones"] = [
            MilestoneModel(
                id=mid,
                label=mid.replace("_", " ").title(),
                success_criteria=f"{prefix} used: {', '.join(items[:3])}",
                status="pending",
            ).model_dump(mode="python")
            for mid, items in hints.items()
        ]
    elif not data.get("milestones"):
        skip_static_cap = cap_act and mode in (
            "learn_syllabus_build",
            "character_build",
            "writing",
            "code",
        )
        if not skip_static_cap:
            fallback = milestone_hints_for_mode(
                mode,
                offline=offline,
                capability=cap_act,
            )
            data["milestones"] = [
                MilestoneModel(
                    id=mid,
                    label=mid.replace("_", " ").title(),
                    success_criteria=f"{prefix} used: {', '.join(tools[:3])}",
                    status="pending",
                ).model_dump(mode="python")
                for mid, tools in fallback.items()
            ]
    data.setdefault("approval_status", "draft")
    data.setdefault("plan_version", 1)
    return data
