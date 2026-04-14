import sys
import os
import re
import importlib
import requests
import inspect
import glob
from pathlib import Path
from typing import Any, Dict, List, Tuple
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from memory import LongTermMemory
from tools import SURVIVAL_TOOLS

console = Console()

# Add current directory path so Python can find agent tools/modules
sys.path.insert(0, str(Path(__file__).parent))

try:
    from memory import AgentMemory
except ImportError as e:
    print(f"[ERROR] Failed to import memory module. Ensure memory.py is in the same directory.")
    sys.exit(1)

class LMStudioClient:
    """Client to interact with the local Qwen model via LM Studio."""
    def __init__(self):
        self.base_url = "http://localhost:1234"
        self.model_name = "qwen/qwen3.5-9b"
        self.session = requests.Session()
        print("✅ Connected to LM Studio")
    
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Sends the full message history to the local LLM."""
        payload = {
            "model": self.model_name, 
            "messages": messages, 
            "temperature": 0.7, 
            "stream": False,
            "max_tokens": 8192  # Increased from 2048 so the agent can finish writing long files!
        }
        
        try:
            response = self.session.post(f"{self.base_url}/v1/chat/completions", json=payload, timeout=300)
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error connecting to LM Studio: {e}"

def parse_tool_calls(response_text: str) -> list[dict]:
    """
    Ultimate Markdown parser: Handles multi-line strings, code blocks,
    lazy formatting, and scrubs ghost horizontal rules (---).
    """
    import re
    action_header_pattern = r"###?.*?ACTION:\s*(\w+)"
    
    tool_calls = []
    chunks = re.split(action_header_pattern, response_text)
    
    if len(chunks) > 1:
        for i in range(1, len(chunks), 2):
            name = chunks[i].strip()
            body = chunks[i+1]
            arguments = {}
            
            # Primary: Looks for **arg_name**: followed by anything, until next arg
            arg_pattern = r"\*\*(\w+)\*\*:\s*([\s\S]*?)(?=\*\*\w+\*\*:|$)"
            matches = re.findall(arg_pattern, body)
            
            # Fallback: If agent forgot asterisks
            if not matches:
                fallback_pattern = r"(?:^|\n)\s*(\w+):\s*([\s\S]*?)(?=(?:\n\s*\w+:\s*)|$)"
                fallback_matches = re.findall(fallback_pattern, body)
                
                # Extended valid keys for custom tools!
                valid_keys = {"file_path", "content", "target_text", "replacement_text", "keyword", "path", "args", "to", "subject", "body", "function_name", "code"}
                matches = [(k, v) for k, v in fallback_matches if k in valid_keys]
            
            for key, value in matches:
                val = value.strip()
                
                # NEW: Scrub stray '---' or '***' from the end of the parsed value
                val = re.sub(r'\n\s*[-_*]{3,}\s*$', '', val).strip()
                while val.endswith('---'):
                    val = val[:-3].strip()
                
                # Strip out code block backticks if used
                if val.startswith("```"):
                    val = re.sub(r"^```[^\n]*\n", "", val)
                    val = re.sub(r"\n```$", "", val)
                elif val.startswith("`") and val.endswith("`"):
                    val = val[1:-1]
                    
                if val:
                    arguments[key] = val.strip()
                    
            if name: # Removed the 'and arguments' requirement
                tool_calls.append({"name": name, "arguments": arguments})
                
    return tool_calls

class ToolExecutor:
    """Dynamically loads and executes functions from the tool registry."""
    def __init__(self, tools_module_name: str = "tools"):
        self.tools_module = None
        try:
            self.tools_module = importlib.import_module(tools_module_name)
            print(f"[Info] Successfully loaded tool registry from {tools_module_name}")
        except ImportError as e:
            print(f"[Error] Could not load tools module '{tools_module_name}': {e}", file=sys.stderr)
            
    def execute(self, tool_calls: list[dict]) -> list[str]:
        results = []
        if not self.tools_module:
            return ["Error: Tool registry is not loaded."]

        # --- LIBRARY CARD INTEGRATION ---
        # Combine both the core survival tools and the massive offline library
        survival_tools = getattr(self.tools_module, 'SURVIVAL_TOOLS', {})
        all_tools = getattr(self.tools_module, 'ALL_TOOLS', {})
        executable_tools = {**survival_tools, **all_tools}

        for call in tool_calls:
            name = call.get("name")
            arguments = call.get("arguments") or {} # Default to empty dict so 0-arg tools work!
            
            if name == "_syntax_error":
                results.append("SYSTEM ERROR: Malformed Markdown. Ensure you use ### 🛠️ ACTION: tool_name followed by bolded arguments.")
                continue

            if not name:
                results.append(f"Tool execution failed: Invalid call format.")
                continue

            if name not in executable_tools:
                results.append(f"Tool {name} returned: Error - Function '{name}' does not exist.")
                continue
                
            # Safely grab the function from our combined dictionary
            func = executable_tools[name]["func"]
            
            try:
                # Inspect the real function to see what arguments it actually accepts
                sig = inspect.signature(func)
                
                # Check if the function has a **kwargs parameter (for hallucination-proofing)
                has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                
                if has_kwargs:
                    # Pass everything if the wrapper handles its own validation
                    valid_args = arguments 
                else:
                    # Filter out hallucinated arguments strictly
                    valid_args = {k: v for k, v in arguments.items() if k in sig.parameters}
                
                # Execute with the validated arguments
                output = func(**valid_args)
                results.append(f"Tool {name} returned: {output if output is not None else '(Success)'}")
                
            except Exception as e:
                results.append(f"Tool {name} returned: ❌ Error - {str(e)}")
                
        return results

class Agent:
    def __init__(self, master_prompt: str):
        self.memory = AgentMemory()
        self.ltm = LongTermMemory()
        self.executor = ToolExecutor()
        self.client = LMStudioClient()
        self.history = [{"role": "system", "content": master_prompt}]
        self.consecutive_errors = 0
    
    def _manage_context_window(self):
        """Smart pruning to prevent deleting immediate tool results."""
        CHAR_LIMIT = 25000  # Increased so the agent can remember its thought process
        
        if len(self.history) <= 4: return

        total_chars = sum(len(m["content"]) for m in self.history)
        if total_chars > CHAR_LIMIT:
            console.print("[dim yellow]✂️ Context limit reached. Aggressive pruning active...[/dim yellow]")
            
            # Keep: 
            # 1. System prompt (index 0)
            # 2. Original task/resumption prompt (index 1)
            # 3. ONLY the single most recent Assistant/User interaction (the last 2 turns)
            preserved_start = self.history[:2]
            preserved_end = self.history[-2:] 

            # --- AUTO-LOAD THE LEDGER ---
            ledger_content = "Ledger could not be read."
            if hasattr(self, 'current_task_file') and os.path.exists(self.current_task_file):
                try:
                    with open(self.current_task_file, 'r', encoding='utf-8') as f:
                        ledger_content = f.read()
                except:
                    pass

            time_skip_note = {
                "role": "user", 
                "content": f"[SYSTEM: MEMORY ARCHIVED TO SAVE RAM. You are waking up mid-task.\n\nHere is your exact current state from your Task Ledger:\n\n{ledger_content}\n\nCRITICAL: Pick up exactly where you left off. Do not repeat completed steps.]"
            }
            
            time_skip_note = {
                "role": "user", 
                "content": "[SYSTEM MEMORY ARCHIVED to save RAM. Look at your Task Ledger (.md file) or use `read_file` if you forgot your place.]"
            }
            
            self.history = preserved_start + [time_skip_note] + preserved_end

    def run_autonomous_task(self, task: str, task_id: str) -> None:
        tasks_dir = "Agent-Tasks"
        os.makedirs(tasks_dir, exist_ok=True)
        task_file = f"{tasks_dir}/{task_id}.md"

        is_resuming = os.path.exists(task_file)

        if not is_resuming:
            # --- INITIALIZE THE LEDGER ---
            initial_template = f"""# Task: {task_id.replace('_', ' ')}

