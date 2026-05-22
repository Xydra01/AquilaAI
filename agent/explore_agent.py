"""Read-only pre-plan reconnaissance subagent (Aquila 3.4)."""
from __future__ import annotations

from dataclasses import dataclass, field

from context_budget import get_context_profile
from context_manager import estimate_messages_tokens
from main import (
    JSON_REASONING_PREFILL,
    assemble_agent_response,
    build_strict_schema,
    parse_agent_response,
    get_executable_tools,
    validate_tool_arguments,
    validate_tool_calls,
)
from tool_policy import EXPLORE_TOOLS, META_TOOLS

MAX_TOOLS_PER_EXPLORE_TURN = 4
MAX_PARSE_RETRIES_PER_TURN = 2


@dataclass
class ExplorationBrief:
    relevant_paths: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    suggested_plan_sketch: str = ""

    def to_markdown(self) -> str:
        lines = ["## Exploration brief", ""]
        if self.relevant_paths:
            lines.append("**Relevant paths:** " + ", ".join(self.relevant_paths[:20]))
        if self.hypotheses:
            lines.append("**Hypotheses:**")
            lines.extend(f"- {h}" for h in self.hypotheses[:8])
        if self.risks:
            lines.append("**Risks:**")
            lines.extend(f"- {r}" for r in self.risks[:8])
        if self.suggested_plan_sketch:
            lines.append(f"**Plan sketch:** {self.suggested_plan_sketch}")
        return "\n".join(lines)


def _explore_tool_subset() -> dict:
    all_tools = get_executable_tools()
    allowed = EXPLORE_TOOLS - META_TOOLS
    return {k: v for k, v in all_tools.items() if k in allowed}


def _max_turns_for_tier() -> int:
    tier = get_context_profile().tier
    if tier == "max":
        return 8
    if tier == "extended":
        return 5
    return 3


def _os_error_text(raw: str) -> bool:
    return raw.startswith("*(API Error") or raw.startswith("*(System")


def _unreachable_text(raw: str) -> bool:
    low = raw.lower()
    return "not reachable" in low or "actively refused" in low or "connection refused" in low


def _pop_last_assistant(messages: list[dict]) -> None:
    if messages and messages[-1].get("role") == "assistant":
        messages.pop()


_explore_runtime: dict = {}


def set_explore_runtime(**kwargs) -> None:
    global _explore_runtime
    _explore_runtime = dict(kwargs)


def get_explore_runtime() -> dict:
    return dict(_explore_runtime)


