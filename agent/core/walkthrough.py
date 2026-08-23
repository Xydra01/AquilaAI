"""Generate post-task walkthrough artifacts via reflect pass."""
from __future__ import annotations

import json
from typing import Any, Callable


def build_walkthrough_prompt(
    *,
    task_name: str,
    mode: str,
    user_goal: str,
    plan_summary: str,
    tool_summary: str,
    deliverable_path: str | None,
    finish_msg: str,
) -> str:
    return f"""You are Aquila completing a task walkthrough for the user.

Task: {task_name}
Mode: {mode}
User goal: {user_goal[:1500]}

Approved plan approach:
{plan_summary[:2000]}

Tool/capability execution summary:
{tool_summary[:4000]}

Deliverable: {deliverable_path or "(none)"}
Finish message: {finish_msg[:500]}

Rules:
- Base the walkthrough only on the goal, plan, execution summary, deliverable path, and finish message.
- If a deliverable path is present, do NOT claim sources were missing or that no PDF/attachments were processed.
- "0 web bibliography sources" on offline/attachment research is normal — it does not mean the report is empty.

Output ONLY valid JSON with these keys:
- summary (string, one paragraph)
- what_we_did (array of strings, ordered key actions)
- why_those_choices (string, tie to plan)
- how_to_verify (array of strings, concrete user checks)
- files_changed (array of strings, paths if known)
- open_questions (array of strings)
- lessons_learned (array of strings, for future tasks)
"""


def generate_walkthrough(
    client,
    *,
    task_name: str,
    mode: str,
    user_goal: str = "",
    plan_summary: str = "",
    tool_summary: str = "",
    deliverable_path: str | None = None,
    finish_msg: str = "",
) -> dict[str, Any]:
    from agent.parser.structured_schema import WalkthroughModel

    prompt = build_walkthrough_prompt(
        task_name=task_name,
        mode=mode,
        user_goal=user_goal,
        plan_summary=plan_summary,
        tool_summary=tool_summary,
        deliverable_path=deliverable_path,
        finish_msg=finish_msg,
    )
    schema = WalkthroughModel.model_json_schema(mode="serialization")
    try:
        from agent.parser.structured_schema import _prepare_ollama_schema

        schema = _prepare_ollama_schema(schema, simplify=True)
    except Exception:
        pass

    result = client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        format=schema,
        stream=False,
        surface="reflect",
        force_think_disabled=True,
    )
    content = ""
    if isinstance(result, dict):
        content = (result.get("message") or {}).get("content") or ""
    try:
        data = json.loads(content)
        model = WalkthroughModel.model_validate(data)
        return model.model_dump(mode="python")
    except Exception:
        return WalkthroughModel(
            summary=finish_msg or f"Completed {task_name}.",
            what_we_did=[tool_summary[:500]] if tool_summary else [],
            why_those_choices=plan_summary[:800],
            how_to_verify=["Review the deliverable and activity log."],
        ).model_dump(mode="python")


def summarize_tool_log(conversation_history: list[dict], *, limit: int = 12) -> str:
    """Extract recent tool/capability result lines from conversation history."""
    lines: list[str] = []
    markers = ("Capability '", "Tool '")
    for msg in reversed(conversation_history):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = str(msg.get("content") or "")
        if role != "user":
            continue
        for marker in markers:
            if marker not in content:
                continue
            for part in content.split(marker)[1:]:
                name = part.split("'")[0] if "'" in part else "action"
                snippet = part[:200].replace("\n", " ")
                prefix = "cap" if marker.startswith("Capability") else "tool"
                lines.append(f"- {prefix}:{name}: {snippet}")
                if len(lines) >= limit:
                    break
            if len(lines) >= limit:
                break
        if len(lines) >= limit:
            break
    return "\n".join(reversed(lines)) if lines else "(no tool log captured)"