## 📍 Current Status
Just initialized. Need to plan the steps to achieve the user's goal: {task}

## 📝 To-Do
- [ ] Use `replace_in_file` to replace this line with your step-by-step plan.
"""
            with open(task_file, "w", encoding="utf-8") as f:
                f.write(initial_template)
            
            console.print(f"[dim cyan]🦅 Aquila spun up a new task thread: {task_file}...[/dim cyan]")
        else:
            console.print(f"[bold green]📂 Aquila is resuming active task: {task_id}[/bold green]")

        # --- 1. PROMPT LOADING (Survival Kit Only) ---
        dynamic_tools_text = ""
        for name, tool_info in SURVIVAL_TOOLS.items():
            sig = inspect.signature(tool_info['func']) 
            template = f"### 🛠️ ACTION: {name}"
            for param in sig.parameters: 
                if param == 'kwargs': continue 
                template += f"\n**{param}**: ..."
            dynamic_tools_text += f"TOOL: {name}\nDESC: {tool_info['description']}\nFORMAT:\n{template}\n\n"

        # Inject tools into the system prompt
        original_system_prompt = self.history[0]["content"]
        if "=== DYNAMIC TOOLS ===" in original_system_prompt:
            original_system_prompt = original_system_prompt.split("=== DYNAMIC TOOLS ===")[0]
            
        new_system_prompt = original_system_prompt + f"""
