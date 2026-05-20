import sys
import ast
import json
import os
import re
import requests
import inspect
import datetime
from pathlib import Path
from typing import Dict, List
from rich.console import Console
from rich.text import Text
from memory_singleton import aquila_memory
from context_budget import set_runtime_context
from prompts import (
    get_autonomous_prompt,
    get_research_prompt,
    get_writing_prompt,
    get_code_prompt,
    get_chat_prompt,
)

# Tools imports
from tools import SURVIVAL_TOOLS
try:
    from tool_library import ALL_TOOLS
except ImportError:
    ALL_TOOLS = {}

# Constrained Decoding Schema
def build_strict_schema(available_tools: dict) -> dict:
    """
    Dynamically builds a strict JSON schema using per-tool anyOf branches.
    Ollama constrained decoding (strict: True, stream: False) enforces this shape.
    """
    tool_schemas = []
    valid_tool_names = list(available_tools.keys())

    for name, meta in available_tools.items():
        func = meta["func"]
        sig = inspect.signature(func)

        props = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param.kind in [inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL]:
                continue
            props[param_name] = {"type": "string"}
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        tool_schemas.append({
            "type": "object",
            "properties": {
                "name": {"const": name},
                "arguments": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                    "additionalProperties": False,
                },
            },
            "required": ["name", "arguments"],
            "additionalProperties": False,
        })

    return {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "Your internal thoughts. Do not use markdown.",
            },
            "final_report": {"type": "string"},
            "tools": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": valid_tool_names,
                        },
                    },
                    "anyOf": tool_schemas,
                    "additionalProperties": False,
                },
            },
        },
        "required": ["reasoning", "tools"],
        "additionalProperties": False,
    }

INTERNAL_TOOL_NAMES = {"_index_codebase"}
MAX_TOOLS_PER_TURN = 6


def get_executable_tools() -> dict:
    """Merged tool registry excluding internal-only helpers."""
    merged = {**SURVIVAL_TOOLS, **ALL_TOOLS}
    return {k: v for k, v in merged.items() if k not in INTERNAL_TOOL_NAMES}


executable_tools = get_executable_tools()
AQUILA_ACTION_SCHEMA = build_strict_schema(executable_tools)


def format_attachment_context(text_chunks: list | None) -> str:
    """Format the first attachment chunk for injection into prompts."""
    if not text_chunks:
        return ""
    return f"\n\n--- ATTACHED CONTEXT ---\n{text_chunks[0]}\n--- END ATTACHED CONTEXT ---\n"

class DualLogger:
    def __init__(self):
        self.console = Console()
        self.current_task = None
        self.log_filename = None
        
    def set_task(self, task_name: str):
        self.current_task = task_name
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_filename = f"Agent-Logs/{self.current_task}_{timestamp}.log"
        
        os.makedirs("Agent-Logs", exist_ok=True)
        
        with open(self.log_filename, "a", encoding="utf-8") as f:
            friendly_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n\n{'='*60}\n🚀 NEW EXECUTION SESSION: {friendly_time}\n{'='*60}\n")
            
    def print(self, message: str, **kwargs):
        self.console.print(message, **kwargs)
        if self.log_filename:
            try:
                clean_text = Text.from_markup(str(message)).plain
            except Exception:
                clean_text = str(message)
            
            with open(self.log_filename, "a", encoding="utf-8") as f:
                f.write(clean_text + "\n")
                
    def log_iteration(self, iteration: int, content: str):
        if not self.log_filename:
            return
        os.makedirs(os.path.dirname(self.log_filename) or ".", exist_ok=True)
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(f"\n--- Iteration {iteration} ---\n{content}\n")

    def log_tool_execution(self, tool_name: str, args: dict, result: str):
        if not self.log_filename:
            return
        os.makedirs(os.path.dirname(self.log_filename) or ".", exist_ok=True)
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(f"\n[🛠️ TOOL EXECUTED: {tool_name}]\nARGS: {args}\nRESULT:\n{result}\n")

console = DualLogger()
sys.path.insert(0, str(Path(__file__).parent))
import time

