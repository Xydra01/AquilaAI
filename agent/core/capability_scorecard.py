"""Analyze Aquila run JSONL logs into capability scorecards (separate from health-check)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .plan_validator import is_degenerate_description
from agent.storage import agent_data_path

_URL_RE = re.compile(r"https?://[^\s\)\]>\"']+", re.I)

FINALIZE_CAPABILITY_IDS = frozenset({
    "cap.research.finalize_deliverable@v1",
    "cap.persona.finalize@v1",
    "cap.learn.finalize_course@v1",
    "cap.writing.finalize_deliverable@v1",
    "cap.writing.compile_document@v1",
    "cap.dev.sync_project@v1",
})

WEB_GATHER_CAPABILITY_IDS = frozenset({
    "cap.research.gather_web_sources@v1",
    "cap.web.search@v1",
})

READ_PAGES_CAPABILITY_IDS = frozenset({
    "cap.web.read_pages@v1",
})


@dataclass
class CapabilityScorecard:
    """Aggregated metrics from one run JSONL file."""

    source_path: str
    task: str = ""
    mode: str = ""
    llm_requests: int = 0
    llm_responses: int = 0
    read_timeouts: int = 0
    scrape_budget_exhausted: int = 0
    dictionary_scrape_avoided: int = 0
    scratchpad_block: int = 0
    premature_finish_blocked: int = 0
    explore_path_hallucination: int = 0
    os_warnings: int = 0
    duplicate_tool_blocks: int = 0
    url_blocks: int = 0
    max_episode_per_step: int = 0
    episodes_by_step: dict[int, int] = field(default_factory=dict)
    tool_starts: dict[str, int] = field(default_factory=dict)
    cap_starts: dict[str, int] = field(default_factory=dict)
    finish_task: bool = False
    capability_finalize: bool = False
    degenerate_scratchpad: bool = False
    deliverable_path: str | None = None
    deliverable_chars: int = 0
    wall_time_s: float | None = None
    micro_plan_used: int = 0
    explore_brief_skipped: int = 0
    act_turns: int = 0
    plan_llm_calls: int = 0
    delegate_mode_complete: int = 0
    forced_advance_count: int = 0
    parse_failures: int = 0
    milestone_update_count: int = 0
    dynamic_loop_runs: int = 0
    tool_call_count: int = 0
    total_output_tokens_est: int = 0
    total_prompt_tokens_est: int = 0
    median_output_tokens_per_s: float | None = None
    failures: list[str] = field(default_factory=list)
    passes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "task": self.task,
            "mode": self.mode,
            "llm_requests": self.llm_requests,
            "llm_responses": self.llm_responses,
            "read_timeouts": self.read_timeouts,
            "scrape_budget_exhausted": self.scrape_budget_exhausted,
            "dictionary_scrape_avoided": self.dictionary_scrape_avoided,
            "scratchpad_block": self.scratchpad_block,
            "premature_finish_blocked": self.premature_finish_blocked,
            "explore_path_hallucination": self.explore_path_hallucination,
            "os_warnings": self.os_warnings,
            "duplicate_tool_blocks": self.duplicate_tool_blocks,
            "url_blocks": self.url_blocks,
            "max_episode_per_step": self.max_episode_per_step,
            "episodes_by_step": self.episodes_by_step,
            "tool_starts": self.tool_starts,
            "cap_starts": self.cap_starts,
            "finish_task": self.finish_task,
            "capability_finalize": self.capability_finalize,
            "degenerate_scratchpad": self.degenerate_scratchpad,
            "deliverable_path": self.deliverable_path,
            "deliverable_chars": self.deliverable_chars,
            "wall_time_s": self.wall_time_s,
            "micro_plan_used": self.micro_plan_used,
            "explore_brief_skipped": self.explore_brief_skipped,
            "act_turns": self.act_turns,
            "plan_llm_calls": self.plan_llm_calls,
            "delegate_mode_complete": self.delegate_mode_complete,
            "forced_advance_count": self.forced_advance_count,
            "milestone_update_count": self.milestone_update_count,
            "dynamic_loop_runs": self.dynamic_loop_runs,
            "tool_call_count": self.tool_call_count,
            "total_output_tokens_est": self.total_output_tokens_est,
            "total_prompt_tokens_est": self.total_prompt_tokens_est,
            "median_output_tokens_per_s": self.median_output_tokens_per_s,
            "passed": self.passed,
            "failures": self.failures,
            "passes": self.passes,
        }


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text or "")


def _record_tool_or_cap_start(card: CapabilityScorecard, name: str) -> None:
    if name.startswith("cap:"):
        cap_id = name[4:]
        card.cap_starts[cap_id] = card.cap_starts.get(cap_id, 0) + 1
        if cap_id in FINALIZE_CAPABILITY_IDS:
            card.capability_finalize = True
            card.finish_task = True
    else:
        card.tool_starts[name] = card.tool_starts.get(name, 0) + 1


def _web_search_count(card: CapabilityScorecard) -> int:
    total = card.tool_starts.get("web_search", 0)
    for cap_id in WEB_GATHER_CAPABILITY_IDS:
        total += card.cap_starts.get(cap_id, 0)
    return total


def _read_webpage_count(card: CapabilityScorecard) -> int:
    total = card.tool_starts.get("read_webpage", 0)
    for cap_id in READ_PAGES_CAPABILITY_IDS:
        total += card.cap_starts.get(cap_id, 0)
    return total


def analyze_jsonl(
    path: str | Path,
    *,
    min_deliverable_chars: int = 0,
    deliverable_glob: str | None = None,
    max_episodes_per_step: int | None = None,
    max_duplicate_blocks: int | None = None,
    max_read_timeouts: int | None = None,
    require_finish: bool = False,
    max_forced_advance_count: int | None = None,
    require_dynamic_loop: bool = False,
    min_web_search: int | None = None,
    min_read_webpage: int | None = None,
    max_parse_failures: int | None = None,
) -> CapabilityScorecard:
    """Parse a run JSONL and compute capability metrics."""
    p = Path(path)
    card = CapabilityScorecard(source_path=str(p.resolve()))
    if not p.is_file():
        card.failures.append(f"JSONL not found: {p}")
        return card

    first_ts: datetime | None = None
    last_ts: datetime | None = None
    last_search_urls: list[str] = []
    scratchpad_texts: list[str] = []
    tps_samples: list[float] = []
    output_tokens_total = 0

    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ev = rec.get("event", "")
            ts = _parse_ts(str(rec.get("ts", "")))
            if ts:
                first_ts = first_ts or ts
                last_ts = ts

            if not card.task and rec.get("task"):
                card.task = str(rec["task"])
            if not card.mode and rec.get("mode"):
                card.mode = str(rec["mode"])

            if ev == "llm_request":
                card.llm_requests += 1
                est = rec.get("est_tokens")
                if est is not None:
                    try:
                        card.total_prompt_tokens_est += int(est)
                    except (TypeError, ValueError):
                        pass
            elif ev == "llm_response":
                card.llm_responses += 1
                out_tok = rec.get("output_tokens_est")
                if out_tok is not None:
                    try:
                        output_tokens_total += int(out_tok)
                    except (TypeError, ValueError):
                        pass
                else:
                    body = rec.get("body") or rec.get("body_preview") or ""
                    dur_ms = rec.get("duration_ms")
                    if body and dur_ms and int(dur_ms) > 0:
                        from agent.parser import estimate_tokens_metrics

                        est_out, tps = estimate_tokens_metrics(
                            str(body), duration_s=int(dur_ms) / 1000.0
                        )
                        output_tokens_total += est_out
                        if tps is not None and tps > 0:
                            tps_samples.append(tps)
                tps_val = rec.get("output_tokens_per_s")
                if tps_val is not None:
                    try:
                        tps_f = float(tps_val)
                        if tps_f > 0:
                            tps_samples.append(tps_f)
                    except (TypeError, ValueError):
                        pass
                step_idx = rec.get("step_index")
                ep = rec.get("episode")
                if step_idx is not None and ep is not None:
                    idx = int(step_idx)
                    card.episodes_by_step[idx] = max(card.episodes_by_step.get(idx, 0), int(ep))
            elif ev == "read_timeout" or (
                ev == "os_warning" and rec.get("message") == "read_timeout"
            ):
                card.read_timeouts += 1
            elif ev == "scrape_budget_exhausted":
                card.scrape_budget_exhausted += 1
            elif ev == "dictionary_scrape_avoided":
                card.dictionary_scrape_avoided += 1
            elif ev == "scratchpad_block":
                card.scratchpad_block += 1
            elif ev == "premature_finish_blocked":
                card.premature_finish_blocked += 1
            elif ev == "explore_path_hallucination":
                card.explore_path_hallucination += 1
            elif ev == "os_warning":
                card.os_warnings += 1
                msg = str(rec.get("message", ""))
                if "PARSE ERROR" in msg.upper():
                    card.parse_failures += 1
            elif ev in ("agent_turn", "llm_response"):
                preview = str(
                    rec.get("body_preview")
                    or rec.get("body")
                    or rec.get("content_preview")
                    or ""
                )
                if "OS PARSE ERROR" in preview:
                    card.parse_failures += 1
            elif ev == "delegate_mode_complete":
                card.delegate_mode_complete += 1
            elif ev == "forced_advance":
                card.forced_advance_count += 1
            elif ev == "milestone_update":
                card.milestone_update_count += 1
            elif ev == "palette_mode":
                if str(rec.get("dynamic", "")).lower() in ("1", "true", "yes"):
                    card.dynamic_loop_runs = max(card.dynamic_loop_runs, 1)
            elif ev == "micro_plan_used":
                card.micro_plan_used += 1
            elif ev == "explore_brief_skipped":
                card.explore_brief_skipped += 1
            elif ev == "act_turn":
                card.act_turns += 1
            elif ev == "plan_llm_call":
                card.plan_llm_calls += 1
            elif ev == "tool_start":
                name = str(rec.get("tool_name", ""))
                _record_tool_or_cap_start(card, name)
                if name == "web_search":
                    args = rec.get("arguments") or {}
                    q = str(args.get("query", ""))
                    last_search_urls = []
                if name == "finish_task":
                    card.finish_task = True
            elif ev == "tool_end":
                card.tool_call_count += 1
                name = str(rec.get("tool_name", ""))
                preview = str(rec.get("result_preview") or rec.get("body_preview") or "")
                if name.startswith("cap:"):
                    cap_id = name[4:]
                    if cap_id in FINALIZE_CAPABILITY_IDS and not preview.startswith("❌"):
                        card.capability_finalize = True
                        card.finish_task = True
                if name == "web_search":
                    last_search_urls = _extract_urls(preview)
                if name == "save_research_note":
                    args = rec.get("arguments") or {}
                    gathered = str(args.get("gathered_data", ""))
                    if gathered:
                        scratchpad_texts.append(gathered)
                    elif "gathered_data" in preview:
                        scratchpad_texts.append(preview)
                if name == "finish_task":
                    card.finish_task = True
                if "OS BLOCK" in preview:
                    if "already fetched" in preview.lower() or "duplicate" in preview.lower():
                        if "tool call repeated" in preview.lower():
                            card.duplicate_tool_blocks += 1
                        else:
                            card.url_blocks += 1
                    elif "tool call repeated" in preview.lower():
                        card.duplicate_tool_blocks += 1

    if card.episodes_by_step:
        card.max_episode_per_step = max(card.episodes_by_step.values())

    if first_ts and last_ts:
        card.wall_time_s = (last_ts - first_ts).total_seconds()

    card.total_output_tokens_est = output_tokens_total
    if tps_samples:
        import statistics

        card.median_output_tokens_per_s = round(statistics.median(tps_samples), 2)

    for text in scratchpad_texts:
        if is_degenerate_description(text):
            card.degenerate_scratchpad = True
            break

    _check_deliverable(card, deliverable_glob, min_deliverable_chars)

    if max_episodes_per_step is not None and card.max_episode_per_step > max_episodes_per_step:
        card.failures.append(
            f"max_episode_per_step {card.max_episode_per_step} > {max_episodes_per_step}"
        )
    else:
        if max_episodes_per_step is not None:
            card.passes.append(f"episodes_per_step<={max_episodes_per_step}")

    if max_duplicate_blocks is not None and card.duplicate_tool_blocks > max_duplicate_blocks:
        card.failures.append(
            f"duplicate_tool_blocks {card.duplicate_tool_blocks} > {max_duplicate_blocks}"
        )
    elif max_duplicate_blocks is not None:
        card.passes.append(f"duplicate_blocks<={max_duplicate_blocks}")

    if max_read_timeouts is not None and card.read_timeouts > max_read_timeouts:
        card.failures.append(f"read_timeouts {card.read_timeouts} > {max_read_timeouts}")
    elif max_read_timeouts is not None:
        card.passes.append(f"read_timeouts<={max_read_timeouts}")

    if require_finish and not (card.finish_task or card.capability_finalize):
        card.failures.append("finish_task / finalize capability not observed in log")
    elif require_finish:
        if card.capability_finalize:
            card.passes.append("finalize capability seen")
        else:
            card.passes.append("finish_task seen")

    if min_web_search is not None:
        ws = _web_search_count(card)
        if ws < min_web_search:
            card.failures.append(f"web/gather sources {ws} < {min_web_search}")
        else:
            card.passes.append(f"web/gather sources>={min_web_search}")

    if min_read_webpage is not None:
        rw = _read_webpage_count(card)
        if rw < min_read_webpage:
            card.failures.append(f"read_webpage / read_pages {rw} < {min_read_webpage}")
        else:
            card.passes.append(f"read_webpage/read_pages>={min_read_webpage}")

    if max_parse_failures is not None and card.parse_failures > max_parse_failures:
        card.failures.append(
            f"parse_failures {card.parse_failures} > {max_parse_failures}"
        )
    elif max_parse_failures is not None:
        card.passes.append(f"parse_failures<={max_parse_failures}")

    if max_forced_advance_count is not None:
        if card.forced_advance_count > max_forced_advance_count:
            card.failures.append(
                f"forced_advance_count {card.forced_advance_count} > "
                f"{max_forced_advance_count}"
            )
        else:
            card.passes.append(
                f"forced_advance_count<={max_forced_advance_count}"
            )

    if require_dynamic_loop and card.dynamic_loop_runs < 1:
        card.failures.append("dynamic loop not active in log (palette_mode missing)")
    elif require_dynamic_loop:
        card.passes.append("dynamic_loop active")

    if card.degenerate_scratchpad:
        card.failures.append("degenerate scratchpad content detected")
    elif scratchpad_texts:
        card.passes.append("scratchpad quality OK")

    if min_deliverable_chars > 0 and card.deliverable_chars < min_deliverable_chars:
        card.failures.append(
            f"deliverable {card.deliverable_chars} chars < {min_deliverable_chars}"
        )
    elif min_deliverable_chars > 0:
        card.passes.append(f"deliverable>={min_deliverable_chars} chars")

    return card


def _check_deliverable(
    card: CapabilityScorecard,
    deliverable_glob: str | None,
    min_chars: int,
) -> None:
    if not deliverable_glob and min_chars <= 0:
        return
    pattern = deliverable_glob or "**/initialization.md"
    root = agent_data_path("Agent-Instances")
    if not root.is_dir():
        return
    best_len = -1
    for candidate in root.glob(pattern):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > best_len:
            best_len = len(text)
            card.deliverable_chars = len(text)
            card.deliverable_path = str(candidate)


# Scenario rubrics for capability runs
CAPABILITY_SCENARIOS: dict[str, dict[str, Any]] = {
    "persona_build_lore": {
        "description": "Character build with web lore (replay JSONL or live)",
        "mode": "character_build",
        "max_episodes_per_step": 6,
        "max_duplicate_blocks": 2,
        "max_read_timeouts": 1,
        "min_deliverable_chars": 800,
        "deliverable_glob": "**/initialization.md",
        "require_finish": False,
    },
    "research_short": {
        "description": "Short research task metrics",
        "mode": "research",
        "max_episodes_per_step": 8,
        "max_duplicate_blocks": 3,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 0,
        "require_finish": False,
    },
    "autonomous_trivial": {
        "description": "Trivial autonomous task",
        "mode": "task",
        "max_episodes_per_step": 10,
        "max_duplicate_blocks": 3,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 0,
        "require_finish": False,
    },
    "chat_tool_once": {
        "description": "Chat with at most one tool round-trip",
        "mode": "chat",
        "max_episodes_per_step": 3,
        "max_duplicate_blocks": 1,
        "max_read_timeouts": 1,
        "min_deliverable_chars": 0,
        "require_finish": False,
    },
    "code_smoke_file": {
        "description": "Harness: create harness_smoke.py",
        "mode": "code",
        "max_episodes_per_step": 12,
        "max_duplicate_blocks": 2,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 0,
        "require_finish": True,
        "max_forced_advance_count": 0,
    },
    "code_habit_tracker": {
        "description": "Harness: TDD habit tracker CLI",
        "mode": "code",
        "max_episodes_per_step": 24,
        "max_duplicate_blocks": 4,
        "max_read_timeouts": 3,
        "min_deliverable_chars": 0,
        "require_finish": False,
        "max_forced_advance_count": 1,
    },
    "code_short": {
        "description": "Harness: short code edit + sync",
        "mode": "code",
        "max_episodes_per_step": 10,
        "max_duplicate_blocks": 2,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 0,
        "require_finish": True,
    },
    "code_local_read": {
        "description": "Harness: local code read/summarize",
        "mode": "code",
        "max_episodes_per_step": 10,
        "max_duplicate_blocks": 1,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 0,
        "require_finish": False,
    },
    "research_local_lock": {
        "description": "Harness: local research on lock module",
        "mode": "research",
        "max_episodes_per_step": 10,
        "max_duplicate_blocks": 1,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 400,
        "require_finish": False,
    },
    "writing_short": {
        "description": "Harness: short writing draft",
        "mode": "writing",
        "max_episodes_per_step": 10,
        "max_duplicate_blocks": 4,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 300,
        "deliverable_glob": "**/Agent-Drafts/*.md",
        "require_finish": False,
    },
    "task_lock_check": {
        "description": "Harness: trivial task on generation lock",
        "mode": "task",
        "max_episodes_per_step": 12,
        "max_duplicate_blocks": 5,
        "max_read_timeouts": 2,
        "min_deliverable_chars": 200,
        "require_finish": False,
    },
    "research_web_chronology_mini": {
        "description": "Web chronology: Iran–Israel + Israel–Lebanon ordered events",
        "mode": "research",
        "max_episodes_per_step": 14,
        "max_duplicate_blocks": 2,
        "max_read_timeouts": 2,
        "min_web_search": 2,
        "min_read_webpage": 1,
        "max_parse_failures": 1,
        "max_forced_advance_count": 0,
        "require_finish": True,
        "min_deliverable_chars": 800,
        "require_dynamic_loop": True,
    },
}


def score_jsonl_for_scenario(path: str | Path, scenario_key: str) -> CapabilityScorecard:
    rubric = CAPABILITY_SCENARIOS.get(scenario_key, {})
    return analyze_jsonl(
        path,
        min_deliverable_chars=int(rubric.get("min_deliverable_chars", 0)),
        deliverable_glob=rubric.get("deliverable_glob"),
        max_episodes_per_step=rubric.get("max_episodes_per_step"),
        max_duplicate_blocks=rubric.get("max_duplicate_blocks"),
        max_read_timeouts=rubric.get("max_read_timeouts"),
        require_finish=bool(rubric.get("require_finish", False)),
        max_forced_advance_count=rubric.get("max_forced_advance_count"),
        require_dynamic_loop=bool(rubric.get("require_dynamic_loop", False)),
        min_web_search=rubric.get("min_web_search"),
        min_read_webpage=rubric.get("min_read_webpage"),
        max_parse_failures=rubric.get("max_parse_failures"),
    )


def write_scorecard_jsonl(card: CapabilityScorecard, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now().isoformat(timespec="seconds"), **card.to_dict()}
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out


def find_latest_jsonl(task_prefix: str) -> Path | None:
    logs = agent_data_path("Agent-Logs")
    if not logs.is_dir():
        return None
    matches = sorted(
        logs.glob(f"{task_prefix}*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None
