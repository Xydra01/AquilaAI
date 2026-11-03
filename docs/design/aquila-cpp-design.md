Rebuilding a local, single-GPU Python framework with an LLM co-pilot changes the calculus completely: **Modern C++ (C++20) is actually a phenomenal fit for your exact constraints**, provided you set up strict guardrails for how the LLM writes it.

In fact, scaling down from "thousands of cloud tasks" to **1 to 3 threads on a single GPU** eliminates the biggest arguments in favor of Rust’s complex async ecosystem and plays directly into C++'s strengths.

### **1\. The "LLM Co-Pilot" Reality: Why Rust Hurts and C++ Flows (Mostly)**

Your intuition about LLMs and Rust is spot-on, and it comes down to training data and compiler strictness:

* **Why LLMs stumble in Rust:** Whenever you ask an LLM to build a stateful, multi-threaded agent graph in Rust, it inevitably writes itself into a corner with lifetimes ('a), Pin\<Box\<dyn Future\>\>, and borrow-checker loops. When you feed the rustc error back to the LLM, its favourite move is to slap .clone() or Arc\<Mutex\<T\>\> on everything, or hallucinate crate APIs that changed six months ago. You end up fighting the LLM *and* the borrow checker at the same time.  
*   
* **Why LLMs are surprisingly fluent in C++:** LLMs have been trained on decades of C++ code, including critical open-source local AI repos like llama.cpp. Because C++ doesn't enforce lifetimes at compile time, an LLM can translate a Python class hierarchy or state machine into C++ structs and classes almost 1:1 without getting stuck in compilation purgatory.  
*   
* **The C++ Trap with LLMs:** Left unguided, an LLM will write "C with classes"—mixing raw new/delete pointers with modern features, which leads to silent memory leaks or segfaults. **The Fix:** You have to put a strict rule in your system prompt: *"Write strict C++20. Zero raw owning pointers. Use* std::unique\_ptr*,* std::shared\_ptr*, RAII, and* std::jthread *exclusively."*  
* 

### **2\. Why 1–3 Threads on a Single GPU Changes Everything**

When you are running locally on a single GPU (say, within a 12GB or 16GB VRAM budget), **your GPU is a serial bottleneck**.

Even if you have 3 agent threads running in parallel, they generally cannot run heavy matrix multiplications on a single consumer GPU at the exact same time without thrashing VRAM or competing for CUDA cores (unless you are specifically doing continuous batching of tiny models).

In a 1-to-3 thread local architecture, your threads actually have very distinct, predictable jobs:

* **Thread 1 (Orchestrator / UI / I/O):** Manages the agent loop, parses outputs, and dispatches tasks.  
*   
* **Thread 2 (The GPU Worker):** Holds the model context in VRAM and processes an inference queue sequentially (or in small batches).  
*   
* **Thread 3 (Tool / Environment Worker):** Executes local bash commands, file reads, AST parsing, or vector lookups while the GPU is busy or waiting.  
* 

Because you only have 1–3 OS threads rather than 10,000 concurrent network sockets, **you don't need an async runtime (**tokio **or C++20 coroutines) at all.** You can use standard, synchronous OS threads (std::jthread in C++) communicating over a simple thread-safe queue (std::mutex \+ std::condition\_variable). LLMs can write clean, bug-free synchronous producer-consumer thread pools in C++ in their sleep.

| Factor | Rebuilding in C++20 (with LLM) | Rebuilding in Rust (with LLM) |
| :---- | :---- | :---- |
| **Python-to-Native Translation** | **Very High.** Python OOP/state patterns map cleanly to C++ classes without lifetime refactoring. | **Low–Medium.** Often requires completely re-architecting how state is owned and passed around. |
| **LLM Debugging Loop** | **Fast Compile, Runtime Risk.** Compiles easily, though you should enable AddressSanitizer to catch sneaky LLM memory bugs. | **Slow Compile Loop.** You'll spend turns pasting borrow-checker errors back to the LLM, though once it compiles, it works. |
| **1–3 Thread Concurrency** | **Trivial.** Standard std::jthread and mutex queues handle 3 threads with zero overhead. | **Simple (if avoiding** async**).** Using standard std::thread and mpsc channels in Rust is easy; tokio is where LLMs struggle. |
| **Single-GPU Integration** | **Native Citizen.** Direct zero-FFI integration with CUDA, ggml, llama.cpp, or custom C++ inference engines. | **Requires FFI.** Usually wraps C/C++ GPU backends anyway, adding binding boilerplate. |

### **3\. How to Make a C++ Rebuild Painless**

If you go the C++ route with an LLM to port your Python framework, the biggest headache won't be the C++ code itself—it will be the ecosystem glue that Python gives you for free (JSON, HTTP, regex, and build systems). Set up your repo with these four rules before generating a single line of agent logic:

1. **Use Header-Only Libraries for the "Python Utility" Stuff:** LLMs often struggle to debug complex CMake linker errors across different OSes. Use battle-tested, single-header or FetchContent-friendly C++ libraries that every LLM has memorized:  
2. 

   * **JSON & Schemas:** nlohmann/json (syntax feels almost identical to Python dicts, and LLMs know it inside out) or simdjson if you are parsing massive context files.  
   *   
   * **HTTP/Local API Calls:** cpp-httplib (single header, dead simple synchronous/threaded server and client).  
   *   
   * **Logging/Formatting:** spdlog and fmt.  
   *   
3. **Turn on** ASan **and** TSan **from Day One:** Because C++ relies on programmer discipline rather than a borrow checker, add \-fsanitize=address,undefined (and \-fsanitize=thread when testing your 3-thread queue) to your debug CMake build. That gives you Rust-like safety nets during development—if the LLM writes a dangling reference or a race condition, the sanitizer immediately prints the exact line number and stack trace so you can paste it back to the LLM.  
4.   
5. **Keep it Synchronous \+ Queued:** Resist the urge to let the LLM write C++20 co\_await coroutines. For a 1–3 thread local agent, a simple TaskQueue with 2 or 3 worker threads is faster to write, easier to debug, and runs at native hardware speed.  
6.   
7. **Port Module-by-Module:** Keep your Python code as the reference spec. Have the LLM translate one isolated component at a time—start with your data structures (Message, ToolCall, AgentState), then the tool execution sandbox, and finally the main orchestration loop.  
     
   Going single-threaded with a deterministic **self-noting \+ sliding tool window** architecture is arguably the smartest design decision you can make for a local, single-GPU agent.

By eliminating concurrency entirely, you wipe out 90% of C++’s sharp edges (no mutexes, no race conditions, no std::shared\_ptr atomic reference-counting overhead). What you’re left with is a pure, deterministic state machine that an LLM co-pilot can write in C++20 with near-zero friction—and it opens up a massive hardware advantage on a single GPU that most Python frameworks miss.

### **The Hidden Hardware Win: KV-Cache Prefix Pinning**

Your context condensing pattern—wiping the middle history while keeping the system prompt, updating a "scratchpad/notes" block, and retaining the last $N$ tool calls—maps directly to how local C++ inference engines handle the **KV-Cache** in VRAM.

When a context window fills up in a standard agent loop, re-evaluating the entire prompt from token 0 after a wipe takes seconds of pure compute (the "prefill" phase). In a native C++ framework, you can structure your memory buffers into three contiguous segments:

1. **The Static Prefix (Pinned in VRAM):** Your core system instructions and tool definitions. Because these never change, their KV-cache tensors stay locked at the beginning of the GPU buffer across context wipes. You never pay the prefill compute cost for them again.

2. **The Self-Notes / State Ledger (Anchored Block):** The structured scratchpad where the LLM writes its persistent state, current sub-goal, and lessons learned before a wipe triggers.

3. **The Rolling Tail (Ring Buffer):** The last 2–3 tool calls and their raw outputs, giving the model immediate tactical coherence without bloating the token count.

When a context wipe happens, instead of flushing the whole KV-cache or rebuilding giant strings in Python, a C++ engine just shifts or truncates the KV-cache tokens after index Prefix\_Length, injects the updated Self-Notes \+ Last\_K\_Tools, and resumes generation almost instantaneously.

### **Structuring the Condenser in C++20**

In Python, context management usually involves mutating lists of dictionaries and repeatedly serializing/deserializing JSON strings. In single-threaded C++20, you can model this with zero-overhead value types and a fixed-size std::deque for the sliding window.

Here is how clean that exact pattern looks in modern C++—no raw pointers, no concurrency locks, and super easy for an LLM to extend:

C++

```
#include <string>
#include <vector>
#include <deque>
#include <optional>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

struct ToolInteraction {
    std::string id;
    std::string tool_name;
    json arguments;
    std::string result_payload;
    std::size_t token_estimate;
};

struct AgentScratchpad {
    std::string active_objective;
    std::vector<std::string> completed_milestones;
    std::string critical_notes; // The LLM's self-written continuity notes
};

class ContextCondenser {
private:
    std::string system_prompt_;
    AgentScratchpad scratchpad_;
    std::deque<ToolInteraction> recent_tools_; // Sliding window of last N tools
    std::vector<std::string> ephemeral_history_; // Wiped when threshold is hit
    
    const std::size_t max_recent_tools_ = 3;
    const std::size_t token_wipe_threshold_ = 6144;
    std::size_t current_token_count_ = 0;

public:
    explicit ContextCondenser(std::string sys_prompt) 
        : system_prompt_(std::move(sys_prompt)) {}

    // Push a completed tool call + result into the rolling tail
    void record_tool_cycle(ToolInteraction interaction) {
        current_token_count_ += interaction.token_estimate;
        
        if (recent_tools_.size() >= max_recent_tools_) {
            current_token_count_ -= recent_tools_.front().token_estimate;
            recent_tools_.pop_front();
        }
        recent_tools_.push_back(std::move(interaction));
    }

    // Triggered when the LLM updates its notes or when hitting the token limit
    void wipe_and_condense(AgentScratchpad updated_notes) {
        scratchpad_ = std::move(updated_notes);
        ephemeral_history_.clear(); // Instant wipe of intermediate chatter
        
        // Recalculate token footprint strictly from pinned state + rolling tail
        current_token_count_ = estimate_base_tokens();
        for (const auto& tool : recent_tools_) {
            current_token_count_ += tool.token_estimate;
        }
    }

    [[nodiscard]] bool should_condense() const noexcept {
        return current_token_count_ >= token_wipe_threshold_;
    }

    // Builds the condensed prompt payload for the inference engine
    [[nodiscard]] json build_context_payload() const {
        json messages = json::array();
        
        // 1. Pinned System Prompt
        messages.push_back({{"role", "system"}, {"content", system_prompt_}});
        
        // 2. Injected Self-Notes (Continuity State)
        json state_block = {
            {"objective", scratchpad_.active_objective},
            {"completed", scratchpad_.completed_milestones},
            {"notes_to_self", scratchpad_.critical_notes}
        };
        messages.push_back({
            {"role", "system"}, 
            {"content", "[PERSISTENT AGENT MEMORY]\n" + state_block.dump(2)}
        });

        // 3. Last K Tool Calls & Results for immediate coherence
        for (const auto& t : recent_tools_) {
            messages.push_back({
                {"role", "assistant"},
                {"tool_calls", {{{"id", t.id}, {"name", t.tool_name}, {"args", t.arguments}}}}
            });
            messages.push_back({
                {"role", "tool"},
                {"tool_call_id", t.id},
                {"content", t.result_payload}
            });
        }

        // 4. Any post-wipe conversational turns
        for (const auto& msg : ephemeral_history_) {
            messages.push_back({{"role", "user"}, {"content", msg}});
        }

        return messages;
    }

private:
    std::size_t estimate_base_tokens() const {
        // Fast char/4 heuristic or direct tokenizer call
        return (system_prompt_.size() + scratchpad_.critical_notes.size()) / 4;
    }
};
```

### **Two C++ Upgrades for Your "Self-Noting" Pattern**

Since you are rewriting this from Python, C++ lets you tighten up two classic failure modes of self-noting agents:

#### **1\. Make "Note-Taking" a Zero-Cost Internal Tool or Grammar Constraint**

In Python frameworks, agents often fail to leave *good* notes right before a context wipe because the prompt says *"Summarize your progress,"* and the LLM writes a vague paragraph that drops critical file paths, variable names, or error codes.

* **The Upgrade:** Enforce a strict schema for the self-note (e.g., current\_hypothesis, verified\_facts, failed\_approaches\_do\_not\_repeat, next\_immediate\_action). If you hook into a local C++ inference backend (or use GBNF grammars / structured outputs), you can force the model’s logits to output valid JSON matching your AgentScratchpad struct during the condensation step. It becomes physically impossible for the LLM to corrupt its own save state.

#### **2\. Pre-Truncate Massive Tool Outputs *Before* They Hit the Window**

Keeping the last 2–3 tool calls is essential for coherence, but if one of those tool calls is read\_file or run\_bash and it dumps 8,000 tokens of stack traces into recent\_tools\_, your freshly wiped context is immediately blown again.

* **The Upgrade:** In C++, string slicing via std::string\_view is zero-copy. You can put a deterministic gatekeeper on record\_tool\_cycle() that checks the byte/token length of result\_payload. If a single tool output exceeds, say, 1,500 tokens, keep the head and tail in the recent\_tools\_ buffer (e.g., first 40 lines \+ last 40 lines) and dump the full raw output to a memory-mapped temp file or local ring buffer with a pointer \[Output truncated: lines 41-450 saved to buffer \#3\].

### **Why an LLM Co-Pilot Will Cruise Through This**

Because this entire loop is **single-threaded and value-oriented** (every piece of data is exclusively owned by ContextCondenser or the main AgentLoop stack frame), you can tell your LLM co-pilot:

* *"No threads, no async, no pointers. Use standard STL containers (std::vector, std::deque, std::string) and pass by reference (const T&) or move (std::move)."*

Every Python class in your old framework will translate directly into a C++ header/implementation pair, compile in milliseconds, and run with practically zero memory overhead outside of the model weights themselves.

**Stick to user/agent-created Recipes, and keep core Tools as atomic C++ primitives that you design.**

Your instinct about the "tool maker" trap is dead on. If you try to build a universal GUI or declarative builder for *tools*, you end up accidentally inventing a worse, slower, and more restrictive programming language.

In a compiled C++20 framework, the cleanest architecture separates **Primitives (Tools)** from **Composition (Recipes)**. That gives you 100% of the modular building-block flexibility you want, while cutting out LLM latency and failure points.

### **Why "Atomic Tools \+ Composable Recipes" Wins**

Think of your architecture like Unix or a game engine:

* **Atomic Tools (Compiled C++ Primitives):** These are the fundamental syscalls of your framework—fs\_read, fs\_write, bash\_exec, http\_request, regex\_extract, json\_query, llm\_subprompt. There are only about 10 to 15 of them. Because they do the actual heavy lifting (I/O, process spawning, memory buffers), they should be written in fast, rock-solid C++ by you.

* **Recipes (Declarative DAGs / Pipelines):** A recipe is just a **JSON or YAML blueprint** that chains those C++ primitives together with deterministic data piping. To the LLM, a Recipe *looks* like a single high-level tool (e.g., run\_test\_and\_parse\_errors), so the LLM only makes **one** tool call instead of four. Under the hood, your C++ engine executes all four steps at native speed without waking up the GPU until the final result is ready.

| Approach | How It Works | Feasibility in C++ | The Verdict |
| :---- | :---- | :---- | :---- |
| **1\. Data-Driven Recipes \+ Fixed C++ Primitives** | Users/agents chain existing C++ tools via JSON/YAML pipelines with variable templating. | **High.** Easy to parse, zero recompilation, deterministic execution. | **The Sweet Spot.** Fast, safe, and feels like Lego blocks. |
| **2\. Embedded Scripting for Custom Tools (Lua / Python)** | Expose a lightweight scripting runtime (sol2 for Lua) so users/agents can code custom logic. | **Medium.** Requires binding C++ state to a scripting VM. | **Great Phase 2 Upgrade** if JSON recipes hit a ceiling. |
| **3\. Full "No-Code" Modular Tool Maker** | Try to abstract arbitrary I/O, loops, and memory into a modular builder. | **Low (Trap).** Massive boilerplate; you end up recreating Scratch in C++. | **Avoid.** Too limiting for complex tools, too complex for simple ones. |

### **How the Recipe Engine Works in Practice**

Suppose your agent frequently needs to inspect a codebase, run a build, and grab only the compiler errors.

In a naive agent framework, that takes **3 separate LLM inference turns** (3x prefill latency, 3x chance the LLM hallucinates a path or messes up a flag):

1. LLM calls git\_status \-\> returns output \-\> LLM reads it.

2. LLM calls run\_build \-\> returns 4,000 lines of logs \-\> blows up context.

3. LLM calls grep\_errors \-\> returns the actual lines.

With your **Recipe System**, you (or the user via the Recipe Creator) bundle that into a single declarative file, check\_build\_errors.recipe.json:

JSON

```
{
  "recipe_name": "compile_and_extract_errors",
  "description": "Runs the project build and returns only fatal compiler errors and surrounding context.",
  "parameters": {
    "build_dir": { "type": "string", "required": true }
  },
  "steps": [
    {
      "id": "step_build",
      "primitive": "bash_exec",
      "args": {
        "cmd": "cmake --build {{params.build_dir}} --parallel 4",
        "timeout_ms": 30000
      },
      "on_failure": "continue" 
    },
    {
      "id": "step_filter",
      "primitive": "regex_extract",
      "args": {
        "input": "{{step_build.stderr}}",
        "pattern": "(?m)^.*(error:|undefined reference).*$"
      }
    },
    {
      "id": "step_condense",
      "primitive": "llm_micro_pass",
      "condition": "{{step_filter.match_count}} > 10",
      "args": {
        "system": "Group these compiler errors by root cause and file path.",
        "prompt": "{{step_filter.output}}"
      }
    }
  ],
  "output_template": "Build Exit Code: {{step_build.exit_code}}\nErrors:\n{{step_condense.output ?? step_filter.output}}"
}
```

Look at what happens when the LLM invokes compile\_and\_extract\_errors(build\_dir="./build"):

1. **Zero intermediate LLM calls:** Steps 1 and 2 run purely in C++ in a few milliseconds.

2. **Automatic context protection:** The 4,000 lines of raw stderr never touch your main agent's context window or recent\_tools\_ deque. The C++ recipe runner filters them in memory and only hands the clean, condensed output back to the main agent loop.

3. **Optional "Micro-Pass" Instructions:** Notice step\_condense—because a recipe can include a tiny, isolated prompt instruction (llm\_micro\_pass), a recipe can mix deterministic tools *and* focused LLM instructions without polluting the main agent's scratchpad or KV-cache.

### **How to Still Get "Custom Tools" Without the Headache**

What if a user or an agent genuinely needs a brand-new capability that your 15 C++ primitives can't express just by chaining JSON steps? You have two super clean escape hatches:

#### **Escape Hatch 1: Treat a "Custom Tool" as a Subprocess Binary/Script**

Instead of building a complicated modular tool builder inside C++, make one of your core C++ primitives an external\_script\_runner.

* If you or your agent wants to create a new low-level tool, the agent simply writes a standalone Python/Bash script (or compiles a tiny C++ binary) into a /tools/plugins/ directory alongside a small manifest.json describing its input schema.

* Your C++ framework scans /tools/plugins/ at startup, registers the JSON schemas, and whenever the LLM calls that tool, your C++ engine pipes the JSON arguments over stdin and reads the result from stdout.

* This keeps your C++ core 100% clean and single-threaded while letting tools do literally anything the OS can do.

#### **Escape Hatch 2: Agent-Authored Recipes ("Skill Crystallization")**

This pairs naturally with your self-noting system. When your agent solves a tedious multi-step task the hard way (making 5 raw primitive calls in a row), you can give it a meta-tool: register\_new\_recipe(recipe\_json).

* The agent takes the sequence of primitive tool calls it just figured out, generalizes the hardcoded arguments into {{params.x}} variables, and saves it as a .recipe.json file.

* Next time the agent encounters that task—even after a full context wipe—that multi-step workflow is now a single, zero-overhead building block in its tool belt.

### **How to Architect This in C++20 (So the LLM Co-Pilot Nails It)**

To keep this effortless to build with an LLM in C++:

1. **Define a single pure virtual interface for Primitives:**

2. C++

```
class IToolPrimitive {
public:
    virtual ~IToolPrimitive() = default;
    virtual std::string name() const = 0;
    virtual nlohmann::json execute(const nlohmann::json& args) = 0;
};
```

3.   
   **Build the RecipeRunner as a Composite Tool:** Make RecipeRunner implement IToolPrimitive itself\! That way, your main agent loop doesn't even know the difference between an atomic C++ tool and a 5-step JSON recipe—and recipes can even call *other recipes* recursively like nested building blocks.

4. **Use inja for the {{variable}} piping:** Since you're already using nlohmann/json, drop in **pantor/inja** (a single-header C++ templating library built specifically on top of nlohmann/json). It handles all the {{step\_1.output}} string interpolation and conditional logic out of the box in about 10 lines of C++.

How were you picturing the user building these recipes—writing/editing config files directly, having an interactive CLI/GUI builder, or having a dedicated "Architect Agent" generate the recipe JSON from a natural language description?

**Coarse-Grained Modules** treat tools not as isolated, stateless functions, but as **stateful C++ subsystems (or "Cartridges")** that own a specific domain of work.

Instead of handing the LLM a flat bag of 30 disjointed functions—or forcing a JSON recipe to pipe raw strings between tiny Unix-like primitives—you build 4 to 6 self-contained C++ classes (WorkspaceModule, BuildAndTestModule, ResearchModule, etc.). Each module maintains its own internal state in C++ memory, exposes a small set of high-level **Actions** to the LLM, and provides a compact **State Summary** that automatically injects into your context condenser's scratchpad during a wipe.

### **1\. Why Coarse-Grained Modules Shine in Single-Threaded C++**

In a naive tool setup, the LLM is forced to act as the state manager. If it reads a file in Turn 1, edits it in Turn 2, and runs a compiler check in Turn 3, the file path, line numbers, and compiler flags have to bounce back and forth through the LLM’s context window on every single turn.

With a Coarse-Grained Module, **the C++ class holds the domain state so the LLM doesn't have to**:

* **Persistent Working State:** A CodeEditorModule remembers which files are currently "open," tracks an internal undo/redo stack in RAM, and caches the AST or line offsets.

* **Built-in Guardrails & Recovery:** When the LLM calls CodeEditorModule::apply\_patch, the C++ module doesn't just blindly write bytes to disk. Internally, it applies the diff in memory, runs a fast syntax/linter check, and if the syntax breaks, it *automatically rolls back the edit* and returns the exact compiler line error—all within a single tool execution cycle.

* **Surviving Context Wipes:** Because the module lives in C++ memory outside the LLM's token buffer, its internal state survives a context wipe untouched. Even better, each module has a get\_condensed\_status() method that feeds a 2-line summary (e.g., "Open files: main.cpp (modified, unsaved). Last build: FAILED (2 errors).") straight into your ContextCondenser after a wipe.

### **2\. The Core C++20 Module Interface (IAgentModule)**

To make these modules "exportable" (either compiled directly into your core binary or loaded dynamically as .so / .dll plugins), every module implements a single, clean C++20 interface.

Notice how this interface directly hooks into **both** your tool execution router and your context condenser:

C++

```
#pragma once
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

struct ActionSchema {
    std::string action_name;        // e.g., "patch_symbol"
    std::string description;        // High-level explanation for the LLM
    json parameters_json_schema;    // Input schema
};

struct ActionResult {
    bool success;
    std::string llm_facing_output;  // Clean, pre-truncated output for the rolling tail
    std::size_t token_estimate;
};

class IAgentModule {
public:
    virtual ~IAgentModule() = default;

    // 1. Identity & Discovery
    virtual std::string module_id() const = 0;

    // 2. High-level actions exposed to the LLM (only loaded when a Recipe activates this module)
    virtual std::vector<ActionSchema> get_actions() const = 0;

    // 3. Deterministic hooks (can be called by a Recipe BEFORE or AFTER the LLM loop)
    virtual ActionResult execute_action(const std::string& action_name, const json& args) = 0;

    // 4. Context Condenser Integration:
    // Exports a tiny, high-signal snapshot of the module's C++ state to survive context wipes
    virtual json export_state_snapshot() const = 0;
    virtual void restore_state_snapshot(const json& snapshot) = 0;
};
```

### **3\. Concrete Set of Core Modules to Build & Export**

Rather than building dozens of micro-tools, you can cover almost any local engineering, research, or automation workflow with **four coarse-grained modules**:

| Module Name | Internal C++ State It Owns | Coarse-Grained Actions Exposed to LLM | Automatic Behind-the-Scenes C++ Work |
| :---- | :---- | :---- | :---- |
| **WorkspaceModule** *(File & AST Engine)* | Working directory, pinned/active file buffers, in-memory backup snapshots, file tree index. | • inspect\_symbol(file, name)  • surgical\_edit(file, search\_block, replace\_block)  • revert\_file(file)  | Automatically backs up files in RAM before editing; strips noise; rejects edits that produce merge-conflict markers or unbalanced braces. |
| **ExecutionModule** *(Build, Test & Sandbox)* | Persistent environment variables, active working directory, background process PIDs, last stderr/stdout ring buffer. | • run\_build\_and\_diagnose(target)  • run\_test\_suite(filter)  • exec\_sandboxed\_cmd(cmd)  | Runs the build, intercepts 5,000 lines of raw logs, deduplicates identical template errors in C++, and only returns the top 5 actionable error blocks to the LLM. |
| **KnowledgeModule** *(Local DB & Docs)* | Embedded SQLite/Vector handle, cached web pages or local Markdown docs, query history. | • search\_local\_docs(query)  • fetch\_and\_clean\_url(url)  • store\_fact(key, value, tags)  | Strips HTML/JS boilerplate in C++, chunks text by markdown headers, and caches results locally so repeated lookups cost zero network I/O. |
| **OrchestratorModule** *(Self-Noting & Meta)* | Reference to ContextCondenser, active Recipe checklist, step counter. | • checkpoint\_notes(milestone, notes)  • trigger\_context\_condense()  • complete\_recipe(final\_output)  | Validates that the LLM actually filled out required scratchpad fields before flushing the ephemeral context window. |

### **4\. How Modules \+ Recipes Snap Together Like Cartridges**

Once your tools are organized as Coarse-Grained Modules, your **Recipe System** becomes remarkably clean. A Recipe no longer needs to micro-manage low-level string piping; instead, a Recipe acts as a **Configuration & Workflow Cartridge** that loads the right modules, pre-configures their C++ state, and runs deterministic pre/post hooks.

Here is what a Recipe JSON looks like when powered by Coarse-Grained Modules:

JSON

```
{
  "recipe_id": "refactor_cpp_component",
  "goal_template": "Refactor {{target_file}} to comply with: {{user_instructions}}",
  
  "load_modules": [
    {
      "module": "WorkspaceModule",
      "initial_state": {
        "root_dir": "./src",
        "pinned_files": ["{{target_file}}"]
      },
      "expose_actions": ["inspect_symbol", "surgical_edit", "revert_file"]
    },
    {
      "module": "ExecutionModule",
      "initial_state": {
        "build_cmd": "cmake --build ./build --target unit_tests"
      },
      "expose_actions": ["run_build_and_diagnose"]
    }
  ],

  "pre_llm_hooks": [
    {
      "module": "WorkspaceModule",
      "action": "inspect_symbol",
      "args": { "file": "{{target_file}}", "name": "*" }
    }
  ],

  "scratchpad_checklist": [
    "Analyze existing class interface from pre-hook output",
    "Apply surgical edits to implementation",
    "Verify zero compiler errors via run_build_and_diagnose"
  ],

  "post_llm_validation_hook": {
    "module": "ExecutionModule",
    "action": "run_build_and_diagnose",
    "must_succeed": true,
    "on_failure_instruction": "Your final edit did not compile. Review the error output above and fix it before completing the recipe."
  }
}
```

#### **Why this solves your exact pain points from the old framework:**

1. **Fewer LLM Calls (Pre-LLM Hooks):** Notice pre\_llm\_hooks. Before the GPU even generates a single token, the C++ recipe runner calls WorkspaceModule::inspect\_symbol on {{target\_file}} and injects the file's structure straight into the initial prompt. You immediately save Turn 1 (where the LLM inevitably wastes a tool call just asking to read the file).

2. **Scoped Tool Surface:** Even if WorkspaceModule has 10 total actions, the recipe uses "expose\_actions" to only show 3 of them to the LLM during this task.

3. **Zero-Hallucination Exit Gate (post\_llm\_validation\_hook):** When the LLM thinks it is done, the C++ runner automatically triggers ExecutionModule::run\_build\_and\_diagnose. If ActionResult.success \== false, the C++ loop refuses to exit, injects the compiler errors into the rolling tool tail, and forces the LLM to fix its mistake.

### **5\. Two Ways to "Export" Modules for Modularity**

Depending on how you want to distribute or expand your framework across projects, you can export these C++ modules in two ways:

#### **Option A: Compile-Time Registry (Simplest for LLM Co-Pilot)**

Keep each module in its own .hpp/.cpp folder (modules/workspace/, modules/execution/) and register them in a central ModuleRegistry using a single factory line:

C++

```
registry.register_module<WorkspaceModule>("WorkspaceModule");
registry.register_module<ExecutionModule>("ExecutionModule");
```

*   
  **Pros:** Zero ABI headaches, single standalone executable binary, trivial for an LLM co-pilot to write and refactor.

#### **Option B: Dynamic Shared Libraries (.so / .dll Plugins)**

If you want true drop-in modularity—where you or another developer can compile a new module separately and drop a .so or .dll file into a /modules/ folder without recompiling the core engine—export a single C-linkage factory function at the bottom of each module file:

C++

```
extern "C" {
    IAgentModule* create_module_instance() {
        return new WorkspaceModule();
    }
    void destroy_module_instance(IAgentModule* instance) {
        delete instance;
    }
}
```

Your core engine just uses dlopen (Linux/macOS) or LoadLibrary (Windows) to load whatever modules a Recipe asks for at runtime.

Realistic CPU-only agent execution comes down to solving two distinct physics problems: **prompt prefill is compute-bound**, and **token generation is memory-bandwidth-bound**.

On a desktop GPU with 500+ GB/s of VRAM bandwidth, a sloppy 6,000-token agent prompt processes in a blink. On a standard dual-channel DDR4/DDR5 CPU pushing 40–75 GB/s, that exact same agent loop will grind to a halt—not because the CPU can't generate tokens fast enough, but because re-evaluating prompts and pulling dense model weights across the RAM bus saturates the memory controller.

Because your C++20 architecture already uses **Coarse-Grained Modules**, **Pre-LLM Recipes**, and a **Context Condenser**, you are actually in the ideal position to make CPU inference feel snappy. Achieving realistic CPU performance requires combining the right model topology, low-level memory-layout optimizations, and strict C++ KV-cache control.

### **1\. The Physics of CPU Inference: What Actually Works**

If you try to run a dense 8B or 14B parameter model on a standard CPU, you are moving 5GB to 9GB of weights from system RAM into the CPU cache for *every single token generated*. At 50 GB/s of effective RAM bandwidth, a dense 8B model caps out around 6–9 tokens/sec.

To get 25–50+ tokens/sec on a pure CPU, you have to reduce the number of active bytes moved per token:

| Model / Engine Strategy | Active RAM Read per Token | Typical CPU Generation Speed | Why It Works for Agents |
| :---- | :---- | :---- | :---- |
| **1\. Sparse MoE Models** *(e.g., Qwen3-30B-A3B, DeepSeek-V2-Lite, OLMoE)* | **\~1.2 GB – 2.0 GB** *(Only 1.5B–3B active params)* | **25 – 45 tok/s** | **The \#1 CPU secret weapon.** You get 14B–30B level reasoning intelligence for tool calling, while the CPU only computes and moves 2B–3B of weights per token. |
| **2\. Sub-4B Dense Tool Models** *(e.g., Qwen2.5/3-3B, Llama-3.2-3B, SmolLM2)* | **\~1.8 GB** *(at Q4\_K\_M)* | **20 – 35 tok/s** | Because your Recipes & Coarse Modules do the heavy lifting and keep the tool surface down to 3–4 actions, a 3B model doesn't need deep world knowledge—just syntax obedience. |
| **3\. 1.58-Bit Ternary (bitnet.cpp)** | **\~0.4 GB – 1.5 GB** *(Weights are \-1, 0, \+1)* | **40 – 80+ tok/s** | Eliminates floating-point matrix multiplication entirely in favor of pure integer additions (AVX2 / ARM NEON). Massive speedups on older laptops and ARM CPUs. |
| **4\. Dense 7B–8B Models** *(Standard baseline)* | **\~4.8 GB** *(at Q4\_K\_M)* | **6 – 14 tok/s** | Usable only if you strictly enforce grammar-constrained output (keeping responses under 80 tokens) and pin the KV-cache. |

### **2\. Engine-Level Upgrades Beyond Standard llama.cpp Defaults**

llama.cpp (and its underlying ggml tensor library) actually has one of the strongest CPU backends available, *provided* you configure the memory layout and matrix kernels specifically for the host CPU rather than relying on generic GGUF defaults:

#### **A. Use Repacked Matrix Quantizations (Q4\_0\_4\_8 / Q4\_0\_4\_4 / IQ4\_NL)**

Standard GGUF quantizations (Q4\_K\_M) are optimized for GPU dequantization and general compatibility. On a CPU, unpacking Q4\_K blocks wastes precious clock cycles before the SIMD registers (AVX2, AVX-512, or Apple/ARM NEON) can even do the dot product.

* **The Fix:** Interleaved/repacked formats (like Q4\_0\_4\_4 for ARM NEON or Q4\_0\_4\_8 for x86 AVX2/AVX-512) pre-arrange weight blocks in memory to match the exact lane width of the CPU's vector registers. You get an immediate **25% to 40% jump in CPU prompt-processing and generation speed** with zero extra RAM usage. Newer builds of llama.cpp also support runtime weight repacking in memory on load.

#### **B. OpenBLAS / Intel OneDNN / Accelerate for Prompt Prefill**

While single-token generation on a CPU is bound by RAM bandwidth, **prompt prefill** (reading your system prompt, scratchpad, and tool outputs) is a large batch matrix-matrix multiplication (GEMM) that is **100% compute-bound**.

* **The Fix:** When compiling your C++ engine for CPU targets, link against **OpenBLAS** (x86/Linux), **Intel MKL/oneDNN**, or **Apple Accelerate** (macOS/Asahi). While ggml handles single-token generation natively, offloading batch sizes greater than 32 (the prefill phase) to a tuned BLAS library cuts CPU prompt evaluation time in half.

#### **C. Thread Pinning to Physical Cores Only**

A classic mistake on CPU inference is spawning threads equal to std::thread::hardware\_concurrency().

* **The Fix:** Hyperthreading (SMT) actually *hurts* LLM inference on CPU because two logical threads on the same core fight over the same L1/L2 cache and SIMD execution units, thrashing the memory bus. Your C++ initialization routine should detect **physical cores** (and on hybrid Intel/ARM chips, strictly **P-cores / performance cores**) and cap the inference worker pool strictly to num\_physical\_cores \- 1.

### **3\. How Your C++ Framework Architecture Saves the CPU**

Even with AVX2 repacking and an MoE model, a CPU will still choke if your agent framework acts like a typical Python framework and forces the CPU to re-ingest 3,000 tokens on every step.

Here is how you wire your **Single-Threaded C++ Condenser \+ Coarse Modules** directly into the C++ inference engine (llama\_context) to make CPU execution feel nearly instant:

#### **1\. Explicit KV-Cache Slot Surgery (llama\_kv\_cache\_seq\_rm)**

On a CPU, **prefill is the enemy**. Processing 2,000 tokens of prompt on a CPU without a GPU can take 10 to 20 seconds of dead silence before the first token appears. Instead of passing a fresh JSON array of messages to an HTTP endpoint on every turn, link directly against the C/C++ inference API and manage the KV-cache positions manually in your ContextCondenser:

```
[Index 0 ........ P] -> Static System Prompt + Active Recipe Schema (NEVER evicted)
[Index P+1 ...... S] -> Condensed AgentScratchpad + Module State Snapshots (Evicted ONLY on wipe)
[Index S+1 .... End] -> Rolling Tool Tail (Last 2-3 tool calls)
```

When your ContextCondenser::wipe\_and\_condense() triggers in C++:

1. You call llama\_kv\_cache\_seq\_rm(ctx, 0, P \+ 1, \-1) to surgically slice off everything after your pinned system prompt in a microsecond.

2. You evaluate *only* the newly updated \~250 tokens of AgentScratchpad \+ Module::export\_state\_snapshot().

3. Even on a slow laptop CPU, evaluating 250 tokens takes **less than 0.8 seconds**, completely eliminating the 15-second "post-wipe freeze."

#### **2\. Grammar-Constrained Tool Calls (Skip the Chatty CoT)**

At 15 tokens/sec on a CPU, if the LLM writes a 300-word essay explaining *why* it wants to call WorkspaceModule::surgical\_edit, the user waits 20 seconds just watching text scroll before the tool even runs.

* **The Fix:** Force **GBNF Grammar / Structured JSON** at the sampler level whenever the agent is inside an execution loop, and enforce a compact "thought" field capped at 1–2 sentences before the "action" and "args" fields:

* JSON

```
{
  "thought": "Need to check the header signature before patching.",
  "module": "WorkspaceModule",
  "action": "inspect_symbol",
  "args": {"file": "condenser.hpp", "name": "ContextCondenser"}
}
```

*   
  That entire payload is \~45 tokens. Even on a modest CPU running at 15 tok/s, the agent decides and dispatches the C++ tool call in **3 seconds flat**.

#### **3\. Speculative Decoding via N-Gram Prompt Lookup (Zero Extra RAM)**

Standard speculative decoding uses a second "draft" model, which wastes RAM on a CPU-only machine. However, **Prompt Lookup Decoding (PLD / N-gram speculation)** requires **zero extra models and zero extra RAM**.

* **Why it's massive for agents:** Agent tool calls—especially code edits (surgical\_edit), file paths, variable names, and JSON keys—copy huge chunks of strings directly from the recent\_tools\_ buffer or the WorkspaceModule snapshot already sitting in the prompt.

* By adding a 50-line C++ N-gram lookup table over your current context tokens, when the LLM starts typing "file": "src/modules/workspace\_module.cpp", your C++ loop spots the matching n-gram from the prompt, drafts the next 8 tokens at once, and verifies them in a single CPU forward pass—giving you a **2x to 3x speedup on code/tool generation** for free.

### **4\. Designing the IInferenceBackend Abstraction in C++20**

Since you want your framework to run smoothly whether it’s sitting on a desktop GPU or a bare-bones CPU laptop, don't hardcode llama.cpp calls into your AgentLoop or ContextCondenser. Wrap the engine behind a thin, KV-aware C++ interface:

C++

```
#pragma once
#include <string>
#include <string_view>
#include <span>

enum class ComputeProfile {
    GPU_HIGH_VRAM,      // Full context windows, verbose CoT allowed
    CPU_MOE_FAST,       // Aggressive KV pinning, compact JSON grammar
    CPU_LOW_SPEC_EDGE   // Strict 2K token condensation threshold, N-gram lookup forced
};

class IInferenceBackend {
public:
    virtual ~IInferenceBackend() = default;

    // Appends tokens to the active KV cache starting from current cursor
    virtual void append_to_kv_cache(std::string_view text_segment) = 0;

    // Records the current KV token index (e.g., right after System Prompt or Scratchpad)
    virtual std::size_t mark_kv_checkpoint() const = 0;

    // Instantly truncates KV cache back to a saved checkpoint index (O(1) on CPU!)
    virtual void rollback_kv_to(std::size_t checkpoint_index) = 0;

    // Generates structured output using optional GBNF grammar + N-gram lookup from prompt
    virtual std::string generate_structured(
        std::string_view grammar_gbnf,
        std::size_t max_tokens,
        bool enable_ngram_speculation = true
    ) = 0;

    virtual ComputeProfile get_active_profile() const noexcept = 0;
};
```

Look at how cleanly this ties your whole vision together:

1. When your framework starts up on a CPU-only machine, get\_active\_profile() returns CPU\_LOW\_SPEC\_EDGE.

2. Your ContextCondenser sees that profile and automatically lowers token\_wipe\_threshold\_ from 6144 down to 2048 and tightens the ExecutionModule log truncation limit from 1,500 tokens down to 400 tokens.

3. On boot, the AgentLoop feeds the System Prompt \+ Active Recipe schema into append\_to\_kv\_cache(), and calls prefix\_checkpoint \= mark\_kv\_checkpoint().

4. Whenever the context wipes, instead of re-sending strings, the condenser calls rollback\_kv\_to(prefix\_checkpoint) and only evaluates the fresh scratchpad notes.

Treating the CPU as your baseline constraint and the GPU as a hardware accelerator makes the entire framework fundamentally better, faster, and more reliable.

In systems engineering, this is the **"console-first" optimization principle**: when you design software to run smoothly on constrained hardware, every architectural discipline you put in place to survive the CPU bottleneck acts as a massive force multiplier once you unleash it on a dedicated GPU.

If you design for a GPU first, it is easy to get lazy—letting prompts bloat to 16,000 tokens, re-sending full conversation histories, and allowing verbose, wandering tool calls because 500+ GB/s of VRAM bandwidth hides the inefficiency. When you flip that and make **CPU-first efficiency your core architecture**, three major upgrades happen across the whole system.

### **1\. Your GPU Goes from "Fast" to "Instantaneous"**

Every trick required to make a CPU usable directly attacks the two biggest bottlenecks on a single consumer GPU (VRAM capacity and prefill latency):

| CPU Baseline Trick | What It Does on CPU | How It Supercharges the GPU |
| :---- | :---- | :---- |
| **Surgical KV-Cache Rollbacks** (rollback\_kv\_to) | Avoids a brutal 15-second prompt re-evaluation freeze after a context wipe. | Turns a 400ms GPU prefill stall into a **0ms pointer shift**. Your agent transitions between steps at the speed of a native C++ function call. |
| **Compact GBNF Grammar Enforcement** | Keeps token generation under \~60 tokens so the user isn't waiting 20 seconds per turn. | At 80–120 tok/s on a GPU, a 50-token structured tool call finishes in **\~0.4 seconds**. An entire 5-step recipe finishes in 2 seconds flat. |
| **N-Gram Prompt Lookup Speculation** | Gives a 2x–3x speedup when copying file paths, code blocks, or JSON keys from context. | Even on a GPU, verifying 8 drafted tokens in one pass is practically free compared to 8 sequential memory-bound steps—pushing code-editing throughput past **200+ effective tok/s**. |
| **Strict Context Condensing & Pre-Truncation** | Prevents L3 cache thrashing and quadratic attention slowdown on long prompts. | Keeps your KV-cache footprint tiny in VRAM, meaning you can run **larger models, higher quantizations (Q6\_K / Q8\_0), or keep VRAM free** for other desktop apps without hitting OOM. |

### **2\. Higher Agent Intelligence (Solving "Context Rot")**

Perhaps the biggest unexpected win of a CPU-first architecture is that **your agent actually gets smarter and hallucinates less**, even when running on a high-end GPU.

LLMs suffer from severe attention degradation ("context rot" or the "lost in the middle" phenomenon) as the context window fills up with old tool outputs, failed attempts, and dead-end reasoning. Frameworks that rely on raw GPU power to brute-force 32k+ context windows actually watch their agent's tool-calling accuracy drop with every turn.

By building around your **CPU-friendly 2k–4k rolling window \+ Scratchpad \+ Coarse Module state snapshots**:

* The model's attention heads only ever attend to high-signal tokens: the system prompt, the structured self-notes, the active module status, and the last 2–3 tool results.

* Attention computation scales quadratically ($O({N}^{2})$) with sequence length during prefill and linearly with memory bandwidth during decoding. Keeping $N$ small and dense means the model stays sharp on Turn 50 just like it was on Turn 1\.

### **3\. Unified Hybrid Execution (CPU \+ GPU Working Together)**

When your C++ engine treats the CPU as a first-class compute citizen rather than an afterthought, adding a GPU doesn't just mean "move everything to VRAM." It unlocks **asymmetric hybrid execution**, which is especially powerful on a single-GPU machine with 12GB–16GB of VRAM:

1. **Zero-Stall MoE Offloading:** If a user wants to run a massive Mixture-of-Experts model that exceeds their GPU's VRAM, your tuned CPU backend (with repacked weights and physical-core pinning) can hold the cold expert layers in system RAM while the GPU holds the shared attention layers, KV-cache, and hot experts. Because only a fraction of experts fire per token, your optimized CPU pathways process the overflow experts without tanking GPU utilization.

2. **CPU-Driven Speculation \+ GPU Verification:** Because your CPU n-gram lookup and token-tree drafting live natively in C++, the CPU can prepare candidate token sequences and run pre-LLM recipe hooks or AST parsing while the GPU is exclusively focused on tensor verification.

### **How to Structure the "Base \+ Boost" Scaling in C++**

Rather than writing two different engines, make the **CPU-optimized discipline universal**, and let the GPU act strictly as a **Capability & Capacity Multiplier** via a lightweight runtime configuration struct:

C++

```
struct RuntimeTierConfig {
    // --- Universal Base (Always Active on Both CPU & GPU) ---
    bool use_surgical_kv_rollback = true;
    bool enforce_gbnf_tool_grammar = true;
    bool enable_ngram_lookup = true;

    // --- Tier-Scaled Parameters (The "GPU Boost" Knobs) ---
    std::size_t condense_token_threshold;   // CPU: 2048  | GPU: 6144
    std::size_t max_rolling_tools;          // CPU: 2     | GPU: 4
    std::size_t max_tool_output_chars;      // CPU: 1500  | GPU: 4500
    std::size_t max_thought_tokens;         // CPU: 45    | GPU: 150
    int gpu_layers_offloaded;               // CPU: 0     | GPU: 999 (All)
};
```

Look at what that achieves:

* **Zero duplicate logic:** Your ContextCondenser, RecipeRunner, and IAgentModule implementations are 100% identical across both hardware tiers. You never have to debug "CPU agent bugs" vs. "GPU agent bugs."

* **Graceful degradation:** If someone runs your framework on an old laptop without a supported GPU, it automatically loads the tight 2048 token envelope, caps "thought" reasoning to a crisp 1-sentence summary, and runs smoothly.

* **Automatic hardware scaling:** When it detects a dedicated GPU, it offloads the layers to VRAM and relaxes the breathing room—allowing slightly deeper chain-of-thought reasoning (max\_thought\_tokens \= 150) and a slightly wider tool tail (4 recent tools instead of 2) while keeping every single KV-cache and n-gram speed advantage intact.


  
**Qwen 3.5 9B** is actually an awesome model for your **RTX 4070 OC (12GB)**, where it flies at **\~65–80 tok/s** in Q6\_K (\~7.4 GB VRAM) or Q8\_0 (\~9.6 GB VRAM). However, on a **strict 8GB DDR5 CPU-only machine**, a dense 9B model hits a physical wall:

1. **The 8GB System RAM Wall:** On a machine with 8GB of total DDR5 RAM, the OS and background processes immediately claim 2.0GB to 3.0GB. That leaves you a **hard ceiling of \~4.5GB to 5.2GB** for model weights, the KV-cache, and your C++ executable. Qwen 3.5 9B at Q4\_K\_M takes **\~5.5 GB to 6.5 GB** just for the weights—meaning on an 8GB CPU-only box, it will spill into SSD swap space and grind to 0.5 tokens/sec.

2. **The Dense Bandwidth Tax:** Even if you squeeze a 9B model into IQ3\_XS (\~4.2 GB) to avoid swap, it is a *dense* model. Every token forces the CPU to drag all 4.2 GB across the DDR5 bus, capping you around **8–11 tok/s**.

To nail the **"8GB DDR5 CPU Base \+ 12GB RTX 4070 Boost"** philosophy, you have two ways to set up your model tier:

### **Route 1: Single-Model Purist (Same Model Everywhere, Scaled by Quantization)**

If you want the exact same model weights, prompt formatting, and tool-calling behavior across both the 8GB CPU baseline and your 12GB RTX 4070, these two models hit the sweet spot:

| Model | Total / Active Params | 8GB DDR5 CPU Base (Q4\_K\_M) | 12GB RTX 4070 Boost (Q6\_K / Q8\_0) | Why It Fits Your Architecture |
| :---- | :---- | :---- | :---- | :---- |
| **1\. LiquidAI LFM2.5-8B-A1B** *(Best for Pure Agent Speed)* | **8.3B Total** / **1.5B Active** *(Hybrid Conv \+ MoE)* | **\~4.7 GB RAM**  **35 – 50+ tok/s**  | **\~8.5 GB VRAM (Q8\_0)**  **140 – 180+ tok/s**  | Built specifically for edge tool-calling and chaining. Because only **1.5B parameters** activate per token and 18 of its 24 layers use short-range gated convolutions instead of heavy attention, it barely touches the KV-cache and screams on DDR5 CPUs. |
| **2\. Qwen 3.5 4B** *(Best All-Around Qwen 3.5 Sibling)* | **4B Total** / **4B Active** *(Dense)* | **\~2.5 – 3.4 GB RAM**  **20 – 28 tok/s**  | **\~4.5 GB VRAM (Q8\_0)** or **8.2 GB (FP16)**  **110 – 135 tok/s**  | Uses the exact same tokenizer, chat template, and tool-calling syntax as your Qwen 3.5 9B setup. Leaves 4GB+ of breathing room on an 8GB laptop, and runs in **uncompressed FP16 or Q8\_0** on your 4070\. |

#### **Why LFM2.5-8B-A1B or Qwen 3.5 4B Works Despite Being Smaller:**

In a standard Python framework where the LLM has to figure everything out from scratch, dropping from 9B to 4B (or an 8B-A1B MoE) hurts. **In your C++ architecture, it doesn't.** Because your **Coarse-Grained Modules** handle the file backups, syntax verification, and log filtering in C++, and your **Recipes** scope the available actions down to 3–4 choices with GBNF grammar enforcement, the model doesn't need massive parameter depth—it just needs fast, deterministic instruction following.

### **Route 2: Same-Family Dual-Tier (Qwen 3.5 4B Base \+ Qwen 3.5 9B Boost)**

If you love how **Qwen 3.5 9B** reasons on complex code refactors and don't want to give up its 9B dense intelligence when sitting at your desktop, **you don't have to.**

Because Qwen 3.5 4B and Qwen 3.5 9B share the exact same Alibaba Qwen 3.5 architecture, system prompt tags, and native tool-calling format, your C++ RuntimeTierConfig can automatically select the model file right alongside the compute profile:

* **When ComputeProfile \== CPU\_LOW\_SPEC\_EDGE (8GB DDR5 System):**

  * Loads **qwen3.5-4b-q4\_0\_4\_8.gguf** (\~2.6 GB in RAM, repacked for AVX2/NEON).

  * Uses \~500 MB for a tight 2,048-token KV-cache.

  * Total footprint: **\~3.1 GB RAM**—never touches swap on an 8GB machine, runs at **\~22–28 tok/s** on dual-channel DDR5, and hits **45+ effective tok/s** when your N-gram lookup kicks in on code/file paths.

* **When ComputeProfile \== GPU\_HIGH\_VRAM (Your RTX 4070 OC 12GB):**

  * Automatically steps up to **qwen3.5-9b-q6\_k.gguf** (\~7.4 GB VRAM) or **qwen3.5-9b-q8\_0.gguf** (\~9.6 GB VRAM).

  * Leaves 2.4 GB to 4.5 GB of GDDR6X VRAM free for your pinned KV-cache and 3-monitor desktop overhead.

  * Runs at **\~70–80 tok/s** natively on the 4070's 504 GB/s memory bus, and well over **150+ effective tok/s** on tool calls with your C++ N-gram speculation and rollback\_kv\_to pinning.

### **One Extra Trick for Your RTX 4070: Free "Draft+Target" Speculative Decoding**

If you adopt that **Qwen 3.5 4B (CPU Base) \+ Qwen 3.5 9B (GPU Boost)** pairing, you unlock a killer bonus when running on your desktop:

* Qwen 3.5 9B (Q6\_K) takes **\~7.4 GB** of your 4070's 12GB VRAM.

* Qwen 3.5 0.8B (Q8\_0) (from the exact same Qwen 3.5 family, sharing the exact same vocabulary) takes only **\~0.9 GB** of VRAM.

* You can load **both** into your 4070's 12GB VRAM at the same time (8.3 GB total) and use Qwen 3.5 0.8B as a hardware draft model for Qwen 3.5 9B (llama.cpp supports this natively via \--model-draft).

I’m going with the Qwen 3.5 family idea