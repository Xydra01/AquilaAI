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

# Tools imports
from tools import SURVIVAL_TOOLS
try:
    from tool_library import ALL_TOOLS
except ImportError:
    ALL_TOOLS = {}

# Constrained Decoding Schema
AQUILA_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Your internal thoughts, reasoning, and explanations. MUST be filled out before calling tools."
        },
        "final_report": {
            "type": "string",
            "description": "ONLY USE ON THE FINAL STEP. Your comprehensive, fully formatted Markdown report."
        },
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string"
                    },
                    "arguments": {
                        "type": "object"
                    }
                },
                "required": ["name", "arguments"]
            }
        }
    },
    "required": ["reasoning", "tools"]
}

class DualLogger:
    def __init__(self):
        self.console = Console()
        self.current_task = None
        self.log_filename = None
        
    def set_task(self, task_name: str):
        """Initializes the log file with a unique timestamp to prevent overlap."""
        self.current_task = task_name
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
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
                
    def log_iteration(self, iteration: int, content: str):
        """Logs the raw LLM response for a specific iteration."""
        if not self.log_filename:
            return
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(f"\n--- Iteration {iteration} ---\n{content}\n")

    def log_tool_execution(self, tool_name: str, args: dict, result: str):
        """Logs the tool call and its output."""
        if not self.log_filename:
            return
        with open(self.log_filename, "a", encoding="utf-8") as f:
            f.write(f"\n[🛠️ TOOL EXECUTED: {tool_name}]\nARGS: {args}\nRESULT:\n{result}\n")

aquila_memory = DualMemorySystem()
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
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.6, timeout: int = 120, format: dict = None) -> str:
        payload = {
            "model": self.model_name, 
            "messages": messages, 
            "temperature": temperature, 
            "stream": True,
            "frequency_penalty": 0.2, 
            "presence_penalty": 0.2
        }
        
        if format:
            payload["format"] = format
            
        try:
            start_time = time.time()
            first_token_received = False
            full_content = ""
            
            console.print(f"[yellow]⏳ Sending prompt to Ollama API at {self.base_url}...[/yellow]")
            
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions", 
                json=payload, 
                stream=True, 
                timeout=(5, 90) 
            )
            response.raise_for_status()

            console.print("[green]✅ Connected! Waiting for GPU to compute first token...[/green]")

            for line in response.iter_lines():
                if line:
                    if not first_token_received:
                        console.print(f"[bold cyan]⚡ FIRST TOKEN RECEIVED in {time.time() - start_time:.2f} seconds![/bold cyan]")
                        first_token_received = True
                        start_time = time.time() 

                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                token = delta["content"]
                                full_content += token
                                
                                sys.stdout.write(token)
                                sys.stdout.flush()
                        except Exception:
                            pass

                if time.time() - start_time > timeout:
                    sys.stdout.write("\n")
                    console.print(f"\n[bold red]⚠️ KILL SWITCH ACTIVATED: Model hit the {timeout}s limit.[/bold red]")
                    response.close() 
                    return full_content.strip() + "\n\n*(System Note: Generation was forcibly severed. Check the terminal to see what she was stuck on!)*"
                
            sys.stdout.write("\n")
            return full_content.strip()
            
        except requests.exceptions.ReadTimeout:
            error_msg = f"*(System Timeout: The model took too long to load into VRAM or process the context.)*"
            console.print(f"[bold red]{error_msg}[/bold red]")
            return error_msg
        except Exception as e:
            error_msg = f"*(API Error: {str(e)})*"
            console.print(f"[bold red]{error_msg}[/bold red]")
            return error_msg

client = OllamaClient()

def parse_agent_response(response_text: str) -> dict:
    """Parses the pure, constrained JSON response from the agent."""
    try:
        data = json.loads(response_text, strict=False)
        return data
    except Exception as e:
        console.print(f"[bold red]⚠️ JSON Parser Error: {e}[/bold red]")
        return {}

