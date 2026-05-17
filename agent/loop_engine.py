"""
Aquila OS 3.3 execution loop: reflect/act turns, budget accounting, step entry ritual.
"""
from __future__ import annotations

import json
import os
import re

from memory_singleton import aquila_memory
from plan_validator import get_step_kind_hint

from main import (
    MAX_TOOLS_PER_TURN,
    REFLECT_SCHEMA,
    advance_json_state,
    complete_ledger_state,
    format_attachment_context,
    parse_agent_response,
    save_task_deliverable,
    read_json_state,
    validate_tool_arguments,
    validate_tool_calls,
)


class LoopEngine:
    def __init__(
        self,
        *,
        client,
        executor,
        console,
        action_schema: dict,
        system_prompt: str,
        mode: str,
        mode_label: str,
        plan_dir: str,
    ):
        self.client = client
        self.executor = executor
        self.console = console
        self.action_schema = action_schema
        self.system_prompt = system_prompt
        self.mode = mode
        self.mode_label = mode_label
        self.plan_dir = plan_dir

    def run(
        self,
        task_name: str,
        user_request: str,
        task_file: str,
        ui_callback=None,
        cancel_check=None,
        text_chunks=None,
        image_payloads=None,
    ) -> str:
        ledger_text = f"Initializing {self.mode.title()} Engine for: {task_name}\n"
        conversation_history: list[dict] = []
        step_count = 0
        max_steps = 50
        attachments_injected = False
        parse_retries = 0
        recent_tool_signatures: list[str] = []
        turn_phase = "act"
        pending_reflect = False
        step_entry_injected = False
        grace_used_this_step = False
        tools_succeeded_this_step: set[str] = set()
        final_step_stalls = 0

        while step_count < max_steps:
            if cancel_check and cancel_check():
                return "🛑 Task was manually aborted by the user."

            try:
                has_finish = False
                state = read_json_state(task_file)
                if state["status"] == "completed":
                    return (
                        f"✅ {self.mode_label} completed successfully. "
                        "Check the directory for final outputs."
                    )

                current_idx = state["current_step_index"]
                if current_idx >= len(state["steps"]):
                    return "✅ All steps are completed."

                step = state["steps"][current_idx]
                current_objective = step["description"]
                max_step_iterations = step.get("max_iterations", 4)
                step_kind = step.get("step_kind", "code")

                step_attempts = sum(
                    1
                    for msg in conversation_history
                    if msg["role"] == "assistant" and msg.get("_counts_as_attempt", True)
                )

                if step_attempts == 0 and not step_entry_injected:
                    conversation_history.extend(
                        self._build_step_entry_messages(task_name, step_kind)
                    )
                    step_entry_injected = True

                user_msg = self._build_user_message(
                    user_request=user_request,
                    current_idx=current_idx,
                    total_steps=len(state["steps"]),
                    current_objective=current_objective,
                    step_attempts=step_attempts,
                    max_step_iterations=max_step_iterations,
                    turn_phase=turn_phase,
                    step_kind=step_kind,
                )

                if step_attempts >= max_step_iterations:
                    if not grace_used_this_step and tools_succeeded_this_step:
                        max_step_iterations += 2
                        step["max_iterations"] = max_step_iterations
                        state["steps"][current_idx] = step
                        with open(task_file, "w", encoding="utf-8") as f:
                            json.dump(state, f, indent=4)
                        grace_used_this_step = True
                        user_msg += (
                            "\n\n⚠️ OS: Budget extended by 2 iterations because tools "
                            "succeeded this step. Finish or save progress soon."
                        )
                        ledger_text += "\n📊 OS: Grace budget extension (+2 iterations).\n"
                    elif current_idx == len(state["steps"]) - 1:
                        user_msg += (
                            "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Output final report "
                            "into `final_report` and use `finish_task`."
                        )
                    else:
                        user_msg += (
                            "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP. Use `save_research_note` "
                            "then use `mark_objective_complete` to move on."
                        )
                elif turn_phase == "reflect":
                    user_msg += (
                        "\n\n**REFLECT TURN:** Summarize tool results and plan next actions. "
                        "Output reasoning only — no tools."
                    )
                else:
                    user_msg += (
                        "\n\nExecute tools to complete objective. Once fully complete, "
                        f"use `mark_objective_complete`.\n"
                        f"(Iteration {step_attempts + 1}/{max_step_iterations})"
                    )

                if not attachments_injected and text_chunks:
                    user_msg += format_attachment_context(text_chunks)
                    attachments_injected = True

                message_dict = self._format_user_message(user_msg, image_payloads)
                active_memory = (
                    [{"role": "system", "content": self.system_prompt}]
                    + conversation_history
                    + [message_dict]
                )

                bt = chr(96) * 3
                prefill_text = f"{bt}json\n" + '{\n  "reasoning": "'
                active_memory.append({"role": "assistant", "content": prefill_text})

                if ui_callback:
                    phase_label = "Reflect" if turn_phase == "reflect" else "Act"
                    ui_callback(
                        f"{ledger_text}\n\n⏳ [Aquila {phase_label} — Iteration {step_count + 1}...]"
                    )

                schema = REFLECT_SCHEMA if turn_phase == "reflect" else self.action_schema
                temperature = 0.3 if turn_phase == "reflect" else 0.2

                result_dict = self.client.chat(
                    active_memory,
                    temperature=temperature,
                    format=schema,
                    stream=False,
                )
                raw_response = ""
                if isinstance(result_dict, dict):
                    raw_response = result_dict.get("message", {}).get("content", "") or ""

                if raw_response.startswith("*(API Error") or raw_response.startswith(
                    "*(System Note"
                ):
                    response_text = raw_response
                else:
                    response_text = prefill_text + raw_response

                self.console.log_iteration(step_count + 1, response_text)
                ledger_text += f"\n\n--- Iteration {step_count + 1} ({turn_phase}) ---\n{response_text}\n"
                if ui_callback:
                    ui_callback(ledger_text)

                counts_as_attempt = True
                conversation_history.append({
                    "role": "assistant",
                    "content": response_text,
                    "_counts_as_attempt": counts_as_attempt,
                })

                parsed_response = parse_agent_response(response_text)

                if turn_phase == "reflect":
                    if not parsed_response.get("reasoning"):
                        parse_retries += 1
                        self._pop_last_assistant(conversation_history)
                        retry_msg = (
                            "Tool Outputs:\n❌ OS PARSE ERROR: Reflect turn requires "
                            "valid JSON with a 'reasoning' string."
                        )
                        conversation_history.append({"role": "user", "content": retry_msg})
                        if parse_retries >= 2:
                            turn_phase = "act"
                            parse_retries = 0
                        continue
                    parse_retries = 0
                    conversation_history.append({
                        "role": "user",
                        "content": (
                            "Tool Outputs:\n✅ Reflection recorded. Now output tool calls "
                            "for your objective (act turn)."
                        ),
                    })
                    turn_phase = "act"
                    pending_reflect = False
                    step_count += 1
                    continue

                parse_ok = bool(parsed_response) and isinstance(
                    parsed_response.get("tools"), list
                )
                if not parse_ok:
                    parse_retries += 1
                    self._pop_last_assistant(conversation_history)
                    retry_msg = (
                        "Tool Outputs:\n❌ OS PARSE ERROR: Your last response was not valid JSON "
                        "with a 'tools' array. Output ONLY a single JSON object matching the schema."
                    )
                    conversation_history.append({"role": "user", "content": retry_msg})
                    ledger_text += f"\n{retry_msg}\n"
                    if ui_callback:
                        ui_callback(ledger_text)
                    if parse_retries >= 2:
                        if self._handle_forced_advance(
                            task_file, current_idx, state, conversation_history
                        ):
                            parse_retries = 0
                            recent_tool_signatures = []
                            step_entry_injected = False
                            grace_used_this_step = False
                            tools_succeeded_this_step = set()
                    continue

                parse_retries = 0

                pending_final_report = parsed_response.get("final_report") or ""

                tool_calls = parsed_response.get("tools", [])
                if not isinstance(tool_calls, list):
                    tool_calls = []

                tool_calls, pending_final_report = self._normalize_tool_calls(
                    tool_calls, pending_final_report
                )

                if pending_final_report:
                    save_task_deliverable(task_name, self.mode, pending_final_report)

                schema_ok, schema_err = validate_tool_calls(tool_calls)
                if not schema_ok:
                    parse_retries += 1
                    self._pop_last_assistant(conversation_history)
                    retry_msg = (
                        f"Tool Outputs:\n❌ OS SCHEMA VIOLATION: {schema_err} "
                        "Constrained decoding requires each tool to use keys "
                        "'name' and 'arguments' only."
                    )
                    conversation_history.append({"role": "user", "content": retry_msg})
                    if parse_retries >= 2 and self._handle_forced_advance(
                        task_file, current_idx, state, conversation_history
                    ):
                        parse_retries = 0
                        recent_tool_signatures = []
                        step_entry_injected = False
                        grace_used_this_step = False
                        tools_succeeded_this_step = set()
                    continue

                args_ok, args_err = validate_tool_arguments(tool_calls)
                if not args_ok:
                    parse_retries += 1
                    self._pop_last_assistant(conversation_history)
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n❌ OS ARGUMENT VIOLATION: {args_err}",
                    })
                    if parse_retries >= 2 and self._handle_forced_advance(
                        task_file, current_idx, state, conversation_history
                    ):
                        parse_retries = 0
                        step_entry_injected = False
                    continue

                if len(tool_calls) > MAX_TOOLS_PER_TURN:
                    tool_calls = tool_calls[:MAX_TOOLS_PER_TURN]

                last_tool_output = ""
                has_advance = False
                has_finish = False
                advance_summary = ""
                finish_msg = ""
                ran_non_meta_tool = False

                for tc in tool_calls:
                    tool_name = tc.get("name", "")
                    if tool_name == "mark_objective_complete":
                        if current_idx == len(state["steps"]) - 1:
                            result = "❌ OS BLOCK: On final step. Use `finish_task`."
                        else:
                            gate = self._tdd_advance_gate(
                                step_kind, conversation_history, last_tool_output
                            )
                            if gate:
                                result = gate + " Run sync_project_to_disk then run_pytest."
                            else:
                                has_advance = True
                                advance_summary = tc.get("arguments", {}).get(
                                    "summary_of_work", "Completed."
                                )
                                result = "✅ State marked complete."
                    elif tool_name == "finish_task":
                        has_finish = True
                        args = tc.get("arguments", {})
                        finish_msg = (
                            args.get("message_to_user")
                            or args.get("summary")
                            or "Task completed."
                        )
                        report_in_args = args.get("final_report")
                        if report_in_args:
                            pending_final_report = report_in_args
                        result = "✅ Finish task triggered."
                    else:
                        ran_non_meta_tool = True
                        execution_results = self.executor.execute([tc])
                        result = execution_results[0] if execution_results else "No output."
                        if result and "❌ Error" not in result:
                            tools_succeeded_this_step.add(tool_name)

                    last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                    self.console.log_tool_execution(
                        tool_name, tc.get("arguments", {}), result
                    )

                if last_tool_output:
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:{last_tool_output}",
                    })
                    ledger_text += f"\n{last_tool_output}\n"
                    if ui_callback:
                        ui_callback(ledger_text)

                if has_advance:
                    advance_json_state(task_file, advance_summary)
                    conversation_history.clear()
                    recent_tool_signatures = []
                    step_entry_injected = False
                    grace_used_this_step = False
                    tools_succeeded_this_step = set()
                    turn_phase = "act"
                    pending_reflect = False

                if has_finish:
                    saved = save_task_deliverable(
                        task_name, self.mode, pending_final_report
                    )
                    complete_ledger_state(task_file, finish_msg)
                    aquila_memory.store_experience(task_name, finish_msg)
                    if saved:
                        finish_msg += f"\n\n📄 Final report saved to: {saved}"
                    return finish_msg

                if (
                    step_attempts >= max_step_iterations
                    and not has_advance
                    and not has_finish
                ):
                    if current_idx == len(state["steps"]) - 1:
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                "Tool Outputs:\n⚠️ OS FORCED: Iteration limit reached on final step. "
                                "You must use finish_task now."
                            ),
                        })
                    elif not self._try_smart_override(
                        task_file,
                        conversation_history,
                        grace_used_this_step,
                        tools_succeeded_this_step,
                    ):
                        advance_json_state(
                            task_file, "OS forced advance (iteration limit)"
                        )
                        conversation_history.clear()
                        recent_tool_signatures = []
                        step_entry_injected = False
                        grace_used_this_step = False
                        tools_succeeded_this_step = set()
                    continue

                for tc in tool_calls:
                    if isinstance(tc, dict):
                        sig = json.dumps(
                            {"name": tc.get("name"), "arguments": tc.get("arguments")},
                            sort_keys=True,
                        )
                        recent_tool_signatures.append(sig)

                dup_msg = self._duplicate_tool_warning(recent_tool_signatures)
                if dup_msg:
                    conversation_history.append({
                        "role": "user",
                        "content": f"Tool Outputs:\n{dup_msg}",
                    })
                    recent_tool_signatures = []

                if ran_non_meta_tool and turn_phase == "act":
                    turn_phase = "reflect"
                    pending_reflect = True

                if current_idx == len(state["steps"]) - 1 and not has_finish:
                    final_step_stalls += 1
                    if final_step_stalls >= 8:
                        complete_ledger_state(
                            task_file, "OS forced completion (final step stall limit)"
                        )
                        return (
                            "⚠️ OS forced task completion: too many retries on the final step."
                        )

                step_count += 1

            except Exception as e:
                return f"OS Error: {str(e)}"

        return "⚠️ OS halted: Maximum iterations reached."

    @staticmethod
    def _normalize_tool_calls(
        tool_calls: list, pending_final_report: str
    ) -> tuple[list, str]:
        """Hoist final_report from finish_task args (legacy shape) before arg validation."""
        report = pending_final_report or ""
        for tc in tool_calls:
            if not isinstance(tc, dict) or tc.get("name") != "finish_task":
                continue
            args = tc.get("arguments")
            if not isinstance(args, dict):
                continue
            if "final_report" in args:
                report = args.pop("final_report") or report
        return tool_calls, report

    def _build_step_entry_messages(self, task_name: str, step_kind: str) -> list[dict]:
        try:
            notes = aquila_memory.get_scratchpad_notes(task_name)
        except Exception:
            notes = "No research notes found for this task."
        hint = get_step_kind_hint(step_kind)
        cwd = os.getcwd()
        parts = [
            f"WORKSPACE_ROOT: {cwd}",
            f"STEP_KIND: {step_kind}",
            f"OS HINT: {hint}",
        ]
        if notes and "No research notes found" not in notes:
            parts.append(f"--- SCRATCHPAD (prior steps) ---\n{notes}\n--- END SCRATCHPAD ---")
        return [{"role": "user", "content": "\n".join(parts)}]

    def _build_user_message(
        self,
        *,
        user_request: str,
        current_idx: int,
        total_steps: int,
        current_objective: str,
        step_attempts: int,
        max_step_iterations: int,
        turn_phase: str,
        step_kind: str,
    ) -> str:
        return (
            f"**Ultimate Topic/Goal:** {user_request}\n\n"
            f"**YOUR CURRENT OBJECTIVE (Step {current_idx + 1} of {total_steps}):**\n"
            f"> {current_objective}\n"
            f"**Step kind:** {step_kind}"
        )

    def _format_user_message(self, user_msg: str, image_payloads) -> dict:
        if image_payloads:
            content_list = [{"type": "text", "text": user_msg}]
            for img_b64 in image_payloads:
                prefix = "data:image/jpeg;base64,"
                clean_b64 = img_b64.split(",", 1)[-1] if "," in img_b64 else img_b64
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"{prefix}{clean_b64}"},
                })
            return {"role": "user", "content": content_list}
        return {"role": "user", "content": user_msg}

    @staticmethod
    def _pop_last_assistant(conversation_history: list[dict]) -> None:
        if conversation_history and conversation_history[-1].get("role") == "assistant":
            conversation_history.pop()

    def _handle_forced_advance(
        self,
        task_file: str,
        current_idx: int,
        state: dict,
        conversation_history: list[dict],
    ) -> bool:
        if current_idx == len(state["steps"]) - 1:
            conversation_history.append({
                "role": "user",
                "content": (
                    "Tool Outputs:\n⚠️ OS OVERRIDE: Parse failures exceeded. "
                    "Put final_report at the top level of your JSON (not inside finish_task) "
                    "and call finish_task with only message_to_user."
                ),
            })
            return False
        advance_json_state(task_file, "OS forced advance (parse failure limit)")
        conversation_history.clear()
        return True

    @staticmethod
    def _try_smart_override(
        task_file: str,
        conversation_history: list[dict],
        grace_used: bool,
        tools_succeeded: set[str],
    ) -> bool:
        """Inject save-and-advance hint before forcing advance. Returns True if injected."""
        if tools_succeeded or grace_used:
            conversation_history.append({
                "role": "user",
                "content": (
                    "Tool Outputs:\n⚠️ OS: Step budget exhausted. "
                    "Call save_research_note with partial progress, then mark_objective_complete."
                ),
            })
            return True
        return False

    @staticmethod
    def _recent_pytest_output(conversation_history: list[dict], current_chunk: str) -> str:
        parts = [current_chunk or ""]
        for msg in reversed(conversation_history):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and "Tool 'run_pytest' result:" in content:
                parts.append(content)
                break
        return "\n".join(parts)

    @staticmethod
    def _tdd_advance_gate(
        step_kind: str,
        conversation_history: list[dict],
        last_tool_output: str,
    ) -> str | None:
        """Soft gates for Code Mode TDD steps."""
        if step_kind not in ("tdd_red", "tdd_green"):
            return None
        blob = LoopEngine._recent_pytest_output(conversation_history, last_tool_output)
        lower = blob.lower()
        if step_kind == "tdd_red":
            if "failed" not in lower and "error" not in lower:
                return (
                    "❌ OS BLOCK (tdd_red): Call run_pytest and confirm failing tests "
                    "(output should mention failed) before mark_objective_complete."
                )
        if step_kind == "tdd_green":
            failed_m = re.search(r"(\d+) failed", blob)
            if failed_m and int(failed_m.group(1)) > 0:
                return (
                    "❌ OS BLOCK (tdd_green): run_pytest must show 0 failed "
                    "before mark_objective_complete."
                )
            if "✅ pytest" not in blob and "passed" not in lower:
                return (
                    "❌ OS BLOCK (tdd_green): Call run_pytest until tests pass "
                    "before mark_objective_complete."
                )
        return None

    @staticmethod
    def _duplicate_tool_warning(recent_tool_signatures: list[str]) -> str | None:
        if len(recent_tool_signatures) < 2:
            return None
        if recent_tool_signatures[-1] == recent_tool_signatures[-2]:
            if len(recent_tool_signatures) >= 3 and recent_tool_signatures[-3] == recent_tool_signatures[-1]:
                return (
                    "⚠️ OS WARNING: You repeated the same tool call three times. "
                    "Use mark_objective_complete or a different tool."
                )
            return (
                "⚠️ OS WARNING: You repeated the same tool call twice. "
                "Try a different approach or mark_objective_complete."
            )
        return None