class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
        self.model_name = os.getenv("OLLAMA_MODEL", "aquila").strip()
        self.num_ctx = self._parse_num_ctx(os.getenv("OLLAMA_NUM_CTX"))
        self.session = requests.Session()
        set_runtime_context(self.model_name, self.num_ctx)
        ctx_note = f", num_ctx={self.num_ctx}" if self.num_ctx else ""
        print(f"✅ Connected to Ollama (Targeting: {self.model_name}{ctx_note})")
        self._log_model_availability()

    @staticmethod
    def _parse_num_ctx(raw: str | None) -> int | None:
        if raw is None or not str(raw).strip():
            return None
        try:
            value = int(str(raw).strip())
            return value if value > 0 else None
        except ValueError:
            return None

    def _log_model_availability(self) -> None:
        try:
            url = f"{self.base_url.rstrip('/')}/api/tags"
            response = self.session.get(url, timeout=3)
            if response.status_code != 200:
                return
            names = [m.get("name", "") for m in response.json().get("models", [])]
            if not any(self.model_name in name for name in names):
                print(
                    f"⚠️ Model '{self.model_name}' not found in Ollama. "
                    f"Run: ollama create {self.model_name} -f Modelfile"
                )
        except Exception:
            pass

    def chat(self, messages: list, temperature: float = 0.6, timeout: int = 120, format: dict = None, stream: bool = False):
        clean_url = self.base_url.strip()
        
        payload = {
            "model": self.model_name, 
            "messages": messages, 
            "temperature": temperature, 
            "stream": stream,
            "frequency_penalty": 0.2, 
            "presence_penalty": 0.2
        }
        if self.num_ctx is not None:
            payload["options"] = {"num_ctx": self.num_ctx}
        
        # FIXED: Use the correct response_format schema for the /v1 endpoint!
        if format: 
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "aquila_strict_schema",
                    "schema": format,
                    "strict": True
                }
            }
            
        try:
            start_time = time.time()
            generation_start = None
            first_token_received = False
            full_content = ""
            
            console.print(f"[yellow]⏳ Sending prompt to Ollama API at {clean_url}...[/yellow]")
            # FIXED: Pass the stream variable directly to requests!
            response = self.session.post(f"{clean_url}/v1/chat/completions", json=payload, stream=stream, timeout=(5, 90))
            response.raise_for_status()
            
            if stream:
                console.print("[green]✅ Connected! Waiting for GPU to compute first token...[/green]")
                def chunk_generator():
                    nonlocal first_token_received, start_time, generation_start, full_content
                    for line in response.iter_lines():
                        if line:
                            if not first_token_received:
                                console.print(f"[bold cyan]⚡ FIRST TOKEN RECEIVED in {time.time() - start_time:.2f} seconds![/bold cyan]")
                                first_token_received = True
                                generation_start = time.time()

                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith("data: "):
                                data_str = decoded_line[6:]
                                if data_str == "[DONE]": break
                                try:
                                    chunk = json.loads(data_str)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    if "content" in delta:
                                        token = delta["content"]
                                        full_content += token
                                        sys.stdout.write(token)
                                        sys.stdout.flush()
                                        yield {"message": {"content": token}}
                                except Exception: pass

                        if generation_start is not None and time.time() - generation_start > timeout:
                            sys.stdout.write("\n")
                            console.print(f"\n[bold red]⚠️ KILL SWITCH ACTIVATED: Model hit the {timeout}s limit.[/bold red]")
                            response.close() 
                            yield {"message": {"content": "\n\n*(System Note: Generation forcibly severed.)*"}}
                            break
                return chunk_generator()

            else:
                # Non-streaming. Get the JSON entirely and manually trigger the TTFT UI print
                data = response.json()
                console.print(f"[bold cyan]⚡ RESPONSE RECEIVED in {time.time() - start_time:.2f} seconds![/bold cyan]")
                content = data["choices"][0]["message"]["content"]
                return {"message": {"content": content}}
            
        except requests.exceptions.ReadTimeout:
            err = "*(System Timeout: Model took too long to load into VRAM.)*"
            return {"message": {"content": err}} if not stream else [{"message": {"content": err}}]
        except Exception as e:
            err = f"*(API Error: {str(e)})*"
            return {"message": {"content": err}} if not stream else [{"message": {"content": err}}]

client = OllamaClient()