class ToolExecutor:
    def execute(self, tool_calls: list[dict]) -> list[str]:
        results = []
        executable_tools = {**SURVIVAL_TOOLS, **ALL_TOOLS}

        for call in tool_calls:
            name = call.get("name")
            arguments = call.get("arguments") or {} 
            
            if not name or name not in executable_tools:
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
        # Initialize directories
        os.makedirs("Agent-Tasks", exist_ok=True)
        os.makedirs("Agent-Creations", exist_ok=True)
        os.makedirs("Agent-Research", exist_ok=True)
        os.makedirs("Agent-Plans", exist_ok=True)
        self.executor = ToolExecutor()
        self.base_task_prompt = master_prompt
        self.memory = aquila_memory 
        aquila_memory.index_tools({**SURVIVAL_TOOLS, **ALL_TOOLS})

    def _get_research_master_prompt(self, task_name: str) -> str:
        """Returns the specific system prompt for Research Mode."""
        current_date = datetime.datetime.now().strftime("%B %d, %Y")
        return f"""# SYSTEM ROLE: Autonomous AI Researcher
You are Aquila, operating in Research Mode. Your primary directive is to gather, extract, and preserve highly technical information and raw data from the internet.

## 1. Identity & Environment
- **Current Date:** {current_date}
- **OS:** {sys.platform} | **Directory:** {os.getcwd()}
- **The Brain:** Use `save_research_note` and `read_all_research_notes` to manage facts.

## 2. The Objective Loop (How you work)
- The OS will feed you exactly ONE objective at a time.
- TOOL CAP: You may output up to 6 tool calls per response.
- **OS AUTO-SCRAPE:** When you use the `web_search` tool, the OS will automatically read the top URL for you. Search once, read the auto-scraped text, and extract the data.
- **NO MASSIVE DATASETS (CRITICAL):** Do not copy-paste raw scraped HTML. Extract the readable, factual data.
- The exact moment you finish your current objective, use the `mark_objective_complete` tool.

## 3. Research & State Management (THE SCRATCHPAD)
- **Short-Term Memory:** You have a rolling memory buffer of your last few actions. However, your memory is COMPLETELY WIPED the moment you advance to a new objective.
- **First Step Rule:** Because of the memory wipe, your FIRST action on a new objective should be to use `read_all_research_notes`. **Do not call this tool more than once per objective.**
- **DATA EXTRACTION:** You MUST use your `save_research_note` tool to securely store facts.
- **COMPLETION:** For the FINAL step, write your fully formatted Markdown report into the `"final_report"` key of your JSON object. Then use the `finish_task` tool.

## 4. Tool Execution Formatting (CRITICAL)
You are locked into a strict JSON output format. You MUST respond with a single, valid JSON object.

Example of advancing to the next step:
{{
    "reasoning": "I have verified the data. I am ready to advance.",
    "tools": [
        {{
            "name": "mark_objective_complete",
            "arguments": {{"summary_of_work": "Compiled genre data."}}
        }}
    ]
}}

Example of finishing the task (FINAL STEP ONLY):
{{
    "reasoning": "Research is complete. I will now output the report and finish the task.",
    "final_report": "# Main Title\n\nHere is my comprehensive research...",
    "tools": [
        {{
            "name": "finish_task",
            "arguments": {{"message_to_user": "Task completed successfully."}}
        }}
    ]
}}
"""

    def generate_plan(self, topic_name: str, user_request: str, mode: str) -> str:
        """Generates a universal JSON state array for both Tasks and Research."""
        
        if mode == "research":
            role_desc = "You are Aquila's Lead Researcher."
            objectives = "Focus on formulating searches, extracting technical data, and cross-referencing."
            example_steps = """
                {"status": "pending", "description": "Search for precursor genres...", "max_iterations": 3},
                {"status": "pending", "description": "Dump the final extracted data to Agent-Research...", "max_iterations": 2}
            """
        else:
            role_desc = "You are the backend task router."
            objectives = "Break the request down into a sequence of specific, executable coding or filing steps."
            example_steps = """
                {"status": "pending", "description": "Create the required python files...", "max_iterations": 2},
                {"status": "pending", "description": "Write the final code logic...", "max_iterations": 4}
            """

        prompt = f"""
        {role_desc}
        The user needs: {user_request}
        
        Create a strict JSON state object to manage this workflow.
        {objectives}
        
        CRITICAL: For every step, you must assign a "max_iterations" integer. 
        
        Output ONLY valid JSON matching this exact structure:
        {{
            "status": "in_progress",
            "current_step_index": 0,
            "steps": [
                {example_steps}
            ]
        }}
        """
        
        for attempt in range(3):
            response = client.chat([{"role": "user", "content": prompt}], temperature=0.1)
            if "Generation was forcibly severed" in response:
                console.print(f"[bold yellow]⚠️ Planner hit the Kill Switch. Retrying ({attempt + 1}/3)...[/bold yellow]")
                continue
            clean_json = response.replace("```json", "").replace("```", "").strip()
            try:
                json.loads(clean_json)
                return clean_json 
            except json.JSONDecodeError as e:
                console.print(f"[bold yellow]⚠️ LLM generated corrupted JSON ({e}). Retrying ({attempt + 1}/3)...[/bold yellow]")
                continue
                
        raise Exception("Fatal: LLM failed to generate a valid JSON plan after 3 attempts.")

    def run_unified_task(self, task_name: str, user_request: str, mode: str = "task", ui_callback=None) -> str:
        """The Master Execution Engine for both Autonomous Tasks and Deep Research."""
        console.set_task(task_name)
        mode_label = "Deep-Dive Research" if mode == "research" else "Autonomous Task"
        console.print(f"\n[bold magenta]🚀 OS is initializing {mode_label} for: {task_name}[/bold magenta]")
        
        plan_dir = "Agent-Plans" if mode == "research" else "Agent-Tasks"
        task_file = os.path.join(plan_dir, f"{task_name}.json")
        system_prompt = self._get_research_master_prompt(task_name) if mode == "research" else self.base_task_prompt
        
        if not os.path.exists(task_file):
            plan_json = self.generate_plan(task_name, user_request, mode)
            with open(task_file, "w", encoding="utf-8") as f:
                f.write(plan_json)

        visited_urls = set()
        conversation_history = []
        step_count = 0
        max_steps = 50

        ledger_text = f"Initializing {mode_label} Engine for: {task_name}\n"
        
        while step_count < max_steps:
            try:
                state = read_json_state(task_file)
                
                if state["status"] == "completed":
                    return f"✅ {mode_label} completed successfully. Check the directory for the final outputs."
                    
                current_idx = state["current_step_index"]
                if current_idx >= len(state["steps"]):
                    return "✅ All steps are completed."
                    
                current_objective = state["steps"][current_idx]["description"]
                max_step_iterations = state["steps"][current_idx].get("max_iterations", 4)
                
                if ui_callback:
                    ui_callback(ledger_text)

                step_attempts = sum(1 for msg in conversation_history if msg["role"] == "assistant")
                
                user_msg = f"**Ultimate Topic/Goal:** {user_request}\n\n**YOUR CURRENT OBJECTIVE (Step {current_idx + 1} of {len(state['steps'])}):**\n> {current_objective}"

                if step_attempts >= max_step_iterations:
                    console.print(f"[bold red]⏰ OS ENFORCER: Iteration budget ({max_step_iterations}) exhausted for Step {current_idx + 1}. Forcing advancement![/bold red]")
                    
                    if current_idx == len(state['steps']) - 1:
                        user_msg += f"\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP FOR THIS FINAL OBJECTIVE.\nYou MUST immediately output your final organized Markdown report into the `final_report` JSON key, and use the `finish_task` tool. Do not delay."
                    else:
                        user_msg += f"\n\n⚠️ CRITICAL OS OVERRIDE: TIME IS UP FOR THIS OBJECTIVE.\nYou have reached the maximum allowed iterations ({max_step_iterations}/{max_step_iterations}). You MUST immediately use `save_research_note` to save any facts you have, then use `mark_objective_complete` to move on. Do not delay."
                else:
                    user_msg += f"\n\nExecute tools to complete this specific objective. Once fully complete, use the `mark_objective_complete` tool to advance.\n(Iteration {step_attempts + 1}/{max_step_iterations} for this step)"

                active_memory = [{"role": "system", "content": system_prompt}] + conversation_history + [{"role": "user", "content": user_msg}]
                
                response_text = client.chat(active_memory, temperature=0.2, format=AQUILA_ACTION_SCHEMA) 
                
                console.log_iteration(step_count + 1, response_text)
                
                ledger_text += f"\n\n--- Iteration {step_count + 1} ---\n{response_text}\n"
                if ui_callback:
                    ui_callback(ledger_text)

                parsed_response = parse_agent_response(response_text)
                
                if parsed_response.get("final_report"):
                    save_dir = "Agent-Research" if mode == "research" else "Agent-Creations"
                    with open(f"{save_dir}/{task_name}.md", "w", encoding="utf-8") as f:
                        f.write(parsed_response["final_report"])
                    console.print(f"[bold green]✅ Final report extracted from JSON schema and saved to {save_dir}![/bold green]")
                
                tool_calls = parsed_response.get("tools", [])
                

                if not isinstance(tool_calls, list):
                    tool_calls = []
                    
                last_tool_output = ""
                has_advance = False
                has_finish = False
                advance_summary = ""
                finish_msg = ""
                
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                        
                    tool_name = tc.get("name", "")
                    
                    if tool_name == "mark_objective_complete":
                        # Final Setp Blockade
                        if current_idx == len(state['steps']) - 1:
                            result = "❌ OS BLOCK: You are on the final step. Do not use `mark_objective_complete`. You MUST output the report using [START_REPORT]...[END_REPORT] and use `finish_task`."
                            last_tool_output += f"\nTool '{tc['name']}' result:\n{result}\n"
                            console.log_tool_execution(tc["name"], tc.get("arguments", {}), result)
                        else:
                            has_advance = True
                            advance_summary = tc.get("arguments", {}).get("summary_of_work", "Completed.")
                    elif tc["name"] == "finish_task":
                        has_finish = True
                        args = tc.get("arguments", {})
                        finish_msg = args.get("message_to_user", args.get("summary", "Task completed."))
                    else:
                        execution_results = self.executor.execute([tc])
                        result = execution_results[0] if execution_results else "No output."

                        if tc["name"] == "save_research_note":
                            note_content = tc.get("arguments", {}).get("gathered_data", "").upper()
                            if re.search(r'(STEP|OBJECTIVE)\s*\d*\s*COMPLETE|(STEP|OBJECTIVE)\s*\d*\s*VERIFIED|ALL VERIFICATION COMPLETE', note_content):
                                if current_idx == len(state['steps']) - 1:
                                    console.print(f"[dim yellow]⚡ OS Auto-Detect: Ignoring step completion phrase because this is the final step. Waiting for report.[/dim yellow]")
                                else:
                                    console.print(f"[bold yellow]⚡ OS Auto-Detect: Step completion detected inside notes. Forcing state advancement![/bold yellow]")
                                    has_advance = True
                                    advance_summary = "Auto-advanced by OS (Completion phrase detected)."
                        
                        # Scraper and url ranking
                        if "web_search" in tc["name"].lower() or "search" in tc["name"].lower():
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

                        last_tool_output += f"\nTool '{tc['name']}' result:\n{result}\n"
                        console.log_tool_execution(tc["name"], tc.get("arguments", {}), result)
                
                if last_tool_output:
                    conversation_history.append({"role": "user", "content": f"Tool Outputs:{last_tool_output}"})
                
                    ledger_text += f"\n{last_tool_output}\n"
                    if ui_callback:
                        ui_callback(ledger_text)

                if has_advance:
                    console.print(f"[bold blue]✅ OS advancing state to next objective...[/bold blue]")
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

