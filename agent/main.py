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
from memory import DualMemorySystem
from prompts import get_autonomous_prompt, get_research_prompt, get_writing_prompt

# Tools imports
from tools import SURVIVAL_TOOLS
try:
    from tool_library import ALL_TOOLS
except ImportError:
    ALL_TOOLS = {}

# Constrained Decoding Schema
def build_strict_schema(available_tools: dict) -> dict:
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
                    "additionalProperties": False
                }
            },
            "required": ["name", "arguments"],
            "additionalProperties": False
        })

    return {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "Your internal thoughts. Do not use markdown."
            },
            "final_report": {
                "type": "string"
            },
            "tools": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": valid_tool_names 
                        }
                    },
                    "anyOf": tool_schemas
                }
            }
        },
        "required": ["reasoning", "tools"],
        "additionalProperties": False
    }

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
        if not self.log_filename: return
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(f"\n--- Iteration {iteration} ---\n{content}\n")

    def log_tool_execution(self, tool_name: str, args: dict, result: str):
        if not self.log_filename: return
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(f"\n[🛠️ TOOL EXECUTED: {tool_name}]\nARGS: {args}\nRESULT:\n{result}\n")

aquila_memory = DualMemorySystem()
console = DualLogger()
sys.path.insert(0, str(Path(__file__).parent))
import time

