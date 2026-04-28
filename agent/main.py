import sys
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

# Direct imports bypass the old getattr loop and prevent circular imports
from tools import SURVIVAL_TOOLS
try:
    from tool_library import ALL_TOOLS
except ImportError:
    ALL_TOOLS = {}

class DualLogger:
    def __init__(self):
        self.console = Console()
        self.current_task = None
        self.log_filename = None
        
    def set_task(self, task_name: str):
        """Initializes the log file with a unique timestamp to prevent overlap."""
        self.current_task = task_name
        os.makedirs("Agent-Logs", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # --- FIX: Unique log file per session! ---
        self.log_filename = f"Agent-Logs/{self.current_task}_{timestamp}.log"
        
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

aquila_memory = DualMemorySystem()
# Replace the standard console with our new indestructible flight recorder
console = DualLogger()

# Add current directory path so Python can find agent tools/modules
sys.path.insert(0, str(Path(__file__).parent))

import time

class OllamaClient:
    def __init__(self):
        self.base_url = "http://127.0.0.1:11434" 
        self.model_name = "aquila"
        self.session = requests.Session()
        print("✅ Connected to Ollama (With Streaming Kill-Switch)")
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.6, timeout: int = 120) -> str:
        # We add frequency and presence penalties to stop Qwen from endlessly looping!
        payload = {
            "model": self.model_name, 
            "messages": messages, 
            "temperature": temperature, 
            "stream": True,             # --- TURN ON STREAMING ---
            "frequency_penalty": 1.05,  # --- ANTI-LOOPING MEASURE ---
            "presence_penalty": 1.05
        }
            
        try:
            start_time = time.time()
            full_content = ""
            
            # timeout=(Connect_Timeout, Read_Timeout_Per_Chunk)
            # If Ollama takes longer than 60 seconds to process the prompt, it aborts.
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions", 
                json=payload, 
                stream=True, 
                timeout=(5, 60) 
            )
            response.raise_for_status()

            # Iterate through the chunks as they arrive from the GPU
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                full_content += delta["content"]
                        except Exception:
                            pass

                # --- THE ACTIVE KILL SWITCH ---
                # Check the clock on every single word generated.
                if time.time() - start_time > timeout:
                    console.print(f"\n[bold red]⚠️ KILL SWITCH ACTIVATED: Model exceeded {timeout}s limit. Severing connection to save GPU.[/bold red]")
                    response.close() # <--- THIS STOPS THE GPU INSTANTLY
                    return full_content.strip() + "\n\n*(System Note: Generation was forcibly severed to save GPU resources. The model may have been stuck in a loop.)*"
                
            return full_content.strip()
            
        except requests.exceptions.ReadTimeout:
            error_msg = f"*(System Timeout: The model took too long to start writing. Context window may be flooded.)*"
            console.print(f"[bold red]{error_msg}[/bold red]")
            return error_msg
        except Exception as e:
            error_msg = f"*(API Error: {str(e)})*"
            console.print(f"[bold red]{error_msg}[/bold red]")
            return error_msg

client = OllamaClient()

def parse_tool_calls(response_text: str) -> list[dict]:
    action_header_pattern = r"###?.*?ACTION:\s*(\w+)"
    tool_calls = []
    chunks = re.split(action_header_pattern, response_text)
    
    if len(chunks) > 1:
        for i in range(1, len(chunks), 2):
            name = chunks[i].strip()
            body = chunks[i+1]
            arguments = {}
            
            arg_pattern = r"\*\*(\w+)\*\*:\s*([\s\S]*?)(?=\*\*\w+\*\*:|$)"
            matches = re.findall(arg_pattern, body)
            
            if not matches:
                fallback_pattern = r"(?:^|\n)\s*(\w+):\s*([\s\S]*?)(?=(?:\n\s*\w+:\s*)|$)"
                matches = re.findall(fallback_pattern, body)
                valid_keys = {"file_path", "content", "target_text", "replacement_text", "keyword", "path", "args", "to", "subject", "body", "function_name", "code", "message_to_user", "summary_of_completed_steps", "summary_of_work"}
                matches = [(k, v) for k, v in matches if k in valid_keys]
            
            for key, value in matches:
                val = value.strip()
                val = re.sub(r'\n\s*[-_*]{3,}\s*$', '', val).strip()
                while val.endswith('---'): val = val[:-3].strip()
                if val.startswith("```"):
                    val = re.sub(r"^```[^\n]*\n", "", val)
                    val = re.sub(r"\n```$", "", val)
                elif val.startswith("`") and val.endswith("`"):
                    val = val[1:-1]
                if val:
                    arguments[key] = val.strip()
                    
            if name: 
                tool_calls.append({"name": name, "arguments": arguments})
    return tool_calls

