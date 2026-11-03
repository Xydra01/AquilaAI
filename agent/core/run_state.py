"""Unified per-task RunState for context management across all Aquila modes."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent.core.implementation_plan import (
    infer_completed_items,
    update_checklist_items,
)
from agent.core.loop_objectives import apply_ground_truth_to_milestone_state
from agent.core.loop_settings import run_digest_compress_enabled, run_state_enabled
from agent.core.run_state_providers import get_ground_truth_provider
from agent.core.task_artifacts import (
    atomic_write_json,
    read_plan_dict,
    run_state_path,
    write_plan_artifact,
)
from agent.policies.context_budget import ContextProfile, get_context_profile


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goal_summary(goal: str) -> str:
    g = (goal or "").strip()
    if len(g) <= 200:
        return g
    return g[:197] + "..."


@dataclass
class CapabilityCheckpoint:
    cap_id: str
    ok: bool
    summary: str
    timestamp: str = ""
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> CapabilityCheckpoint | None:
        if not raw:
            return None
        return cls(
            cap_id=str(raw.get("cap_id") or ""),
            ok=bool(raw.get("ok")),
            summary=str(raw.get("summary") or "")[:4000],
            timestamp=str(raw.get("timestamp") or _utc_now()),
            error_code=str(raw.get("error_code") or "") or None,
        )


@dataclass
class ChecklistItemState:
    id: str
    text: str
    status: str = "pending"

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "text": self.text, "status": self.status}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChecklistItemState:
        return cls(
            id=str(raw.get("id") or ""),
            text=str(raw.get("text") or ""),
            status=str(raw.get("status") or "pending"),
        )


class DigestCompressor:
    """Compress run digests when they exceed tier budget."""

    @staticmethod
    def compress_digest(digest: str, client: Any, task_name: str = "") -> str:
        from agent.policies.context_manager import compress_step_transcript

        if not digest.strip():
            return ""
        pseudo_history = [{"role": "user", "content": digest}]
        return compress_step_transcript(pseudo_history, client, task_name)


@dataclass
class TaskRunContext:
    """Single source of truth for per-task run progress and prompt context."""

    task_id: str
    mode: str
    goal: str
    goal_summary: str = ""
    run_digest: str = ""
    last_capability: CapabilityCheckpoint | None = None
    ground_truth: dict[str, Any] = field(default_factory=dict)
    checklist: list[ChecklistItemState] = field(default_factory=list)
    episode: int = 0
    step_index: int = 0
    milestones: dict[str, bool] = field(default_factory=dict)
    updated_at: str = ""
    instance_id: str = "default"

    def __post_init__(self) -> None:
        if not self.goal_summary:
            self.goal_summary = _goal_summary(self.goal)
        if not self.updated_at:
            self.updated_at = _utc_now()

    @classmethod
    def bootstrap(
        cls,
        *,
        task_id: str,
        mode: str,
        goal: str,
        instance_id: str = "default",
        workspace_summary: str = "",
        step_index: int = 0,
    ) -> TaskRunContext:
        plan = read_plan_dict(task_id, mode)
        checklist: list[ChecklistItemState] = []
        impl = plan.get("implementation") if isinstance(plan, dict) else None
        if isinstance(impl, dict):
            for item in impl.get("checklist") or []:
                if isinstance(item, dict):
                    checklist.append(ChecklistItemState.from_dict(item))
        digest = ""
        if workspace_summary and workspace_summary.strip() not in (
            "(No steps completed yet.)",
            "# Workspace summary",
        ):
            digest = f"[Bootstrapped from workspace summary]\n{workspace_summary[-2000:]}"
        return cls(
            task_id=task_id,
            mode=mode,
            goal=goal,
            run_digest=digest,
            checklist=checklist,
            step_index=step_index,
            instance_id=instance_id,
        )

    @classmethod
    def load(
        cls,
        task_id: str,
        mode: str,
        *,
        goal: str = "",
        instance_id: str = "default",
        workspace_summary: str = "",
        step_index: int = 0,
    ) -> TaskRunContext:
        path = run_state_path(task_id, mode)
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return cls.from_dict(raw)
            except Exception:
                pass
        return cls.bootstrap(
            task_id=task_id,
            mode=mode,
            goal=goal,
            instance_id=instance_id,
            workspace_summary=workspace_summary,
            step_index=step_index,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TaskRunContext:
        checklist = [
            ChecklistItemState.from_dict(x)
            for x in (raw.get("checklist") or [])
            if isinstance(x, dict)
        ]
        return cls(
            task_id=str(raw.get("task_id") or ""),
            mode=str(raw.get("mode") or "task"),
            goal=str(raw.get("goal") or ""),
            goal_summary=str(raw.get("goal_summary") or ""),
            run_digest=str(raw.get("run_digest") or ""),
            last_capability=CapabilityCheckpoint.from_dict(raw.get("last_capability")),
            ground_truth=dict(raw.get("ground_truth") or {}),
            checklist=checklist,
            episode=int(raw.get("episode") or 0),
            step_index=int(raw.get("step_index") or 0),
            milestones=dict(raw.get("milestones") or {}),
            updated_at=str(raw.get("updated_at") or _utc_now()),
            instance_id=str(raw.get("instance_id") or "default"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mode": self.mode,
            "goal": self.goal,
            "goal_summary": self.goal_summary,
            "run_digest": self.run_digest,
            "last_capability": (
                self.last_capability.to_dict() if self.last_capability else None
            ),
            "ground_truth": self.ground_truth,
            "checklist": [c.to_dict() for c in self.checklist],
            "episode": self.episode,
            "step_index": self.step_index,
            "milestones": self.milestones,
            "updated_at": self.updated_at,
            "instance_id": self.instance_id,
        }

    def persist(self) -> str:
        self.updated_at = _utc_now()
        path = run_state_path(self.task_id, self.mode)
        atomic_write_json(path, self.to_dict())
        return str(path)

    def _sync_checklist_to_plan(self, item_ids: list[str]) -> int:
        if not item_ids:
            return 0
        plan = read_plan_dict(self.task_id, self.mode)
        plan, count = update_checklist_items(
            plan,
            mode=self.mode,
            item_ids=item_ids,
            status="done",
        )
        if count:
            write_plan_artifact(self.task_id, self.mode, plan)
            impl = plan.get("implementation") or {}
            self.checklist = [
                ChecklistItemState.from_dict(x)
                for x in (impl.get("checklist") or [])
                if isinstance(x, dict)
            ]
        return count

    def checkpoint_outcome(
        self,
        *,
        cap_id: str,
        ok: bool,
        summary_text: str,
        harness_ctx: Any = None,
        client: Any = None,
        milestone_tracker: Any = None,
        profile: ContextProfile | None = None,
    ) -> dict[str, Any]:
        """Record any capability outcome (success, failure, or OS block) in RunState."""
        from agent.capabilities.base import CapabilityResult

        if ok:
            result: Any = CapabilityResult.success(summary=(summary_text or "")[:500])
        else:
            result = CapabilityResult.failure("os_block", (summary_text or "")[:500])
        meta = self.checkpoint_capability(
            cap_id=cap_id,
            result=result,
            summary_text=summary_text,
            harness_ctx=harness_ctx,
            client=client,
            milestone_tracker=milestone_tracker,
            profile=profile,
        )
        return meta

    def checkpoint_capability(
        self,
        *,
        cap_id: str,
        result: Any,
        summary_text: str,
        harness_ctx: Any = None,
        client: Any = None,
        milestone_tracker: Any = None,
        profile: ContextProfile | None = None,
    ) -> dict[str, Any]:
        """Update run state after a capability completes. Returns change metadata."""
        profile = profile or get_context_profile()
        ok = bool(getattr(result, "ok", False))
        error_code = getattr(result, "error_code", None)
        if not ok and not error_code and "OS BLOCK" in (summary_text or ""):
            error_code = "os_block"
        self.last_capability = CapabilityCheckpoint(
            cap_id=cap_id,
            ok=ok,
            summary=(summary_text or "")[:4000],
            error_code=str(error_code) if error_code else None,
        )

        provider = get_ground_truth_provider(self.mode)
        if cap_id == "cap.dev.run_tests@v1" and ok:
            low = (summary_text or "").lower()
            passed = "passed" in low or "0 failed" in low
            self.ground_truth["tests_pass"] = passed
        snapshot = provider.snapshot(
            task_id=self.task_id,
            mode=self.mode,
            harness_ctx=harness_ctx,
        )
        if self.ground_truth.get("tests_pass") is not None:
            snapshot["tests_pass"] = self.ground_truth["tests_pass"]
        self.ground_truth = snapshot

        provider_ticks = provider.infer_checklist_ticks(cap_id, result, snapshot)
        inferred = infer_completed_items(
            cap_id,
            result,
            snapshot,
            mode=self.mode,
        )
        gt_ticks_fn = getattr(provider, "infer_checklist_ticks_from_snapshot", None)
        gt_ticks = gt_ticks_fn(snapshot) if callable(gt_ticks_fn) else []
        all_ticks = list(dict.fromkeys(provider_ticks + inferred + gt_ticks))
        checklist_updated = self._sync_checklist_to_plan(all_ticks)

        self.milestones = provider.infer_milestones(snapshot)
        if milestone_tracker is not None:
            apply_ground_truth_to_milestone_state(
                milestone_tracker.state,
                self.mode,
                self.ground_truth,
                cap_id=cap_id,
                result_ok=ok,
            )

        bullet = f"- [{cap_id}] {'OK' if ok else 'FAIL'}: {(summary_text or '')[:500]}"
        if self.run_digest:
            self.run_digest = f"{self.run_digest.rstrip()}\n{bullet}"
        else:
            self.run_digest = bullet

        digest_cap = profile.run_digest_max_chars
        if (
            digest_cap > 0
            and len(self.run_digest) > digest_cap
            and run_digest_compress_enabled()
            and client
        ):
            self.run_digest = DigestCompressor.compress_digest(
                self.run_digest,
                client,
                self.task_id,
            )
        if digest_cap > 0 and len(self.run_digest) > digest_cap:
            self.run_digest = self.run_digest[-digest_cap:]

        self.persist()
        return {
            "checklist_updated": checklist_updated,
            "checklist_ticks": all_ticks,
            "milestones": dict(self.milestones),
            "digest_len": len(self.run_digest),
        }

    def render_for_prompt(
        self,
        *,
        profile: ContextProfile | None = None,
        include_full_goal: bool = False,
    ) -> str:
        profile = profile or get_context_profile()
        lines = ["--- RUN STATE (authoritative progress) ---"]
        if include_full_goal or self.episode == 0:
            lines.append(f"**Goal:** {self.goal[:2000]}")
        else:
            lines.append(f"**Goal (summary):** {self.goal_summary}")
        if self.run_digest.strip():
            digest = self._digest_for_prompt(profile)
            lines.extend(["", "**Progress digest:**", digest])
        if self.last_capability:
            lc = self.last_capability
            lines.extend([
                "",
                "**Last capability:**",
                f"- `{lc.cap_id}` ({'ok' if lc.ok else 'failed'})",
                lc.summary[:2500],
            ])
        if self.ground_truth:
            gt_lines = self._format_ground_truth(profile)
            if gt_lines:
                lines.extend(["", "**Ground truth:**", gt_lines])
        open_items = [c for c in self.checklist if c.status == "pending"]
        if self.checklist:
            done = sum(1 for c in self.checklist if c.status == "done")
            lines.append(f"\n**Checklist:** {done}/{len(self.checklist)} done")
            for item in open_items[:5]:
                lines.append(f"- [ ] {item.text} (`{item.id}`)")
        if self.milestones:
            done_ms = [k for k, v in self.milestones.items() if v]
            if done_ms:
                lines.append(f"**Milestones done:** {', '.join(done_ms)}")
        lines.append("--- END RUN STATE ---")
        return "\n".join(lines)

    def _digest_for_prompt(self, profile: ContextProfile) -> str:
        digest = self.run_digest
        if "- [" in digest and "[Bootstrapped from workspace summary]" in digest:
            idx = digest.find("- [")
            if idx > 0:
                digest = digest[idx:]
        cap = profile.run_digest_max_chars
        if cap > 0 and len(digest) > cap:
            digest = digest[-cap:]
        return digest

    def render_think_anchor(self) -> str:
        """Compact progress summary for think/reflect turns."""
        lines: list[str] = []
        gt = self.ground_truth or {}
        files = gt.get("buffer_files") or []
        if files:
            shown = ", ".join(f"`{f}`" for f in files[:8])
            lines.append(f"Buffer files: {shown}")
        if self.last_capability:
            lc = self.last_capability
            status = "ok" if lc.ok else "FAILED"
            summary_line = (lc.summary or "").splitlines()[0][:200]
            lines.append(f"Last capability: `{lc.cap_id}` ({status}) — {summary_line}")
        open_ids = [c.id for c in self.checklist if c.status == "pending"]
        if open_ids:
            lines.append(f"Open checklist: {', '.join(open_ids[:5])}")
        if self.last_capability and not self.last_capability.ok:
            low = (self.last_capability.summary or "").lower()
            error_code = (self.last_capability.error_code or "").strip().lower()
            if (
                self.last_capability.cap_id == "cap.dev.create_file@v1"
                and "exists" in low
            ):
                lines.append(
                    "Next: do NOT create_file again — use read_region, edit_apply, or run_tests."
                )
            elif error_code in ("invalid_input", "os_block") or "os block" in low:
                from agent.capabilities.schema_hints import format_capability_argument_hints

                hints = format_capability_argument_hints(
                    [self.last_capability.cap_id],
                    max_caps=1,
                )
                if hints:
                    lines.append(f"Argument hint: {hints.lstrip('- ')}")
        if not lines:
            lines.append("(No progress recorded yet.)")
        return "\n".join(lines[:15])

    def _format_ground_truth(self, profile: ContextProfile) -> str:
        cap = profile.ground_truth_max_chars or 2000
        parts: list[str] = []
        mode = (self.mode or "").lower()
        gt = self.ground_truth
        if mode == "code":
            files = gt.get("buffer_files") or []
            if files:
                parts.append("Files: " + ", ".join(f"`{f}`" for f in files[:12]))
            if gt.get("setup_done"):
                parts.append("Project setup: done")
            if gt.get("tests_pass") is not None:
                parts.append(f"Tests: {'pass' if gt['tests_pass'] else 'fail/pending'}")
        elif mode == "writing":
            parts.append(
                f"Draft: {gt.get('section_count', 0)} sections, "
                f"{gt.get('word_count', 0)} words"
            )
        elif mode == "research":
            parts.append(f"Notes: ~{gt.get('notes_count', 0)}")
        elif mode == "learn_syllabus_build":
            parts.append(
                f"Syllabus: {'yes' if gt.get('has_syllabus') else 'no'}, "
                f"modules: {gt.get('module_count', 0)}"
            )
        elif mode == "character_build":
            parts.append(
                f"Init: {'yes' if gt.get('has_initialization') else 'no'}, "
                f"finalized: {'yes' if gt.get('finalized') else 'no'}"
            )
        text = "\n".join(parts)
        if len(text) > cap:
            return text[: cap - 20] + "\n…[truncated]"
        return text

    def build_turn_messages(
        self,
        *,
        system_prompt: str,
        step_entry: list[dict],
        conversation_history: list[dict],
        user_message: dict,
        profile: ContextProfile | None = None,
        include_full_goal: bool = False,
        legacy_workspace_summary: str = "",
    ) -> list[dict]:
        """Assemble messages for one loop turn using RunState as canonical context."""
        from agent.policies.context_manager import build_loop_messages

        profile = profile or get_context_profile()
        run_block = self.render_for_prompt(
            profile=profile,
            include_full_goal=include_full_goal,
        )
        return build_loop_messages(
            system_prompt=system_prompt,
            rolling_summary=legacy_workspace_summary if not run_state_enabled() else "",
            step_entry=step_entry,
            conversation_history=conversation_history,
            user_message=user_message,
            profile=profile,
            run_state_block=run_block if run_state_enabled() else "",
        )

    def rollup_to_workspace_summary(self, step_summary: str = "") -> str:
        """Produce text for instance-level workspace summary rollup on step advance."""
        parts = [f"## Task — {self.task_id}"]
        if step_summary.strip():
            parts.append(step_summary.strip())
        if self.run_digest.strip():
            parts.append(self.run_digest[-3000:])
        return "\n\n".join(parts)


def rollup_run_digest_to_workspace(
    run_ctx: TaskRunContext,
    *,
    instance_id: str,
    step_summary: str,
    profile: ContextProfile,
    memory: Any,
) -> str:
    """Merge run digest into instance workspace summary on step advance."""
    from agent.policies.context_manager import merge_workspace_summary

    body = run_ctx.rollup_to_workspace_summary(step_summary)
    if profile.workspace_summary_max_chars <= 0:
        return ""
    return merge_workspace_summary(
        instance_id,
        run_ctx.task_id,
        body,
        profile,
        memory,
    )