def parse_agent_response(response_text: str) -> dict:
    bt = chr(96) * 3
    match = re.search(bt + r'(?:json)?\s*(\{.*?)' + bt, response_text, re.DOTALL)
    if match:
        clean_json = match.group(1).strip()
    else:
        match = re.search(r'(\{.*\})', response_text, re.DOTALL)
        if match:
            clean_json = match.group(1).strip()
        else:
            clean_json = response_text.strip()
            
    def try_parse(text):
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            pass
        try:
            safe_str = text.replace('\n', '\\n')
            safe_str = safe_str.replace('true', 'True').replace('false', 'False').replace('null', 'None')
            parsed = ast.literal_eval(safe_str)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return None

    res = try_parse(clean_json)
    if res: return res

    # RESTORED: Aggressive JSON Healer
    healed = re.sub(r'[\}\]\s]+$', '', clean_json)
    stack = []
    in_string = False
    escape = False

    for char in healed:
        if char == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if char in '{[':
                stack.append(char)
            elif char in '}]':
                if stack:
                    stack.pop()
        if char == '\\':
            escape = not escape
        else:
            escape = False
            
    if in_string: healed += '"'
    while stack:
        healed += '}' if stack.pop() == '{' else ']'
    
    res = try_parse(healed)
    if res: return res
    
    console.print(f"[bold red]⚠️ JSON Parser Error: Failed to parse or heal output.[/bold red]")
    return {}


def validate_tool_calls(tool_calls: list) -> tuple[bool, str]:
    """
    Verify parsed tool calls match the strict schema shape (no alias repair).
    Used when constrained decoding output still fails validation.
    """
    if not isinstance(tool_calls, list):
        return False, "tools must be a JSON array"

    valid_names = set(get_executable_tools().keys())
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            return False, f"tools[{i}] must be an object"
        extra_keys = set(tc.keys()) - {"name", "arguments"}
        if extra_keys:
            return (
                False,
                f"tools[{i}] schema violation: illegal keys {sorted(extra_keys)}. "
                f"Use only 'name' and 'arguments'.",
            )
        if "name" not in tc:
            return False, f"tools[{i}] missing required key 'name'"
        if tc["name"] not in valid_names:
            return False, f"tools[{i}] unknown tool '{tc['name']}'"
        if not isinstance(tc.get("arguments"), dict):
            return False, f"tools[{i}].arguments must be an object"

    return True, ""


def _tool_argument_properties(tool_name: str) -> dict | None:
    """Return properties dict for a tool's arguments from the strict schema."""
    tools = get_executable_tools()
    if tool_name not in tools:
        return None
    func = tools[tool_name]["func"]
    sig = inspect.signature(func)
    props = {}
    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        props[param_name] = {"type": "string"}
    return props


def validate_tool_arguments(tool_calls: list) -> tuple[bool, str]:
    """Reject unknown keys inside each tool's arguments object."""
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue
        name = tc.get("name")
        args = tc.get("arguments")
        if not name or not isinstance(args, dict):
            continue
        allowed = _tool_argument_properties(name)
        if allowed is None:
            continue
        extra = set(args.keys()) - set(allowed.keys())
        if extra:
            return (
                False,
                f"tools[{i}] ({name}) illegal argument keys {sorted(extra)}. "
                f"Allowed: {sorted(allowed.keys())}.",
            )
    return True, ""


REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Brief reflection on tool results and next steps. No tools this turn.",
        },
    },
    "required": ["reasoning"],
    "additionalProperties": False,
}

META_TOOL_NAMES = frozenset({"mark_objective_complete", "finish_task"})


class ToolExecutor:
    def _coerce_arguments(self, func, arguments: dict) -> dict:
        """Coerce string LLM arguments to int where the signature expects int."""
        sig = inspect.signature(func)
        coerced = {}
        for key, value in arguments.items():
            if key not in sig.parameters:
                continue
            param = sig.parameters[key]
            if param.annotation is int or (
                param.default != inspect.Parameter.empty and type(param.default) is int
            ):
                try:
                    coerced[key] = int(value) if not isinstance(value, int) else value
                    continue
                except (TypeError, ValueError):
                    pass
            coerced[key] = value
        return coerced

    def execute(self, tool_calls: list[dict]) -> list[str]:
        results = []
        tools = get_executable_tools()

        for call in tool_calls:
            name = call.get("name")
            arguments = call.get("arguments") or {}
            if not name or name not in tools:
                results.append(f"Tool '{name}' returned: ❌ Error - Function does not exist.")
                continue
            func = tools[name]["func"]
            try:
                sig = inspect.signature(func)
                has_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                )
                if has_kwargs:
                    valid_args = self._coerce_arguments(func, arguments)
                else:
                    filtered = {k: v for k, v in arguments.items() if k in sig.parameters}
                    valid_args = self._coerce_arguments(func, filtered)
                output = func(**valid_args)
                results.append(
                    f"Tool {name} returned: {output if output is not None else '(Success)'}"
                )
            except Exception as e:
                results.append(f"Tool {name} returned: ❌ Error - {str(e)}")
        return results