class ToolExecutor:
    def execute(self, tool_calls: list[dict]) -> list[str]:
        results = []
        executable_tools = {**SURVIVAL_TOOLS, **ALL_TOOLS}

        for call in tool_calls:
            name = call.get("name")
            arguments = call.get("arguments") or {} 
            
            if not name or name not in executable_tools:
                # --- FIX: Stop her from hallucinating tools ---
                results.append(f"Tool '{name}' returned: ❌ Error - Function does not exist. DO NOT guess tool names. Use 'search_tool_library' to find valid tools.")
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

# --- JSON STATE MANAGEMENT ---
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

class Agent:
    def __init__(self, master_prompt: str):
        self.executor = ToolExecutor()
        self.master_prompt = master_prompt
        aquila_memory.index_tools({**SURVIVAL_TOOLS, **ALL_TOOLS})
        
    def _get_dynamic_system_prompt(self, routed_tool_names: list[str] = None) -> str:
        executable_tools = {**SURVIVAL_TOOLS, **ALL_TOOLS}
        
        core_tools = {
            "mark_objective_complete", "finish_task", "search_tool_library", 
            "write_file", "read_file", "read_file_lines"
        }
        
        if routed_tool_names:
            core_tools.update(routed_tool_names)
        else:
            core_tools.update(executable_tools.keys()) 
            
        dynamic_tools_text = ""
        
        for name in core_tools:
            if name not in executable_tools: continue
            tool_info = executable_tools[name]
            
            sig = inspect.signature(tool_info['func']) 
            template = f"### 🛠️ ACTION: {name}"
            for param in sig.parameters: 
                if param == 'kwargs': continue 
                template += f"\n**{param}**: ..."
            dynamic_tools_text += f"TOOL: {name}\nDESC: {tool_info['description']}\nFORMAT:\n{template}\n\n"

        return self.master_prompt + f"\n=== AVAILABLE TOOLS ===\nUse ONLY this MARKDOWN format:\n{dynamic_tools_text}"

    def generate_json_plan(self, user_request: str) -> list:
        """Forces the LLM to output a strict JSON array of context-loaded steps."""
        console.print("[dim cyan]⚙️ OS is generating structured task plan...[/dim cyan]")
        
        prompt = f"""
        You are the backend task router. The user wants to: "{user_request}"
        
        Break this down into a sequence of specific, executable steps.
        CRITICAL: Each step must contain full context (e.g., "Research Africa news" NOT "Research first item").
        
        You MUST output ONLY a raw, valid JSON array of strings. No markdown formatting. No explanation.
        
        Example Output:
        [
            "Create reports directory.",
            "Research current news for Africa.",
            "Write the final report."
        ]
        """
        response = client.chat([{"role": "user", "content": prompt}], temperature=0.1)
        
        try:
            clean_json = response.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            console.print(f"[bold red]Failed to parse JSON plan: {e}[/bold red]")
            return [f"Execute user request: {user_request}"]

    def run_autonomous_task(self, task_name: str, user_request: str, ledger_placeholder=None) -> str:
        # --- INITIALIZE THE BLACK BOX RECORDER ---
        console.set_task(task_name)
        
        tasks_dir = "Agent-Tasks"
        os.makedirs(tasks_dir, exist_ok=True)
        task_file = f"{tasks_dir}/{task_name}.json" 

        # Phase 1: OS Initializes the Plan
        if not os.path.exists(task_file):
            steps = self.generate_json_plan(user_request)
            initialize_json_ledger(task_file, steps)
        
        system_prompt = self._get_dynamic_system_prompt()
        last_tool_output = None
        step_count = 0
        MAX_ITERATIONS = 50
        
        # --- ROLLING MEMORY BUFFER ---
        conversation_history = []

        # Phase 2: The Focused Worker Loop
        while step_count < MAX_ITERATIONS:
            console.print(f"\n[bold magenta]--- Aquila OS Iteration {step_count + 1} ---[/bold magenta]")
            
            try:
                state = read_json_state(task_file)
                
                if state["status"] == "completed":
                    return "All objectives in the JSON task array have been completed successfully."
                    
                current_idx = state["current_step_index"]
                current_objective = state["steps"][current_idx]["description"]
                
                # Update UI
                if ledger_placeholder:
                    with ledger_placeholder.container():
                        import streamlit as st
                        st.subheader(f"Task: `{task_name}`")
                        st.caption(f"Status: {state.get('status', 'unknown').upper()}")
                        for i, step in enumerate(state.get("steps", [])):
                            if step["status"] == "completed":
                                st.markdown(f"✅ ~~{step['description']}~~")
                            elif i == state.get("current_step_index"):
                                st.markdown(f"🔄 **{step['description']}**")
                            else:
                                st.markdown(f"⏳ {step['description']}")
                                
            except Exception as e:
                return f"Fatal Error: Could not read JSON State. {e}"

            # --- THE LASER-FOCUSED PROMPT ---
            user_msg = f"""**Ultimate Goal:** {user_request}

**YOUR CURRENT OBJECTIVE (Step {current_idx + 1} of {len(state['steps'])}):**
> {current_objective}

Execute tools to complete this objective. 
Once fully complete, you MUST use the `mark_objective_complete` tool to advance."""
            
            if last_tool_output:
                user_msg += f"\n\n**Result of last tool execution:**\n{last_tool_output}"
                
            # 1. Add OS message to the rolling buffer
            conversation_history.append({"role": "user", "content": user_msg})
            
            # 2. Cap the buffer to the last 4 messages (2 full Agent/OS interaction turns)
            # This prevents context bloat while letting her chain multiple tools!
            if len(conversation_history) > 4:
                conversation_history = conversation_history[-4:]
                
            active_memory = [{"role": "system", "content": system_prompt}] + conversation_history
            
            response_text = client.chat(active_memory, temperature=0.2)

            if response_text.startswith("Error connecting to Ollama") or response_text.startswith("API Error"):
                error_msg = (
                    "⚠️ SYSTEM ERROR: The LLM API timed out. "
                    "Your last action requested too much data or caused an infinite loop. "
                    "DO NOT repeat the exact same tool call. Try a smaller, more specific approach."
                )
                console.print(f"[bold red]API Timeout. Intercepting error and giving Aquila a chance to recover...[/bold red]")
                
                # Pass the warning directly into her memory buffer and skip the rest of the loop!
                last_tool_output = error_msg
                step_count += 1
                continue
            
            console.print(f"[green]{response_text}[/green]")
            
            # 3. Add Agent response to the rolling buffer
            conversation_history.append({"role": "assistant", "content": response_text})
            
            tool_calls = parse_tool_calls(response_text)
            
            if tool_calls:
                # --- THE SMART HYBRID EXECUTOR ---
                has_advance = False
                has_finish = False
                advance_summary = ""
                finish_msg = ""
                
                # 1. Scan ALL tool calls for State Changers (so they never get chopped off!)
                for tc in tool_calls:
                    if tc["name"] == "mark_objective_complete":
                        has_advance = True
                        advance_summary = tc.get("arguments", {}).get("summary_of_work", "Completed.")
                    elif tc["name"] == "finish_task":
                        has_finish = True
                        finish_msg = tc.get("arguments", {}).get("message_to_user", "Task completed.")

                # 2. Categorize and Cap Tools
                # We ALWAYS allow memory saves. We ONLY cap active environment interactions.
                save_tools = [tc for tc in tool_calls if tc["name"] == "save_research_note"]
                normal_tools = [tc for tc in tool_calls if tc["name"] not in ["mark_objective_complete", "finish_task", "save_research_note"]]
                
                tools_to_execute = normal_tools[:3] + save_tools
                last_tool_output = ""
                
                if tools_to_execute:
                    execution_results = self.executor.execute(tools_to_execute)
                    last_tool_output = "\n\n".join(execution_results)
                
                if len(normal_tools) > 3:
                    last_tool_output += "\n\n⚠️ SYSTEM WARNING: You called too many action tools. Only the first 3 were executed to prevent context flooding."

                # 3. Process State Changers Last
                if has_finish:
                    aquila_memory.store_experience(task_name, finish_msg)
                    return finish_msg
                    
                elif has_advance:
                    console.print(f"[bold blue]✅ OS advancing state to next objective...[/bold blue]")
                    advance_json_state(task_file, advance_summary)
                    last_tool_output += f"\n\nObjective complete: {advance_summary}. System has advanced you to the next step."
                    
                    # --- THE CLEAN SLATE ---
                    conversation_history = []
                    
            else:
                last_tool_output = "SYSTEM WARNING: Format your tool calls using '### 🛠️ ACTION: tool_name'."
                console.print(f"[bold red]{last_tool_output}[/bold red]")
                
            step_count += 1
            
        return "Task paused: Reached maximum safety iterations (50)."