def run_brief(
    *,
    client,
    executor,
    user_request: str,
    mode: str,
    instance_id: str,
    memory,
    max_turns: int | None = None,
    console=None,
) -> ExplorationBrief:
    max_turns = max_turns or _max_turns_for_tier()
    tools = _explore_tool_subset()
    if not tools:
        return _brief_from_findings([], user_request)

    explore_names = set(tools.keys())
    schema = build_strict_schema(tools)
    bt = chr(96) * 3
    prefill = f"{bt}json\n{JSON_REASONING_PREFILL}"

    code_recon = (
        " For code mode: first tool call SHOULD be get_directory_tree(path='.', max_depth=2) "
        "or read_code_outline — do not re-list directories in the main loop."
        if mode == "code"
        else ""
    )
    system = (
        "You are Aquila's read-only explore subagent. Reconnaissance only — map the workspace "
        "before the main task. Each turn output ONE JSON object with string reasoning and a "
        "tools array (max 4 tools). Prefer get_directory_tree then read_code_outline for repos; "
        "use read_file_region, index_codebase_for_search, web_search as needed. "
        "Avoid repeated list_directory. No finish_task."
        f"{code_recon}\nMode: {mode}. Instance: {instance_id}."
    )
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_request},
    ]
    findings: list[str] = []
    schema_failures = 0
    successful_tool_turns = 0

    for turn_idx in range(max_turns):
        parse_retries = 0
        turn_had_tools = False

        while parse_retries <= MAX_PARSE_RETRIES_PER_TURN:
            use_schema = schema if schema_failures < 2 else None
            turn_messages = messages + [{"role": "assistant", "content": prefill}]
            est = estimate_messages_tokens(turn_messages)
            result = client.chat(
                turn_messages,
                temperature=0.2,
                format=use_schema,
                stream=False,
                estimated_prompt_tokens=est,
            )
            raw = ""
            if isinstance(result, dict):
                raw = result.get("message", {}).get("content", "") or ""

            if _os_error_text(raw):
                if _unreachable_text(raw):
                    if console:
                        console.print(
                            f"[bold red]Explore brief skipped — Ollama offline at turn "
                            f"{turn_idx + 1}.[/bold red]"
                        )
                    return _brief_from_findings(findings, user_request)
                if console:
                    console.print(
                        f"[yellow]Explore brief (turn {turn_idx + 1}): {raw[:400]}[/yellow]"
                    )
                schema_failures = max(schema_failures, 2)
                parse_retries += 1
                if parse_retries <= MAX_PARSE_RETRIES_PER_TURN:
                    continue
                break

            response_text = assemble_agent_response(prefill, raw)
            parsed = parse_agent_response(response_text, quiet=True)

            from main import normalize_tool_calls_list

            raw_tools = parsed.get("tools") if isinstance(parsed, dict) else None
            parse_ok = bool(parsed) and isinstance(raw_tools, list)
            if parse_ok:
                tool_calls = normalize_tool_calls_list(raw_tools)
                if tool_calls != raw_tools:
                    parsed["tools"] = tool_calls
                for item in tool_calls:
                    if not isinstance(item, dict) or "name" not in item:
                        parse_ok = False
                        break
            if not parse_ok:
                parse_retries += 1
                schema_failures += 1
                if parse_retries <= MAX_PARSE_RETRIES_PER_TURN:
                    _pop_last_assistant(messages)
                    messages.append({
                        "role": "user",
                        "content": (
                            "Tool Outputs:\n❌ OS PARSE ERROR: Output ONLY valid JSON with "
                            "'reasoning' (string) and 'tools' (array). No markdown."
                        ),
                    })
                    continue
                break

            schema_failures = 0
            tool_calls = parsed.get("tools") or []
            schema_ok, schema_err = validate_tool_calls(
                tool_calls, valid_names=explore_names
            )
            if not schema_ok:
                parse_retries += 1
                if parse_retries <= MAX_PARSE_RETRIES_PER_TURN:
                    messages.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n❌ OS SCHEMA VIOLATION: {schema_err}",
                    })
                    continue
                break

            args_ok, args_err = validate_tool_arguments(tool_calls)
            if not args_ok:
                parse_retries += 1
                if parse_retries <= MAX_PARSE_RETRIES_PER_TURN:
                    messages.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n❌ OS ARGUMENT VIOLATION: {args_err}",
                    })
                    continue
                break

            reasoning = parsed.get("reasoning", "")
            if reasoning:
                findings.append(reasoning)

            messages.append({"role": "assistant", "content": response_text})

            if not tool_calls:
                return _finish_brief(findings, user_request, memory, mode)

            executed = 0
            last_output = ""
            for tc in tool_calls[:MAX_TOOLS_PER_EXPLORE_TURN]:
                if not isinstance(tc, dict):
                    continue
                name = tc.get("name", "")
                if name in META_TOOLS:
                    continue
                results = executor.execute([tc])
                last_output = results[0] if results else ""
                findings.append(f"{name}: {last_output[:500]}")
                executed += 1

            if executed:
                turn_had_tools = True
                successful_tool_turns += 1
                messages.append({
                    "role": "user",
                    "content": f"Tool Outputs:\n{last_output}",
                })
            break

        if not turn_had_tools and parse_retries > MAX_PARSE_RETRIES_PER_TURN:
            if console:
                console.print(
                    f"[yellow]Explore brief: stopping after turn {turn_idx + 1} "
                    "(could not obtain valid tool JSON).[/yellow]"
                )
            break

    if console and successful_tool_turns:
        console.print(
            f"[cyan]🔍 Explore brief: {successful_tool_turns} tool turn(s), "
            f"{len(findings)} finding(s).[/cyan]"
        )

    return _finish_brief(findings, user_request, memory, mode)


def _finish_brief(findings: list[str], user_request: str, memory, mode: str) -> ExplorationBrief:
    brief = _brief_from_findings(findings, user_request)
    memory.save_scratchpad_note(
        f"__explore_brief__{mode}",
        brief.to_markdown(),
    )
    return brief


def _brief_from_findings(findings: list[str], user_request: str) -> ExplorationBrief:
    blob = "\n".join(findings)
    paths = []
    for token in blob.replace("\\", "/").split():
        if "/" in token or token.endswith((".py", ".md", ".ts", ".js", ".json")):
            clean = token.strip("',\"[]()")
            if len(clean) < 120:
                paths.append(clean)
    paths = list(dict.fromkeys(paths))[:15]
    return ExplorationBrief(
        relevant_paths=paths,
        hypotheses=[user_request[:200]] if user_request else [],
        risks=["Verify scope before mutating files"] if paths else [],
        suggested_plan_sketch=blob[:800] if blob else "Run explore step then implement.",
    )