=== DYNAMIC TOOLS ===
Use ONLY this MARKDOWN format:
{dynamic_tools_text}

=== TASK LEDGER PROTOCOL ===
Your brain state is saved in: `{task_file}`.
Update it frequently. Never lose your place.
"""
        self.history[0] = {"role": "system", "content": new_system_prompt}
        
        # --- LONG TERM MEMORY ---
        past_experience = self.ltm.retrieve_relevant_experience(task, limit=3)
        
        task_msg = f"Task: {task}\n\n"
        if "PAST EXPERIENCES FOUND" in past_experience:
            task_msg += f"🧠 PAST EXPERIENCE RECALLED:\n{past_experience}\nUse these past patterns to guide your current approach.\n\n"
            
        if is_resuming:
            task_msg += (
                f"⚠️ THIS IS AN EXISTING PROJECT. You have just woken up from a memory wipe.\n"
                f"CRITICAL: Before taking any action, you MUST use `read_file` on `{task_file}` to read your 'Current Status' and see the checklist."
            )
            
        self.history.append({"role": "user", "content": task_msg})
        self.memory.update_summary(action_type="Task Started", content=task)
            
        step = 0
        MAX_ITERATIONS = 200

        while step < MAX_ITERATIONS:
            console.print(f"\n[bold magenta]--- Step {step + 1} ---[/bold magenta]")
            
            # --- ITERATION WARNING SYSTEM (The "Wrap Up" Protocol) ---
            if step == MAX_ITERATIONS - 3:
                console.print("\n[bold yellow]⚠️ Time Limit Approaching. Forcing Agent to Wrap Up...[/bold yellow]")
                warning_msg = {
                    "role": "user",
                    "content": (
                        f"🚨 SYSTEM OVERRIDE: You only have 3 iterations left before forced shutdown. "
                        f"1. You MUST immediately stop what you are doing.\n"
                        f"2. Use `replace_in_file` to update `{task_file}` with exact instructions on what you were about to do next.\n"
                        f"3. Once the file is updated, reply with the exact text: 'PAUSING TASK' to gracefully hibernate."
                    )
                }
                self.history.append(warning_msg)
            
            
            try:
                self._manage_context_window()
                response_text = self.client.chat(self.history)
                
                if not response_text.strip():
                    console.print("\n[bold red]⚠️ Empty response. Likely context overflow.[/bold red]")
                    # Prune a bit harder if it fails
                    self.history = [self.history[0], self.history[1]] + self.history[-2:]
                    continue
                
                self.history.append({"role": "assistant", "content": response_text})
                console.print(Panel(Markdown(response_text.strip()), title="🤖 [bold blue]Agent[/bold blue]", border_style="blue"))
                
                # 1. PARSE TOOLS
                tool_calls = parse_tool_calls(response_text)
                
                # 2. --- TOOL EXECUTION & NEW KILL SWITCH ---
                if tool_calls:
                    # --- INTERCEPT FINISH TASK ---
                    if tool_calls[0]["name"] == "finish_task":
                        args = tool_calls[0].get("arguments", {})
                        
                        # Grab the conversational message
                        message = args.get("message_to_user", "Task complete.") if isinstance(args, dict) else "Task complete."
                        
                        # Print it beautifully as the agent's final words!
                        console.print(Panel(Markdown(message), title="🤖 [bold blue]Aquila (Task Complete)[/bold blue]", border_style="green"))
                        
                        # 1. Safely attempt to save to Long Term Memory
                        try:
                            if hasattr(self.ltm, 'add_memory'):
                                self.ltm.add_memory(f"Successfully completed task: {task_id}. Agent's final message: {message}")
                        except Exception:
                            pass

                        # 2. Clean up the desk
                        if os.path.exists(task_file):
                            os.remove(task_file)
                        
                        # 3. GUARANTEE THE LOOP BREAKS
                        break
                    # ------------------------------

                    # Let the agent execute all other tools!
                    if len(tool_calls) > 1:
                        console.print(f"[bold cyan]🛠️ Agent is executing a sequence of {len(tool_calls)} tools...[/bold cyan]")
                        
                    execution_results = self.executor.execute(tool_calls)
                    tool_output_text = "\n\n".join(execution_results)
                    
                    self.history.append({"role": "user", "content": f"Tool execution output:\n{tool_output_text}"})
                    console.print(Panel(tool_output_text, title="⚙️ [dim]Tool Results[/dim]", border_style="dim"))
                    step += 1
                else:
                    # --- NO TOOLS FOUND ---
                    if "PAUSING TASK" in response_text:
                        console.print(f"\n[bold yellow]⏸️ Task Paused. To resume later, select '{task_id}' from the menu.[/bold yellow]")
                        break
                    else:
                        console.print("\n[bold yellow]⚠️ No actions taken and no completion signal. Prompting agent to act.[/bold yellow]")
                        self.history.append({
                            "role": "user", 
                            "content": "You didn't use any tools. If you are finished, you MUST use the `finish_task` tool. If you are waiting on me, state your question clearly."
                        })
                        step += 1
                        
            except Exception as e:
                console.print(f"[bold red]❌ Error: {str(e)}[/bold red]")
                step += 1

def select_active_task() -> str:
    """Scans for active task files and provides a clean selection menu."""
    tasks_dir = Path("Agent-Tasks")
    tasks_dir.mkdir(exist_ok=True)
    
    # Only look for .md files in the tasks directory (ignores the agent's code folders)
    active_tasks = [f.stem for f in tasks_dir.glob("*.md")]
    
    if active_tasks:
        console.print("\n[bold yellow]📌 Active Tasks on your Desk:[/bold yellow]")
        for i, task in enumerate(active_tasks, 1):
            console.print(f"  [cyan]{i}.[/cyan] {task.replace('_', ' ')}")
            
    while True:
        choice = Prompt.ask("\n[bold cyan]📝 Task Name[/bold cyan] [dim](Enter a new name OR a number to resume)[/dim]")
        choice = choice.strip()
        
        if not choice: continue
        if choice.lower() in ['exit', 'quit']: sys.exit(0)
            
        if choice.isdigit() and active_tasks:
            idx = int(choice) - 1
            if 0 <= idx < len(active_tasks):
                return active_tasks[idx]
        
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in choice)
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')
        return safe_name
    
def dispatch_task(user_input: str, client) -> str:
    """
    Acts as the 'front desk' for Aquila. Reviews active tasks and routes the user,
    or generates a clean task name for new requests.
    """
    tasks_dir = Path("Agent-Tasks")
    os.makedirs(tasks_dir, exist_ok=True)
    
    # 1. Read the board
    active_tasks = [f.stem for f in tasks_dir.glob("*.md")]
    
    # 2. If the board is empty, just generate a name
    if not active_tasks:
        return _generate_task_name(user_input, client)
        
    # 3. Ask the LLM to route the request
    routing_system_prompt = f"""You are an automated task router. 
