"""Rolling workspace summaries and tiered conversation retention (Aquila 3.4)."""
from __future__ import annotations

import json
import os
from typing import Any

from context_budget import ContextProfile, get_context_profile
from instance_registry import (
    append_conversation_archive,
    load_workspace_summary,
    save_workspace_summary,
)


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(str(part.get("text", "")))
        else:
            total += len(str(content))
    return max(1, total // 4)


def _strip_internal_keys(messages: list[dict]) -> list[dict]:
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]


def compress_step_transcript(history: list[dict], client, task_name: str = "") -> str:
    """Summarize a completed step for workspace memory."""
    if not history:
        return ""
    lines = []
    for msg in history[-24:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            snippet = content[:2000]
            lines.append(f"[{role}]: {snippet}")
    blob = "\n".join(lines)[:12_000]
    if not client:
        return f"Step summary for {task_name}:\n{blob[:1500]}"

    prompt = (
        "Summarize this agent step for future steps. Include: files touched, "
        "decisions, pytest/lint outcomes, open questions. Be factual; quote paths.\n\n"
        f"{blob}"
    )
    try:
        result = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            stream=False,
        )
        if isinstance(result, dict):
            text = result.get("message", {}).get("content", "") or ""
            if text.strip():
                return text.strip()
    except Exception:
        pass
    return f"Step summary for {task_name}:\n{blob[:1500]}"


def _keep_recent_turns(history: list[dict], keep: int) -> list[dict]:
    if keep <= 0 or not history:
        return []
    tool_turns: list[dict] = []
    for msg in history:
        content = msg.get("content", "")
        if msg.get("role") == "user" and isinstance(content, str) and "Tool Outputs:" in content:
            tool_turns.append(msg)
    kept = tool_turns[-keep:]
    if not kept:
        return history[-keep * 2 :] if len(history) > keep * 2 else list(history)
    return kept


def merge_workspace_summary(
    instance_id: str,
    task_name: str,
    step_summary: str,
    profile: ContextProfile,
    memory,
) -> str:
    existing = load_workspace_summary(instance_id) or memory.get_workspace_summary_row(task_name, instance_id)
    block = f"\n\n## Step — {task_name}\n{step_summary.strip()}\n"
    merged = (existing or f"# Workspace summary\n") + block
    cap = profile.workspace_summary_max_chars
    if cap > 0 and len(merged) > cap:
        merged = merged[-cap:]
    save_workspace_summary(instance_id, merged)
    memory.save_workspace_summary_row(task_name, merged, instance_id)
    return merged


def on_step_advance(
    *,
    conversation_history: list[dict],
    instance_id: str,
    task_name: str,
    advance_summary: str,
    client,
    memory,
    profile: ContextProfile | None = None,
) -> str:
    """Apply tier policy when advancing ledger steps; returns updated workspace summary text."""
    profile = profile or get_context_profile()
    step_summary = compress_step_transcript(conversation_history, client, task_name)
    if advance_summary:
        step_summary = f"{advance_summary}\n\n{step_summary}"

    try:
        from tool_library.agent_tools import save_research_note

        checkpoint_body = (step_summary or advance_summary or "")[:2000]
        if checkpoint_body.strip():
            save_research_note(
                task_name,
                f"[OS checkpoint]\n{checkpoint_body}",
            )
    except Exception:
        pass

    workspace_text = ""
    if profile.workspace_summary_max_chars > 0:
        workspace_text = merge_workspace_summary(
            instance_id, task_name, step_summary, profile, memory
        )

    append_conversation_archive(
        instance_id,
        {"event": "step_advance", "task": task_name, "summary": step_summary[:4000]},
    )

    if profile.clear_on_step_advance:
        conversation_history.clear()
    else:
        kept = _keep_recent_turns(conversation_history, profile.keep_turns_on_advance)
        conversation_history.clear()
        conversation_history.extend(kept)

    return workspace_text


def should_force_summarize(profile: ContextProfile, estimated_tokens: int) -> bool:
    return estimated_tokens > profile.in_step_token_cap