# Global Agent Definition
master_prompt = f"""# SYSTEM ROLE: Autonomous AI Worker & Executor
You are Aquila, a highly capable autonomous AI. The Python OS acts as your Project Manager, and you act as the Executor. 

## 1. Identity & Environment
- **OS:** {sys.platform} | **Directory:** {os.getcwd()} 
- **The Brain:** To save absolute rules/lore, use `store_fact`. 
- **The Hands:** Only use `write_file` for actual code, scripts, and reports. Do NOT write markdown checklists.

## 2. The Objective Loop (How you work)
- The OS will feed you exactly ONE objective at a time. Your only goal is to complete that specific objective.
- **TOOL CAP:** You may output up to 3 tool calls (`### 🛠️ ACTION:`) per response. This allows you to combine actions (e.g., using `save_research_note` and `mark_objective_complete` in the exact same turn).
- If you don't know the exact name of a tool, use `search_tool_library`.
- **ADVANCING:** The exact moment you finish your current objective, use `mark_objective_complete`. 

## 3. Research & State Management (THE SCRATCHPAD)
- **Short-Term Memory:** You have a rolling memory buffer of your last few actions. However, your memory is **COMPLETELY WIPED** the moment you advance to a new objective.
- **First Step Rule:** Because of the memory wipe, when you start a new objective, your FIRST action should usually be `read_all_research_notes` to load previously gathered context.
- If you gather data (using `web_search`, `get_directory_tree`, etc.), you MUST use `save_research_note` to dump the facts into your SQLite database so you don't lose them.
- **NEVER use `replace_in_file` to build large reports line-by-line.** Write the final document using a SINGLE `write_file` action.
"""

global_agent = Agent(master_prompt=master_prompt)

def initiate_sleep_cycle() -> str:
    tasks_dir = Path("Agent-Tasks")
    if not tasks_dir.exists(): 
        return "🧠 Sleep cycle aborted. No tasks folder found."

    # NOW LOOKING FOR JSON FILES
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