# Global Agent Definition
current_date = datetime.datetime.now().strftime("%B %d, %Y")
        
master_prompt = f"""# SYSTEM ROLE: Autonomous AI Engineer & Operator
You are Aquila, an advanced autonomous AI. Your directive is to execute complex research, coding, system operation, and file manipulation tasks across multiple iterative steps.

## 1. Identity & Environment
- **Current Date:** {current_date}
- **OS:** {sys.platform} | **Directory:** {os.getcwd()}
- **The Brain (Breadcrumbs):** You MUST use `save_research_note` to leave a paper trail for yourself across steps.

## 2. The Objective Loop (How you work)
- The OS will feed you exactly ONE objective at a time. Do NOT attempt to complete future objectives early. Compartmentalize your work.
- TOOL CAP: You may output up to 6 tool calls per response.
- **PAPER TRAIL:** If you learn something, gather facts, generate code logic, or plan a structure, save it to your scratchpad using `save_research_note` so you don't forget it when the objective changes.
- The exact moment you finish your current objective, use the `mark_objective_complete` tool.

## 3. Execution & State Management
- **Short-Term Memory:** Your short-term conversation buffer is COMPLETELY WIPED the moment you advance to a new objective.
- **First Step Rule:** Because of the memory wipe, your FIRST action on a new objective should be to use `read_all_research_notes` to regain context of what you did in previous steps.
- **COMPLETION:** For the FINAL step, write your final project documentation or research report into the `"final_report"` key of your JSON object. Then use the `finish_task` tool.

## 4. Tool Execution Formatting (CRITICAL)
You are locked into a strict JSON output format. You MUST respond with a single, valid JSON object matching the OS Schema.

Example of saving a breadcrumb:
{{
    "reasoning": "I need to save the structure of the classes I just designed before I write the files.",
    "tools": [
        {{
            "name": "save_research_note",
            "arguments": {{
                "task_name": "current_task",
                "gathered_data": "Class A: Handles UI. Class B: Handles DB."
            }}
        }}
    ]
}}

Example of advancing to the next step:
{{
    "reasoning": "I have successfully verified the scripts work. I am ready to advance.",
    "tools": [
        {{
            "name": "mark_objective_complete",
            "arguments": {{"summary_of_work": "Created and tested the 4 classifiers."}}
        }}
    ]
}}

Example of finishing the task (FINAL STEP ONLY):
{{
    "reasoning": "The project is complete. I will now output the final report and finish the task.",
    "final_report": "# Project Completion\\n\\nAll files have been generated...",
    "tools": [
        {{
            "name": "finish_task",
            "arguments": {{"message_to_user": "Task completed successfully."}}
        }}
    ]
}}
"""


global_agent = Agent(master_prompt=master_prompt)

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