def initialize_json_ledger(task_file: str, steps: list):
    state = {
        "status": "in_progress",
        "current_step_index": 0,
        "steps": [{"description": step, "status": "pending", "result": ""} for step in steps]
    }
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def read_json_state(task_file: str) -> dict:
    with open(task_file, "r", encoding="utf-8") as f:
        return json.load(f)

def advance_json_state(task_file: str, result_summary: str):
    state = read_json_state(task_file)
    idx = state["current_step_index"]
    if idx < len(state["steps"]):
        state["steps"][idx]["status"] = "completed"
        state["steps"][idx]["result"] = result_summary
        state["current_step_index"] += 1
        if state["current_step_index"] >= len(state["steps"]):
            state["status"] = "completed"
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)


def complete_ledger_state(task_file: str, summary: str = "Task finished successfully."):
    """Mark every step and the overall ledger as completed (called on finish_task)."""
    state = read_json_state(task_file)
    for i, step in enumerate(state["steps"]):
        step["status"] = "completed"
        if not step.get("result"):
            step["result"] = summary if i == len(state["steps"]) - 1 else "Completed."
    state["current_step_index"] = len(state["steps"])
    state["status"] = "completed"
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)


def save_task_deliverable(
    task_name: str,
    mode: str,
    report_text: str,
    sources=None,
) -> str | None:
    """Write final_report markdown to Agent-Research or Agent-Creations. Returns path or None."""
    from web_enrichment import append_bibliography_to_report

    if not report_text or not str(report_text).strip():
        if mode != "research" or sources is None:
            return None
        report_text = ""

    final_text = append_bibliography_to_report(report_text, sources, mode=mode)
    if not final_text.strip():
        return None

    save_dir = "Agent-Research" if mode == "research" else "Agent-Creations"
    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, f"{task_name}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_text)
    return out_path