Your ONLY job is to decide if the user's input matches an ongoing task or is a completely new request.

ACTIVE TASKS: {', '.join(active_tasks)}

RULES:
- If the input is clearly continuing or related to an ACTIVE TASK, reply with ONLY the exact name of that task (no extension).
- If it is a completely new request, reply with exactly the word: NEW
- Do not output any other text, reasoning, or punctuation."""
    
    try:
        # Split into System and User messages to satisfy LM Studio's Jinja templates
        messages = [
            {"role": "system", "content": routing_system_prompt},
            {"role": "user", "content": f"USER INPUT: '{user_input}'"}
        ]
        
        response = client.chat(messages)
        decision = response.strip()
        
        if decision in active_tasks:
            console.print(f"[dim cyan]🔀 Dispatcher routed to active task: {decision}[/dim cyan]")
            return decision
        else:
            return _generate_task_name(user_input, client)
            
    except Exception as e:
        console.print(f"[dim red]⚠️ Dispatcher failed ({e}), falling back to default name...[/dim red]")
        return "Manual_Task"

def _generate_task_name(user_input: str, client) -> str:
    """Generates a clean, 2-3 word snake_case slug based on the prompt."""
    naming_system_prompt = """Convert the user request into a short, 2-3 word snake_case file name.
Example 1: "Write a python script to download youtube videos" -> "youtube_downloader"
Example 2: "Help me debug this FastAPI route" -> "fastapi_debugging"
Reply ONLY with the snake_case name. No quotes, no markdown, no other text."""

    try:
        messages = [
            {"role": "system", "content": naming_system_prompt},
            {"role": "user", "content": f"USER REQUEST: '{user_input}'"}
        ]
        
        response = client.chat(messages)
        name = response.strip().replace(" ", "_").replace('"', '').replace("'", "")
        
        # SANITY CHECK: If the LLM returns an error string or a massive sentence, abort to fallback
        if "error" in name.lower() or len(name) > 30:
            raise ValueError("LLM returned an invalid name format.")
            
        console.print(f"[dim cyan]✨ Dispatcher created new task: {name}[/dim cyan]")
        return name
    except Exception as e:
        # Fallback heuristic if the LLM fails or goes crazy
        words = "".join(char for char in user_input if char.isalnum() or char.isspace()).split()
        fallback_name = "_".join(words[:3]).capitalize()
        if not fallback_name:
            fallback_name = "Aquila_Task"
        console.print(f"[dim cyan]✨ Dispatcher created new task (fallback): {fallback_name}[/dim cyan]")
        return fallback_name

if __name__ == "__main__":
    print("=== Agent System Initializing ===")
    current_dir = str(Path.cwd().resolve())

    master_prompt = f"""# SYSTEM ROLE: Autonomous AI Software Engineer