class OllamaClient:
    def __init__(self):
        self.base_url = "http://127.0.0.1:11434" 
        self.model_name = "aquila" 
        self.session = requests.Session()
        print(f"✅ Connected to Ollama (Targeting: {self.model_name})")
    
    def chat(self, messages: list, temperature: float = 0.6, timeout: int = 120, format: dict = None, stream: bool = False):
        import time
        import json
        import sys
        import requests

        payload = {
            "model": self.model_name, 
            "messages": messages, 
            "temperature": temperature, 
            "stream": True,
            "frequency_penalty": 0.2, 
            "presence_penalty": 0.2
        }
        
        if format: payload["format"] = format
            
        try:
            start_time = time.time()
            first_token_received = False
            full_content = ""
            
            console.print(f"[yellow]⏳ Sending prompt to Ollama API at {self.base_url}...[/yellow]")
            response = self.session.post(f"{self.base_url}/v1/chat/completions", json=payload, stream=True, timeout=(5, 90))
            response.raise_for_status()
            console.print("[green]✅ Connected! Waiting for GPU to compute first token...[/green]")

            if stream:
                def chunk_generator():
                    nonlocal start_time, first_token_received
                    for line in response.iter_lines():
                        if line:
                            if not first_token_received:
                                console.print(f"[bold cyan]⚡ FIRST TOKEN RECEIVED in {time.time() - start_time:.2f} seconds![/bold cyan]")
                                first_token_received = True

                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith("data: "):
                                data_str = decoded_line[6:]
                                if data_str == "[DONE]": break
                                try:
                                    chunk = json.loads(data_str)
                                    delta = chunk["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        token = delta["content"]
                                        sys.stdout.write(token)
                                        sys.stdout.flush()
                                        yield {"message": {"content": token}}
                                except Exception: pass
                return chunk_generator()

            else:
                for line in response.iter_lines():
                    if line:
                        if not first_token_received:
                            console.print(f"[bold cyan]⚡ FIRST TOKEN RECEIVED in {time.time() - start_time:.2f} seconds![/bold cyan]")
                            first_token_received = True
                            start_time = time.time() 

                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data: "):
                            data_str = decoded_line[6:]
                            if data_str == "[DONE]": break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    token = delta["content"]
                                    full_content += token
                                    sys.stdout.write(token)
                                    sys.stdout.flush()
                            except Exception: pass

                    if time.time() - start_time > timeout:
                        sys.stdout.write("\n")
                        console.print(f"\n[bold red]⚠️ KILL SWITCH ACTIVATED: Model hit the {timeout}s limit.[/bold red]")
                        response.close() 
                        return full_content.strip() + "\n\n*(System Note: Generation forcibly severed.)*"
                
                sys.stdout.write("\n")
                return full_content.strip()
                
        except requests.exceptions.ReadTimeout:
            return "*(System Timeout: Model took too long to load into VRAM.)*"
        except Exception as e:
            return f"*(API Error: {str(e)})*"

client = OllamaClient()

def parse_agent_response(response_text: str) -> dict:
    # 1. Extract JSON block (Removed the closing brace constraint to catch truncated JSON)
    bt = chr(96) * 3
    match = re.search(bt + r'(?:json)?\s*(\{.*)' + bt, response_text, re.DOTALL)
    if match:
        clean_json = match.group(1).strip()
    else:
        match = re.search(r'(\{.*)', response_text, re.DOTALL)
        if match:
            clean_json = match.group(1).strip()
        else:
            clean_json = response_text.strip()
        
# 2. Try Standard Parsing
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

    # 3. Aggressive JSON Healer (Fixes Ollama grammar desync cutoffs)
    # Strip corrupted trailing brackets and whitespace
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
        
    if in_string:
        healed += '"'
    
    while stack:
        healed += '}' if stack.pop() == '{' else ']'
    
    res = try_parse(healed)
    if res: return res

    return {}

class ToolExecutor:
    def execute(self, tool_calls: list[dict]) -> list[str]:
        results = []
        executable_tools = {**SURVIVAL_TOOLS, **ALL_TOOLS}

        for call in tool_calls:
            name = call.get("name")
            arguments = call.get("arguments") or {} 
            if not name or name not in executable_tools:
                results.append(f"Tool '{name}' returned: ❌ Error - Function does not exist.")
                continue
            func = executable_tools[name]["func"]
            try:
                sig = inspect.signature(func)
                has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                valid_args = arguments if has_kwargs else {k: v for k, v in arguments.items() if k in sig.parameters}
                output = func(**valid_args)
                results.append(f"Tool {name} returned: {output if output is not None else '(Success)'}")
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

def generate_tool_docs(available_tools: dict) -> str:
    docs = []
    for name, meta in available_tools.items():
        desc = str(meta.get("description", "No description")).strip().split('\n')[0]
        func = meta["func"]
        sig = inspect.signature(func)
        args = [p for p, p_info in sig.parameters.items() if p_info.kind not in [inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL]]
        docs.append(f"- `{name}({', '.join(args)})`: {desc}")
    return "\n".join(docs)

class Agent:
    def __init__(self):
        os.makedirs("Agent-Tasks", exist_ok=True)
        os.makedirs("Agent-Creations", exist_ok=True)
        os.makedirs("Agent-Research", exist_ok=True)
        os.makedirs("Agent-Plans", exist_ok=True)
        
        self.executor = ToolExecutor()
        self.client = client
        self.memory = aquila_memory 
        
        executable_tools = {**SURVIVAL_TOOLS, **ALL_TOOLS}
        aquila_memory.index_tools(executable_tools)
        
        tool_docs = generate_tool_docs(executable_tools)
        
        self.master_prompt = get_autonomous_prompt(tool_docs)
        self.RESEARCH_PROMPT = get_research_prompt(tool_docs)
        self.WRITING_PROMPT = get_writing_prompt(tool_docs)

    def generate_plan(self, topic_name: str, user_request: str, mode: str, text_chunks: list = None, image_payloads: list = None) -> str:
        if mode == "research":
            role_desc = "You are Aquila's Lead Researcher."
            objectives = "Focus on formulating searches, extracting technical data, and cross-referencing."
            example_steps = '{"status": "pending", "description": "Search for X...", "max_iterations": 3}, {"status": "pending", "description": "Compile report...", "max_iterations": 2}'
        elif mode == "writing":
            role_desc = "You are Aquila's Lead Author."
            objectives = "Break the document down into logical sections to draft sequentially using the init_document and write_section tools."
            example_steps = '{"status": "pending", "description": "Draft Section 1...", "max_iterations": 3}'
        else:
            role_desc = "You are the backend task router."
            objectives = "Break the request down into a sequence of specific, executable coding or filing steps."
            example_steps = '{"status": "pending", "description": "Create files...", "max_iterations": 2}'

        prompt = f"""
        {role_desc}
        The user needs: {user_request}

        Create a strict JSON state object to manage this workflow.
        {objectives}

        CRITICAL TASK DECOMPOSITION RULES:
        1. NEVER compress a multi-part user request into a single step.
        2. You MUST decompose complex requests into a minimum of 3 to 5 highly specific, sequential steps.
        3. Isolate variables: If a user asks for multiple distinct things (e.g., "Story updates" AND "Character releases"), you MUST separate them into completely different steps.
        4. You MUST add a final dedicated step to "Compile data, format the final output, and finish the task."
        5. For every step, assign a reasonable "max_iterations" integer (usually 2 to 4).

        Output ONLY valid JSON matching this structure:
        {{
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [ {example_steps} ]
        }}
        """

        # --- NEW: Inject files into the Planner so it can plan around the attachments ---
        augmented_prompt = prompt
        if text_chunks:
            augmented_prompt += f"\n\n[USER ATTACHED FILE CONTEXT (Part 1/{len(text_chunks)})]:\n" + text_chunks[0]
            if len(text_chunks) > 1:
                augmented_prompt += "\n\n(System Note: Additional file chunks exist. Account for them in your plan if necessary.)"

        for attempt in range(3):
            # Using the '{' prefill trick to prevent Ollama from hanging!
            message_dict = {"role": "user", "content": augmented_prompt}
            if image_payloads:
                message_dict["images"] = image_payloads
                
            messages = [message_dict, {"role": "assistant", "content": "{"}]
            response = self.client.chat(messages, temperature=0.1, format="json")
            
            if "Generation forcibly severed" in response: 
                continue
            
            clean_json = "{" + response.replace("```json", "").replace("```", "").strip()
            
            try:
                json.loads(clean_json)
                return clean_json 
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
        else:
            system_prompt = self.master_prompt
            working_dir = Path("Agent-Tasks")

        working_dir.mkdir(exist_ok=True)
        console.set_task(task_name)
        mode_label = "Deep-Dive Research" if mode == "research" else "Autonomous Task"
        
        plan_dir = "Agent-Plans" if mode == "research" else "Agent-Tasks"
        task_file = os.path.join(plan_dir, f"{task_name}.json")
        
        ledger_text = f"Initializing {mode.title()} Engine for: {task_name}\n"
        
        if not os.path.exists(task_file):
            if ui_callback: ui_callback(f"{ledger_text}\n⏳ Planning phase initiated. Building JSON execution steps... (This takes a moment)")
            # --- Pass attachments down to the planner ---
            plan_json = self.generate_plan(task_name, user_request, mode, text_chunks, image_payloads)
            
            try:
                plan_data = json.loads(plan_json)
                plan_data["sources"] = []
                with open(task_file, "w", encoding="utf-8") as f:
                    json.dump(plan_data, f, indent=4)
            except Exception:
                with open(task_file, "w", encoding="utf-8") as f:
                    f.write(plan_json)

        conversation_history = []
        step_count = 0
        max_steps = 50

        while step_count < max_steps:
            if cancel_check and cancel_check():
                return "🛑 Task was manually aborted by the user."
            try:
                state = read_json_state(task_file)
                
                # --- NEW: Sync bibliography with persistent state ---
                bibliography = state.get("sources", [])
                visited_urls = set(bibliography)
                
                if state["status"] == "completed":
                    return f"✅ {mode_label} completed successfully. Check the directory for final outputs."
                    
                current_idx = state["current_step_index"]
                if current_idx >= len(state["steps"]):
                    return "✅ All steps are completed."
                    
                current_objective = state["steps"][current_idx]["description"]
                max_step_iterations = state["steps"][current_idx].get("max_iterations", 4)
                
                step_attempts = sum(1 for msg in conversation_history if msg["role"] == "assistant")
                user_msg = f"**Ultimate Topic/Goal:** {user_request}\n\n**YOUR CURRENT OBJECTIVE (Step {current_idx + 1} of {len(state['steps'])}):**\n> {current_objective}"

                # --- NEW: Auto-Inject the Uploaded File Context ---
                if text_chunks:
                    user_msg += f"\n\n[USER ATTACHED FILE CONTEXT (Part 1/{len(text_chunks)})]:\n" + text_chunks[0]
                    if len(text_chunks) > 1:
                        user_msg += "\n\n(System Note: Additional file chunks exist. The OS will automatically rotate them into your context if you request the next chunk.)"

                # --- NEW: Auto-Inject the Document Outline ---
                if mode == "writing":
                    draft_file = Path("Agent-Drafts/active_draft_state.json")
                    if draft_file.exists():
                        try:
                            with open(draft_file, "r", encoding="utf-8") as df:
                                draft_state = json.load(df)
                                if draft_state.get("sections"):
                                    user_msg += "\n\n📄 **CURRENT DOCUMENT STATUS (Do not rewrite these):**\n"
                                    for i, sec in enumerate(draft_state["sections"]):
                                        user_msg += f"- Section {i+1}: {sec.get('header', 'Untitled')} (Already drafted)\n"
                        except Exception:
                            pass

                # --- NEW: Bibliography Injection for Final Step ---
                if current_idx == len(state['steps']) - 1 and bibliography:
                    user_msg += "\n\n📚 OS BIBLIOGRAPHY TRACKER:\nThe OS has automatically tracked the sources you read. You MUST include a 'Sources' or 'References' section at the bottom of your final report containing these URLs:\n- " + "\n- ".join(bibliography)
                
                if step_attempts > max_step_iterations:
                    console.print(f"[bold red]🚨 FATAL: Agent trapped in loop. Hard-advancing state automatically![/bold red]")
                    if current_idx == len(state['steps']) - 1:
                        return "⚠️ Task forcefully terminated by OS due to infinite loop on the final step."
                    else:
                        advance_json_state(task_file, "Hard-advanced by OS Enforcer (Infinite Loop Prevented).")
                        conversation_history = [] 
                        step_count += 1
                        continue

                elif step_attempts == max_step_iterations:
                    console.print(f"[bold red]⏰ OS ENFORCER: Iteration budget ({max_step_iterations}) exhausted for Step {current_idx + 1}. Issuing final warning![/bold red]")
                    if current_idx == len(state['steps']) - 1:
                        user_msg += "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP FOR THIS FINAL OBJECTIVE.\nYou MUST ONLY use the compile_final_document and finish_task tools right now. Do not do anything else."
                    else:
                        user_msg += "\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP FOR THIS OBJECTIVE.\nYou MUST ONLY use the mark_objective_complete tool right now to move on. Do not use any other tools."
                else:
                    user_msg += f"\n\nExecute tools to complete this specific objective. Once fully complete, use the mark_objective_complete tool to advance.\n(Iteration {step_attempts + 1}/{max_step_iterations} for this step)"

                # --- NEW: Inject Multi-Modal Image Payloads into the Message Dictionary ---
                message_dict = {"role": "user", "content": user_msg}
                if image_payloads:
                    message_dict["images"] = image_payloads

                active_memory = [{"role": "system", "content": system_prompt}] + conversation_history + [message_dict]
            
                # Assistant Prefill to stop Ollama JSON hangs
                active_memory.append({"role": "assistant", "content": "{"})
                
                if ui_callback:
                    ui_callback(f"{ledger_text}\n\n⏳ [Aquila is processing Iteration {step_count + 1}...]")

                raw_response = ""
                loop_detected = False
                
                # NEW: Streaming chat to allow infinite time with intelligent loop detection
                for chunk in self.client.chat(active_memory, temperature=0.2, format=build_strict_schema({**SURVIVAL_TOOLS, **ALL_TOOLS}), stream=True):
                    token = chunk.get("message", {}).get("content", "")
                    raw_response += token
                    
                    # Every 50 chars, check for the Autoregressive Spiral
                    if len(raw_response) > 300 and len(raw_response) % 50 == 0:
                        words = raw_response.split()
                        if len(words) >= 20:
                            # Grab the most recent 15 words (roughly one full sentence)
                            recent_phrase = " ".join(words[-15:])
                            
                            # If this exact 15-word phrase has been generated 4 times, she is stuck!
                            if raw_response.count(recent_phrase) >= 4:
                                console.print("[bold red]⚠️ SPIRAL DETECTED: Severing generation to prevent infinite loop![/bold red]")
                                loop_detected = True
                                break
                                
                # If we severed a loop, forcefully append closing quotes/brackets so the Auto-Healer can stitch it
                if loop_detected:
                    raw_response += '"}' 
                    
                # Re-attach the bracket we prefilled
                response_text = "{" + raw_response 
                
                console.log_iteration(step_count + 1, response_text)
                ledger_text += f"\n\n--- Iteration {step_count + 1} ---\n{response_text}\n"
                
                if ui_callback: ui_callback(ledger_text)

                conversation_history.append({"role": "assistant", "content": response_text})

                parsed_response = parse_agent_response(response_text)
                
                if not parsed_response:
                    error_msg = "❌ OS Error: Your response was invalid JSON. Please ensure your commas and brackets are correct, and try again."
                    conversation_history.append({"role": "user", "content": error_msg})
                    ledger_text += f"\n{error_msg}\n"
                    if ui_callback: ui_callback(ledger_text)
                    step_count += 1
                    continue
                
                if parsed_response.get("final_report"):
                    save_dir = "Agent-Research" if mode == "research" else "Agent-Creations"
                    with open(f"{save_dir}/{task_name}.md", "w", encoding="utf-8") as f:
                        f.write(parsed_response["final_report"])
                
                tool_calls = parsed_response.get("tools", [])
                if not isinstance(tool_calls, list): tool_calls = []
                    
                last_tool_output = ""
                has_advance = False
                has_finish = False
                advance_summary = ""
                finish_msg = ""
                
                for tc in tool_calls:
                    # --- NEW: Loudly catch string-based tool hallucinations ---
                    if not isinstance(tc, dict): 
                        error_msg = "❌ OS Error: Tool calls MUST be JSON objects with 'name' and 'arguments' keys. Do NOT use string function calls like 'tool_name()'."
                        last_tool_output += f"\nMalformed Tool Error:\n{error_msg}\n"
                        continue
                        
                    tool_name = tc.get("name", tc.get("tool_name", tc.get("tool", "")))
                    tc["name"] = tool_name 
                    
                    if not tool_name:
                        result = "❌ OS Error: Tool call missing 'name' attribute."
                    elif tool_name == "mark_objective_complete":
                        if current_idx == len(state['steps']) - 1:
                            result = "❌ OS BLOCK: On final step. Use [START_REPORT]...[END_REPORT] and `finish_task`."
                        else:
                            has_advance = True
                            advance_summary = tc.get("arguments", {}).get("summary_of_work", "Completed.")
                            result = "✅ State marked complete."
                    elif tool_name == "finish_task":
                        has_finish = True
                        args = tc.get("arguments", {})
                        finish_msg = args.get("message_to_user", args.get("summary", "Task completed."))
                        result = "✅ Finish task triggered."
                    else:
                        execution_results = self.executor.execute([tc])
                        result = execution_results[0] if execution_results else "No output."

                    
                    if tool_name == "save_research_note":
                        note_content = tc.get("arguments", {}).get("gathered_data", "").upper()
                        if re.search(r'(STEP|OBJECTIVE)\s*\d*\s*COMPLETE|(STEP|OBJECTIVE)\s*\d*\s*VERIFIED|ALL VERIFICATION COMPLETE', note_content):
                            if current_idx == len(state['steps']) - 1:
                                console.print(f"[dim yellow]⚡ OS Auto-Detect: Ignoring step completion phrase because this is the final step. Waiting for report.[/dim yellow]")
                            else:
                                console.print(f"[bold yellow]⚡ OS Auto-Detect: Step completion detected inside notes. Forcing state advancement![/bold yellow]")
                                has_advance = True
                                advance_summary = "Auto-advanced by OS (Completion phrase detected)."

                    
                    # --- RESTORED: OS Auto-Scrape Interceptor ---
                    if "web_search" in tool_name.lower() or "search" in tool_name.lower():
                        urls = re.findall(r'URL:\s+(https?://[^\s]+)', result)
                        best_url, best_score = None, -9999
                        for url in urls:
                            url = url.strip()
                            if url in visited_urls: continue
                            score = 0
                            lower_url = url.lower()
                            if '.edu' in lower_url or '.gov' in lower_url: score += 50
                            if '.org' in lower_url: score += 20
                            if 'arxiv.org' in lower_url or 'github.com' in lower_url: score += 30
                            if 'reddit.com' in lower_url or 'quora.com' in lower_url: score -= 30
                            if 'pinterest.com' in lower_url: score -= 50
                            if score > best_score:
                                best_score, best_url = score, url
                                
                        if best_url:
                            visited_urls.add(best_url)
                            bibliography.append(best_url) # <-- Track it!
                            console.print(f"[dim cyan]🔗 OS Smart-Scrape: Selected high-value URL (Score: {best_score}) -> {best_url}[/dim cyan]")
                            try:
                                if "read_webpage" in ALL_TOOLS:
                                    scrape_data = ALL_TOOLS["read_webpage"](url=best_url)
                                else:
                                    scrape_data = "(Error: read_webpage missing)"
                                result += f"\n\n--- OS AUTO-SCRAPED TEXT FROM {best_url} ---\n{scrape_data}\n--- END AUTO-SCRAPE ---"
                            except Exception as e:
                                result += f"\n\n(OS Auto-Scrape failed for {best_url}: {e})"
                        else:
                            result += "\n\n(OS Note: No new high-quality URLs found to auto-scrape.)"
                            
                    # --- NEW: Manual Read Interceptor ---
                    elif tool_name == "read_webpage":
                        url_arg = tc.get("arguments", {}).get("url", "")
                        if url_arg and url_arg not in visited_urls:
                            visited_urls.add(url_arg)
                            bibliography.append(url_arg)

                    last_tool_output += f"\nTool '{tool_name}' result:\n{result}\n"
                    console.log_tool_execution(tool_name, tc.get("arguments", {}), result)
                
                if len(bibliography) > len(state.get("sources", [])):
                    state["sources"] = bibliography
                    with open(task_file, "w", encoding="utf-8") as f:
                        json.dump(state, f, indent=4)
                        
                if last_tool_output:
                    conversation_history.append({"role": "user", "content": f"Tool Outputs:{last_tool_output}"})
                    ledger_text += f"\n{last_tool_output}\n"
                    if ui_callback: ui_callback(ledger_text)
                elif not has_advance and not has_finish:
                    error_msg = "❌ OS Error: You must call at least one tool to progress."
                    conversation_history.append({"role": "user", "content": error_msg})
                    ledger_text += f"\n{error_msg}\n"
                    if ui_callback: ui_callback(ledger_text)

                if has_advance:
                    advance_json_state(task_file, advance_summary)
                    conversation_history = [] 
                    
                if has_finish:
                    aquila_memory.store_experience(task_name, finish_msg)
                    return finish_msg
                    
                step_count += 1
                
            except Exception as e:
                console.print(f"[bold red]Critical OS Error in loop: {e}[/bold red]")
                return f"OS Error: {str(e)}"
                
        return "⚠️ OS halted: Maximum iterations reached."

global_agent = Agent()

def initiate_sleep_cycle() -> str:
    tasks_dir = Path("Agent-Tasks")
    if not tasks_dir.exists(): 
        return "🧠 Sleep cycle aborted. No tasks folder found."

    json_files = list(tasks_dir.glob("*.json"))
    if not json_files: 
        return "🧠 Sleep cycle complete. The desk is already clean."

    consolidation_results = []

    for file_path in json_files:
        task_name = file_path.stem
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
            
            summary = client.chat([{"role": "user", "content": prompt}], temperature=0.1)
            aquila_memory.store_experience(task_name, summary)
            file_path.unlink()
            consolidation_results.append(f"- **{task_name}**: Compressed and cleared.")
            
        except Exception as e:
            consolidation_results.append(f"- **{task_name}**: ❌ Failed to consolidate ({e})")

    return "🌙 **Sleep Cycle Complete. KV Cache Flushed.**\n\n" + "\n".join(consolidation_results)