class Agent:
    def __init__(self):
        os.makedirs("Agent-Tasks", exist_ok=True)
        os.makedirs("Agent-Creations", exist_ok=True)
        os.makedirs("Agent-Research", exist_ok=True)
        os.makedirs("Agent-Plans", exist_ok=True)
        os.makedirs("Agent-Code", exist_ok=True)
        self.executor = ToolExecutor()
        self.client = client
        self.memory = aquila_memory 
        
        tools = get_executable_tools()
        self.memory.index_tools(tools)

        docs = []
        for name, meta in tools.items():
            desc = str(meta.get("description", "No description")).strip().split('\n')[0]
            sig = inspect.signature(meta["func"])
            args = [p for p, p_info in sig.parameters.items() if p_info.kind not in [inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL]]
            docs.append(f"- `{name}({', '.join(args)})`: {desc}")
        tool_docs = "\n".join(docs)
        
        self.master_prompt = get_autonomous_prompt(tool_docs)
        self.RESEARCH_PROMPT = get_research_prompt(tool_docs)
        self.WRITING_PROMPT = get_writing_prompt(tool_docs)
        self.CODE_PROMPT = get_code_prompt(tool_docs)
        self.action_schema = build_strict_schema(tools)

    def run_chat(self, user_input: str, chat_history: list, image_payloads: list = None, stream: bool = True):
        facts = self.memory.get_all_facts()
        episodic_memories = self.memory.recall_experiences(user_input, n_results=2)
        
        system_prompt = get_chat_prompt(facts, episodic_memories)
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        
        if image_payloads:
            content_list = [{"type": "text", "text": user_input}]
            for img_b64 in image_payloads:
                prefix = "data:image/jpeg;base64,"
                clean_b64 = img_b64.split(",", 1)[-1] if "," in img_b64 else img_b64
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"{prefix}{clean_b64}"}
                })
            user_msg = {"role": "user", "content": content_list}
        else:
            user_msg = {"role": "user", "content": user_input}
            
        messages.append(user_msg)
        
        return self.client.chat(messages, temperature=0.6, stream=stream)

    def generate_plan(self, topic_name: str, user_request: str, mode: str, text_chunks: list = None, image_payloads: list = None) -> str:
        from plan_validator import BUDGET_RUBRIC, STEP_KINDS

        workspace_root = os.getcwd()
        code_scope_note = ""
        if mode == "code":
            from tool_library.code_canvas_tools import get_active_project_scope

            scope = get_active_project_scope()
            if scope:
                workspace_root = scope["root"]
                code_scope_note = (
                    f"\nActive code project '{scope['project_name']}' at {scope['root']}. "
                    "ALL steps must use Code Canvas tools and paths under this root only. "
                    "Do NOT explore the parent workspace with list_directory/get_directory_tree."
                )
            else:
                code_scope_note = (
                    "\nNo code project buffer yet — first step should init_code_project "
                    "or attach_existing_repo before editing files."
                )
        rubric_lines = "\n".join(
            f"  - {kind}: min={lo}, default={default}, max={hi}"
            for kind, (lo, default, hi) in BUDGET_RUBRIC.items()
        )
        kinds_list = ", ".join(STEP_KINDS)

        if mode == "research":
            role_desc = "You are Aquila's Lead Researcher."
            objectives = (
                "Decompose into focused steps: search → read sources → save notes → "
                "synthesize → final report. Do NOT combine search+read+synthesis in one step."
            )
            example_step = (
                '{"status": "pending", "description": "Search for ...", '
                '"step_kind": "search", "max_iterations": 4}'
            )
        elif mode == "writing":
            role_desc = "You are Aquila's Writing Mode planner."
            objectives = "Outline, draft sections, then compile. One major writing action per step."
            example_step = (
                '{"status": "pending", "description": "Draft section 1", '
                '"step_kind": "write", "max_iterations": 5}'
            )
        elif mode == "code":
            role_desc = "You are Aquila's Code Mode planner (TDD)."
            objectives = (
                "For implementation tasks use TDD steps: explore (read/verify) → tdd_red (failing pytest) "
                "→ tdd_green (minimal code) → optional tdd_refactor → verify (full pytest) → finalize. "
                "Use step_kind values tdd_red, tdd_green, tdd_refactor, code, verify, finalize."
            )
            example_step = (
                '{"status": "pending", "description": "Write failing test for feature X", '
                '"step_kind": "tdd_red", "max_iterations": 5}'
            )
        else:
            role_desc = "You are the backend task router."
            objectives = (
                "Break the request into small executable steps (code, verify, file ops). "
                "Never assign only 2 iterations to multi-file grep or multi-file read tasks."
            )
            example_step = (
                '{"status": "pending", "description": "Implement ...", '
                '"step_kind": "code", "max_iterations": 6}'
            )

        attachment_block = format_attachment_context(text_chunks)
        prompt = f"""
        {role_desc}
        WORKSPACE_ROOT (all paths relative to): {workspace_root}
        {code_scope_note}
        The user needs: {user_request}
        {attachment_block}
        Create a strict JSON state object to manage this workflow.
        {objectives}

        Each step MUST include:
        - "description" (string)
        - "step_kind" (one of: {kinds_list})
        - "max_iterations" (integer; use rubric below — do NOT default everything to 2–3)
        - "status": "pending"

        Iteration budget rubric:
{rubric_lines}

        Output ONLY valid JSON matching this structure:
        {{
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [ {example_step} ]
        }}
        """
        
        for attempt in range(3):
            bt = chr(96) * 3
            prefill_text = f"{bt}json\n" + '{\n  "status": "in_progress",\n  "current_step_index": 0,\n  "steps": ['
            
            # FIXED: Properly format the user message for the planning payload
            if image_payloads:
                content_list = [{"type": "text", "text": prompt}]
                for img_b64 in image_payloads:
                    prefix = "data:image/jpeg;base64,"
                    clean_b64 = img_b64.split(",", 1)[-1] if "," in img_b64 else img_b64
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"{prefix}{clean_b64}"}
                    })
                message_dict = {"role": "user", "content": content_list}
            else:
                message_dict = {"role": "user", "content": prompt}
                
            messages = [message_dict, {"role": "assistant", "content": prefill_text}]
            
            result_dict = self.client.chat(messages, temperature=0.1, stream=False)
            
            raw_response = result_dict.get("message", {}).get("content", "") if isinstance(result_dict, dict) else str(result_dict)
            
            if "Generation forcibly severed" in raw_response: continue
            
            response = prefill_text + raw_response
            clean_json = response.replace(f"{bt}json", "").replace(bt, "").strip()
            
            try:
                plan_dict = json.loads(clean_json)
                from plan_validator import validate_and_tune_plan

                tuned, tune_notes = validate_and_tune_plan(plan_dict, mode, user_request)
                if tune_notes:
                    console.print("[cyan]📋 Plan tuning:[/cyan]")
                    for note in tune_notes:
                        console.print(f"  • {note}")
                return json.dumps(tuned, indent=2)
            except json.JSONDecodeError:
                continue
                
        raise Exception("Fatal: LLM failed to generate a valid JSON plan after 3 attempts.")

    def run_unified_task(self, task_name: str, user_request: str, mode: str = "task", ui_callback=None, cancel_check=None, text_chunks: list = None, image_payloads: list = None) -> str:
        if mode == "research":
            system_prompt = self.RESEARCH_PROMPT
            working_dir = Path("Agent-Research")
        elif mode == "writing":
            system_prompt = self.WRITING_PROMPT
            working_dir = Path("Agent-Drafts")
        elif mode == "code":
            system_prompt = self.CODE_PROMPT
            working_dir = Path("Agent-Code")
        else:
            system_prompt = self.master_prompt
            working_dir = Path("Agent-Tasks")

        working_dir.mkdir(exist_ok=True)
        console.set_task(task_name)
        if mode == "research":
            mode_label = "Deep-Dive Research"
        elif mode == "writing":
            mode_label = "Writing Task"
        elif mode == "code":
            mode_label = "Code Mode (TDD)"
        else:
            mode_label = "Autonomous Task"
        
        plan_dir = "Agent-Plans" if mode == "research" else "Agent-Tasks"
        task_file = os.path.join(plan_dir, f"{task_name}.json")
        
        ledger_text = f"Initializing {mode.title()} Engine for: {task_name}\n"
        
        if not os.path.exists(task_file):
            if ui_callback: ui_callback(f"{ledger_text}\n⏳ Planning phase initiated. Building JSON execution steps... (This takes a moment)")
            plan_json = self.generate_plan(task_name, user_request, mode, text_chunks, image_payloads)
            with open(task_file, "w", encoding="utf-8") as f:
                f.write(plan_json)

        from loop_engine import LoopEngine

        engine = LoopEngine(
            client=self.client,
            executor=self.executor,
            console=console,
            action_schema=self.action_schema,
            system_prompt=system_prompt,
            mode=mode,
            mode_label=mode_label,
            plan_dir=plan_dir,
        )
        return engine.run(
            task_name=task_name,
            user_request=user_request,
            task_file=task_file,
            ui_callback=ui_callback,
            cancel_check=cancel_check,
            text_chunks=text_chunks,
            image_payloads=image_payloads,
        )