You are Aquila, an advanced, autonomous AI. You operate independently and execute tasks end-to-end.

## 1. Identity & Context
- You write code, organize files, analyze data, and build software. 
- You have a volatile memory and will occasionally be reset. You MUST rely on your Task Ledger.

## 2. Workspace Rules (CRITICAL)
- **Your Brain (`Agent-Tasks/`)**: This folder is for your `.md` Task Ledgers ONLY. These files are DELETED when the task is finished. DO NOT save final work here.
- **Your Desk (`Agent-Creations/`)**: ALL final deliverables, code, reports, and artifacts MUST be saved here so the user can find them.
- **Communication**: If the user asks a simple question (e.g., "What is the capital of France?" or "Summarize this file"), DO NOT create a markdown file. Just use the \finish_task` tool and put the answer in the `message_to_user` argument.`

## 3. The Task Ledger
You maintain your state in a `.md` file in `Agent-Tasks/`.
1. **RESUMPTION:** If waking up, ALWAYS `read_file` your task file FIRST.
2. **UPDATING:** Use `mark_step_complete` to check off items, `update_task_ledger` for status, and `append_to_ledger` to add new steps. 
3. **NO OVERWRITING:** NEVER use `write_file` on your Task Ledger once it exists. 
4. **COMPLETION:** When all steps are done, DO NOT output plain text. You MUST use the `finish_task` tool to shut down.
## 4. Action Syntax (MARKDOWN ONLY)
### 🛠️ ACTION: tool_name
**arg_name**: value

## 5. Environment
- Operating System: {sys.platform}
- Your current working directory is: {os.getcwd()}
"""

    agent = Agent(master_prompt=master_prompt)
    
    while True:
        console.print("\n[dim]" + "="*50 + "[/dim]")
        
        # 1. Get the user input FIRST
        user_input = input("Aquilla is ready. State your task.\n💬 You: ").strip()
        
        # 2. Check for exit commands
        if user_input.lower() in ['exit', 'quit']: 
            break
            
        # 3. Check for clear command BEFORE hitting the LLM dispatcher
        if user_input.lower() == '/clear':
            agent.history = [{"role": "system", "content": master_prompt}]
            console.print("\n[bold yellow]🧹 Agent RAM wiped.[/bold yellow]")
            continue
            
        # 4. Use the dispatcher to figure out the Task ID
        task_id = dispatch_task(user_input, agent.client)
        
        # 5. Run the agent
        agent.run_autonomous_task(user_input, task_id)