def should_proactive_summarize(profile: ContextProfile, estimated_tokens: int) -> bool:
    """Compress before/after turns when approaching in-step cap (max tier)."""
    if profile.tier != "max":
        return False
    cap = profile.in_step_token_cap
    if cap <= 0:
        return False
    # 50% — large single-turn scrapes can add ~20k tokens before the next pre-LLM check
    return estimated_tokens > int(cap * 0.5)


def build_loop_messages(
    *,
    system_prompt: str,
    rolling_summary: str,
    step_entry: list[dict],
    conversation_history: list[dict],
    user_message: dict,
    profile: ContextProfile | None = None,
) -> list[dict]:
    """Assemble messages for one loop turn with summary injection and in-step cap."""
    profile = profile or get_context_profile()

    def _env_int(name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return max(1, int(raw))
        except ValueError:
            return default

    def _truncate(text: str, cap: int, *, tail: bool = False, note: str = "") -> str:
        if cap <= 0 or len(text) <= cap:
            return text
        suffix = note or f"\n... [truncated to {cap} chars]"
        # Ensure we don't exceed cap by adding the suffix.
        avail = max(1, cap - len(suffix))
        clipped = text[-avail:] if tail else text[:avail]
        return clipped + suffix

    def _truncate_section(
        text: str,
        *,
        start: str,
        end: str,
        cap: int,
        tail: bool = True,
    ) -> tuple[str, bool]:
        if cap <= 0:
            return text, False
        i = text.find(start)
        if i < 0:
            return text, False
        j = text.find(end, i + len(start))
        if j < 0:
            return text, False
        body = text[i + len(start) : j]
        if len(body) <= cap:
            return text, False
        body_new = _truncate(
            body,
            cap,
            tail=tail,
            note=f"\n... [section truncated to {cap} chars]",
        )
        return text[: i + len(start)] + body_new + text[j:], True

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if rolling_summary and profile.workspace_summary_max_chars > 0:
        cap = profile.workspace_summary_max_chars
        text = rolling_summary[-cap:] if len(rolling_summary) > cap else rolling_summary
        messages.append({
            "role": "user",
            "content": f"--- WORKSPACE SUMMARY (prior steps) ---\n{text}\n--- END WORKSPACE SUMMARY ---",
        })
    messages.extend(_strip_internal_keys(step_entry))
    hist = list(conversation_history)
    while hist and estimate_messages_tokens(hist) > profile.in_step_token_cap:
        if len(hist) <= 2:
            break
        hist.pop(0)
    messages.extend(_strip_internal_keys(hist))
    messages.append(user_message)

    # Guardrail: enforce an overall prompt budget (step entry + summary + history + user msg),
    # not just conversation_history. This keeps 32k/standard stable on resume-heavy tasks.
    total_cap = _env_int("AQUILA_TOTAL_PROMPT_TOKEN_CAP", profile.in_step_token_cap)
    total_cap = max(2000, total_cap)
    if estimate_messages_tokens(messages) > total_cap:
        scratch_cap = max(2000, int(profile.scratchpad_bytes * 2))
        summary_cap = max(800, min(2000, profile.workspace_summary_max_chars or 2000))
        step_entry_cap = max(4000, int(profile.scrape_char_cap))

        for _ in range(6):
            if estimate_messages_tokens(messages) <= total_cap:
                break

            changed = False
            for m in messages:
                c = m.get("content")
                if not isinstance(c, str):
                    continue

                # Prefer truncating large embedded sections first.
                new_c, did = _truncate_section(
                    c,
                    start="--- SCRATCHPAD (prior steps) ---\n",
                    end="\n--- END SCRATCHPAD ---",
                    cap=scratch_cap,
                    tail=True,
                )
                if did:
                    m["content"] = new_c
                    changed = True
                    continue

                if "WORKSPACE SUMMARY" in c:
                    capped = _truncate(c, summary_cap, tail=True)
                    if capped != c:
                        m["content"] = capped
                        changed = True
                        continue

                if "OS HINT:" in c and len(c) > step_entry_cap:
                    capped = _truncate(c, step_entry_cap, tail=False)
                    if capped != c:
                        m["content"] = capped
                        changed = True

            if changed:
                continue

            # Last resort: drop oldest non-system, non-current-user messages.
            if len(messages) > 2:
                messages.pop(1)
            else:
                break

    return messages