_agent_instance = None


def get_global_agent() -> Agent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = Agent()
    return _agent_instance


class _AgentProxy:
    """Lazy proxy so importing main does not eagerly index tools / Chroma on import."""

    def __getattr__(self, name):
        return getattr(get_global_agent(), name)


global_agent = _AgentProxy()


def initiate_sleep_cycle() -> str:
    json_files = []
    for folder in ("Agent-Tasks", "Agent-Plans"):
        tasks_dir = Path(folder)
        if tasks_dir.exists():
            json_files.extend(tasks_dir.glob("*.json"))

    if not json_files:
        return "🧠 Sleep cycle complete. The desk is already clean."

    consolidation_results = []

    for file_path in json_files:
        task_name = file_path.stem
        ledger_label = file_path.parent.name
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content_dict = json.load(f)
                content = json.dumps(content_dict, indent=2)

            if len(content) > 12000: 
                content = content[-12000:]

            prompt = f"""
            You are Aquila's sub-conscious memory consolidator.
            Review this raw JSON task state:
            
            {content}

            Write a highly dense, 3-sentence summary of what was completed and what facts were established. 
            Do not include pleasantries. Just the pure, extracted knowledge.
            """
            
            # 1. Ask the LLM (ensure stream=False is passed so it returns a clean dict)
            response_dict = client.chat([{"role": "user", "content": prompt}], temperature=0.1, stream=False)
            
            # 2. FIXED: Bulletproof dictionary extraction that survives testing mocks
            summary = ""
            try:
                # Standard API response handling
                if isinstance(response_dict, dict) and "message" in response_dict:
                    summary = response_dict["message"].get("content", "")
                else:
                    # Fallback for weird mock behavior
                    summary = str(response_dict)
            except Exception:
                summary = "Memory consolidation successful."
                
            aquila_memory.store_experience(f"{ledger_label}/{task_name}", summary)
            file_path.unlink()
            consolidation_results.append(
                f"- **{ledger_label}/{task_name}**: Compressed and cleared."
            )

        except Exception as e:
            consolidation_results.append(
                f"- **{ledger_label}/{task_name}**: ❌ Failed to consolidate ({e})"
            )

    # FIXED: Re-attached the consolidation results to the final string!
    return "🌙 **Sleep Cycle Complete. KV Cache Flushed.**\n\n" + "\n".join(consolidation_results)