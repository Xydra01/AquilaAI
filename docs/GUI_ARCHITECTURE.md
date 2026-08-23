## Aquila GUI Architecture (PySide6)

This document describes how the **PySide6 GUI** in `agent/gui/gui.py` and `agent/gui/gui_pages/` connects to Aquila’s core agent in `agent/core/main.py`. It is intended as a handoff for a **UI-focused LLM (e.g. Google Gemini)** to propose a **visual/UX redesign only**, while keeping all behavioral hooks and data flows intact.

---

## 1. High-level flow: GUI ↔ Agent ↔ Tools

At runtime there are three main layers:

- **GUI layer (PySide6)**
  - `QApplication` / `QMainWindow` in `agent/gui/gui.py`
  - Mode-specific pages under `agent/gui/gui_pages/` (`ChatPage`, `TaskPage`, `CodeIdePage`, `ResearchPage`, `WritingPage`, `CharacterPage`, `LearnPage`, `HomePage`, `SettingsPage`; `DataPage` when `AQUILA_ENABLE_DATA_PROCESSING=1`)
  - Shared widgets: `AgentRail`, `ExecutionLogPanel`, rich-text views
- **Worker bridge**
  - `AgentWorker(QThread)` in `agent/gui/gui.py` (and some smaller helpers like chat subcalls)
- **Agent core**
  - `Agent` + tool loop in `agent/core/main.py`
  - Tools in `agent/core/tools.py` and `agent/tool_library/*`
  - Memory (`DualMemorySystem` via `memory_singleton.py`), ledgers and deliverables under `Agent-*` dirs

### 1.1 Runtime data flow

```mermaid
flowchart LR
  subgraph guiLayer [GUI Layer (PySide6)]
    mainWindow[MainWindow (gui.py)]
    stacked[QStackedWidget\nmode pages]
    agentRail[AgentRail\n(chat input, history, buttons)]
  end

  subgraph workerLayer [Worker Thread]
    agentWorker[AgentWorker (QThread)]
  end

  subgraph coreLayer [Agent Core]
    agentBrain[Agent (main.py)]
    loopEngine[LoopEngine\n(run_unified_task)]
    tools[Tools + Tool Library]
    ledgers[JSON ledgers\nAgent-Tasks / Agent-Plans]
    memory[DualMemorySystem\n(memory_singleton)]
  end

  mainWindow --> stacked
  stacked --> agentRail

  mainWindow -->|start task/chat| agentWorker
  agentRail -->|user input, attachments| agentWorker

  agentWorker -->|run_chat / run_character_chat / run_unified_task| agentBrain
  agentBrain --> loopEngine
  loopEngine --> tools
  loopEngine --> ledgers
  loopEngine --> memory

  agentWorker -->|ledger_signal (stream)| mainWindow
  agentWorker -->|finished_signal| mainWindow
  agentWorker -->|ask_user_signal| mainWindow

  mainWindow -->|update UI| stacked
```

Key properties:

- **All long-running work** (LLM calls, tool loop) runs in `AgentWorker(QThread)`, not the UI thread.
- The UI is updated **only via signals** and page methods (see the `BaseModePage` contract below).
- The agent core and tool loop **must not be reimplemented** in the UI layer; the UI simply **orchestrates** calls and renders state.

---

## 2. Main window and mode selection

### 2.1 Mode registry

[`agent/gui/gui_modes.py`](agent/gui/gui_modes.py) defines the mapping between **labels** and **mode flags**:

- `WORKSPACE_MODE_FLAGS`: e.g. `"Chat Mode" → "chat"`, `"Autonomous Task" → "autonomous"`, `"Code Mode" → "code"`, `"Research Mode" → "research"`, `"Writing Mode" → "writing"`, `"Character Mode" → "character"`, `"Learn Mode" → "learn"`. `"Data Processing" → "data"` appears only when `AQUILA_ENABLE_DATA_PROCESSING=1`.
- `INSTANCE_DEFAULT_MODE_IDS` is the set of valid short IDs stored on instances.
- `workspace_label_for_default_mode()` and `normalize_default_mode_id()` convert between labels and internal IDs.

The main window uses this mapping to:

- Populate the **workspace selector** on the home screen.
- Decide which `BaseModePage` subclass to show in the `QStackedWidget`.

### 2.2 Mode pages

All workspace pages inherit from [`agent/gui/gui_pages/base.py`](agent/gui/gui_pages/base.py):

- Base class: `BaseModePage(QWidget)`
- Attributes:
  - `MODE: str` (e.g. `"chat"`, `"autonomous"`, `"code"`)
  - `MODE_LABEL: str` (e.g. `"Chat Mode"`, `"Code Mode"`)
- Constructor: `__init__(self, main_window)` receives the owning main window instance. The page may call back to the main window for “global” operations such as starting tasks, opening attachment dialogs, or ejecting the Ollama model in Code Mode.

The main window keeps one instance of each page and swaps them into the stacked widget based on the current mode flag.

---

## 3. AgentWorker: bridge between GUI and Agent

The central execution bridge is `AgentWorker(QThread)` in [`agent/gui/gui.py`](agent/gui/gui.py).

### 3.1 Construction

The main window creates an `AgentWorker` with:

- `task_name`: string label used to construct ledger filenames under `Agent-Tasks/` / `Agent-Plans/`
- `prompt`: current user prompt
- `mode`: mode flag (`"chat"`, `"autonomous"`, `"research"`, `"writing"`, `"code"`, `"character"`, `"learn_tutor"`, etc.)
- `attached_chunks`: text chunks from file attachments (see §4)
- `attached_images`: base64 image payloads for vision
- `chat_history`: prior messages for streaming chat modes
- `instance_id`: current Aquila instance (for multi-instance memory)
- `persona_id`, `persona_research_lore` (Character AI)
- `course_id`, `archive_id`, `archive_title`, `node_id` (Learn mode)

The main window also calls `current_page.bind_worker(worker)` so each `BaseModePage` knows which worker is active.

### 3.2 Signals

`AgentWorker` defines three Qt signals:

- `ledger_signal: Signal(str)` — emitted with incremental text during streaming; used for chat bubbles and/or execution log.
- `finished_signal: Signal(str)` — emitted when the run finishes with the full assistant text.
- `ask_user_signal: Signal(str)` — emitted when the agent invokes `agent_tools.USER_INPUT_CALLBACK` and needs a GUI prompt/response loop.

These are connected by the main window to slots that delegate to the current `BaseModePage` implementation (see §5).

### 3.3 Run loop

`AgentWorker.run` roughly does:

- Set the active instance (`set_active_instance_id(self.instance_id)`).
- Acquire an `Agent` instance via `get_agent(instance_id)` from `main.py`.
- Branch on `self.mode.lower()`:
  - `"chat"` → `agent.run_chat(...)`, or `run_light_research_chat` / `run_light_coding_chat` when the Chat context toggles are on.
  - `"character"` → `agent.run_character_chat(...)` (persona aware).
  - `"learn_tutor"`, `"learn_archive_chat"` → tutor/archive chat helpers.
  - All other modes (task, research, writing, code, character_build, learn_build, etc.) → `agent.run_unified_task(...)`.
- For streaming call paths, iterate over chunks, accumulate `full_text`, emit `ledger_signal` for each token or chunk, and finally emit `finished_signal(full_text)`.
- For `USER_INPUT_CALLBACK`, set `agent_tools.USER_INPUT_CALLBACK = self._ask_user_bridge`, which emits `ask_user_signal` and blocks on a `threading.Event` until the GUI provides the reply.

**Important for redesign:** The worker owns all interactions with `Agent` and tools. The GUI must continue to use this abstraction rather than calling `Agent` directly on the UI thread.

---

## 4. Attachments pipeline

### 4.1 From file picker to text chunks

The attachment workflow is:

1. User clicks an attachment button in the current page (usually on an `AgentRail` or in Code Mode’s right-hand panel).
2. The main window opens a file dialog and uses functions from [`agent/file_parser.py`](agent/file_parser.py):
   - `attachment_dialog_filter` to configure the filter (PDF, DOCX, images, code, etc.).
   - `process_local_attachments` to load and chunk text into `text_chunks` and encode images.
3. The resulting `attached_chunks` and `attached_images` arrays are passed into `AgentWorker`.

### 4.2 Injection into prompts

Some modes (e.g., Chat and Character) also use `format_attachment_context` from `main.py`:

- `format_attachment_context(text_chunks)` builds a capped “ATTACHED CONTEXT” block inserted into the user message.
- This block is used by `agent.run_chat` / `agent.run_character_chat` as an in-context supplement to the prompt text.

`AgentWorker` stores both the original `self.prompt` and `self.model_user_content` (prompt + attachment block) for logging.

---

## 5. Mode page contract (`BaseModePage`)

All mode pages must implement the public interface defined in [`agent/gui/gui_pages/base.py`](agent/gui/gui_pages/base.py). This is the primary hook surface that must **not** change when redesigning the UI.

### 5.1 Class and lifecycle

```python
class BaseModePage(QWidget):
    MODE: str = \"\"
    MODE_LABEL: str = \"\"

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self._worker = None
```

Methods of interest:

- `mode_flag(self) -> str` — returns the mode ID.
- `on_activate(self)`, `on_deactivate(self)` — optional hooks when page is shown/hidden.
- `bind_worker(self, worker)` — main window calls this when starting a run.

### 5.2 Chat and streaming API

Pages that show streaming chat or logs implement:

- `append_chat_html(html: str)` — append formatted HTML to the conversation area.
- `clear_chat_display()` — reset the conversation/log display.
- `begin_assistant_stream()` — optional: mark the start of a new assistant message.
- `stream_chat_token(token: str)` — append a streamed token (used for live typing effects).
- `finalize_streamed_message(raw_text: str)` — finalize a streamed message into a stable bubble or log entry.

The main window wires `AgentWorker.ledger_signal` and `finished_signal` into these methods depending on the active page.

### 5.3 Input and buttons

Required for pages that start runs:

- `get_chat_input_text() -> str` — returns the current prompt text.
- `clear_chat_input()` — clear the prompt input after a run starts/completes.
- `set_run_buttons_running(running: bool)` — toggle Run/Stop/Resume buttons (disable run button while a worker is active, enable stop, etc.).

Different pages provide different UI for these hooks:

- `ChatPage` delegates everything to `AgentRail` (single-column chat).
- `TaskPage` and `ResearchPage` use `AgentRail` plus additional panels.
- `CodeIdePage` uses its own right-hand chat/log panel instead of `AgentRail` but exposes equivalent properties (`chat_input`, `chat_history`, `attach_button`, `run_btn`, `stop_btn`, etc.).

### 5.4 Ledger and state

Pages that show structured task state implement:

- `update_ledger(text: str, *, clear: bool = False)` — append to or reset the execution log.
- `refresh_state()` — re-read current ledger / draft / code buffer from disk and update the “state” panel.

State resolution/rendering is centralized in [`agent/gui/gui_state.py`](agent/gui/gui_state.py):

- `resolve_ledger_path(mode, task_name)` — determines which JSON file to open based on mode:
  - Writing: `Agent-Drafts/active_draft_state.json` or fallback to `Agent-Tasks/{task}.json`.
  - Code: `Agent-Code/active_code_state.json` or fallback to `Agent-Tasks/{task}.json`.
  - Research: `Agent-Plans/{task}.json`.
  - Autonomous/task: `Agent-Tasks/{task}.json`.
- `render_step_ledger_html(state)` — generates an HTML checklist for step-by-step task progress.
- `render_writing_draft_html(state)` — renders the current writing draft.
- `render_code_canvas_html(state_data, task_ledger)` — renders Code Mode project state and relates it to the current tool-step.

Pages like `TaskPage` and `CodeIdePage` call these helpers in `refresh_state()` and display the results in rich-text panes.

### 5.5 Extra context and attachments per page

Optional methods:

- `get_extra_run_context() -> str` — additional text that should be prepended/appended to the prompt (e.g., selection summaries, journal excerpts).
- `get_extra_text_chunks() -> list[str]` — extra attachment chunks specific to the page.

When present, the main window includes these in the arguments passed to `AgentWorker`.

---

## 6. Mode pages overview

For a visual redesign, you can change the internal layouts and widgets of each page as long as the **external behavior and method contract** stay the same.

Key pages:

- `ChatPage` (`agent/gui/gui_pages/chat_page.py`)
  - Chat workspace with `AgentRail` (prompt, attachments, history, run/stop/clear) plus a right **Context** pane.
  - Context pane: attachment summary, **Light web research** checkbox, **Light coding** toggle (Open repo / Use Code IDE project / Clear / Refresh), token stats, and **Open in Code Mode** handoff.
- `TaskPage` (`agent/gui/gui_pages/task_page.py`)
  - Three-column layout: left `AgentRail`, middle plan + output preview, right `ExecutionLogPanel` with ledger/state tabs.
  - Uses `resolve_ledger_path` + `render_step_ledger_html` to show an expanding checklist of steps.
- `ResearchPage` (`agent/gui/gui_pages/research_page.py`)
  - Similar to Task, but with research-specific panels (journal, references, etc.).
- `WritingPage` (`agent/gui/gui_pages/writing_page.py`)
  - Focused on drafts and sections; uses `render_writing_draft_html` for state.
- `CodeIdePage` (`agent/gui/gui_pages/code_ide_page.py`)
  - Left: file tree; center: editor tabs; right: chat/log + lint/test/state views (see §7).
  - Bottom row: pending patch queue and actions (Accept/Reject).
- `CharacterPage`, `LearnPage`, `HomePage`
  - Character: persona management + in-character chat.
  - Learn: syllabus build, tutor, and archives.
  - Home: instance selector, mode chooser, quick links.

You may **reorganize layouts** (e.g., consolidate logs, add sidebars, use tabs instead of splitters) as long as the same data is shown and the same hooks are honored.

---

## 7. Code Mode IDE hooks

`CodeIdePage` is the most complex page from a data-flow perspective. For a visual redesign it is critical to preserve its integrations.

### 7.1 Project lifecycle

Code Mode integrates with `tool_library.code_canvas_tools` via several actions:

- **Open in-place** (`_open_in_place`)\n  - Calls `attach_existing_repo(path, name)`.\n  - Treats the selected directory as the live codebase; tools operate in-place.\n- **Import sandbox** (`_import_sandbox`)\n  - Calls `import_codebase(path, name, workspace_mode=\"sandbox\")`.\n  - Copies files into a managed sandbox under `Agent-Code/`.\n- **New project** (`_new_project`)\n  - Calls `init_code_project(\"new_project\", \"\", \"python\")` (defaults to Python starter).\n- **Sync to disk** (`_sync_disk`)\n  - Calls `sync_project_to_disk()` to apply queued changes to the underlying repo.\n

### 7.2 Editing and buffer save

The center editor tabs are backed by an in-memory buffer and persisted via tools:

- Each open file tab has an associated path stored in `self._tab_paths`.\n- On manual **Save buffer** (`_save_buffer`):\n  - Fetch current editor text, call `apply_user_buffer_edit(path, contents)`.\n  - Clear “dirty” markers on success and refresh state.\n- On idle editing (stop typing for ~400ms):\n  - `_schedule_editor_save` starts a `QTimer`.\n  - `_flush_editor_save` calls `apply_user_buffer_edit` to keep the code canvas in sync and mark files dirty.\n

### 7.3 Lint/tests/state panes

The bottom split shows three read-only panes:

- **Problems** — lint diagnostics.\n- **Tests** — pytest output summary.\n- **State** — Code canvas state as HTML from `render_code_canvas_html`.\n

These panes are updated based on the JSON state written by code tools and the tool loop. A redesigned UI can change **how** they’re laid out (tabs, side panels, etc.) but must keep:

- One dedicated area for lint feedback.\n- One area for test results.\n- One area for “code canvas” state (files, last tests, line counts, dirty flags, pytest targets).\n

### 7.4 Patch review queue

The bottom row shows the **pending patch queue**:

- `pending_view` shows textual summaries or unified diffs.\n- Buttons: `Accept`, `Accept all`, `Reject` call into methods that in turn use tools to apply or discard patches.\n

You may restyle this region (e.g., cards, tables, collapsible sections) but the core behavior — **explicit human approval for patches** — must remain.\n

---

## 8. Theme and styling boundaries

All theme-level styling is centralized in:

- `agent/gui/gui_theme.py` — palettes, accent colors, fonts, mode-specific CSS snippets.\n- `agent/gui/gui_richtext.py` — rich-text widgets like `SmartScrollTextEdit`, helper `apply_panel_style`.\n- `agent/gui/gui_formatting.py` — functions to format messages and ledgers as HTML (assistant/user bubbles, system messages, attachment notices, sleep cycle messages).\n

When redesigning the UI visually, it is safe to:

- Replace fonts, colors, paddings, and borders.\n- Change icons and emoji.\n- Reorganize panel layout and splitter/tab structure.\n

It is **not** safe to:\n
\n- Bypass `AgentWorker` and call the agent core on the UI thread.\n- Remove or rename `BaseModePage` methods used by the main window (without updating all callers accordingly).\n- Change the semantics of signals or the contract of `AgentWorker`.\n

---

## 9. Copy/paste prompt for Google Gemini (visual redesign only)

Use this prompt as-is (you can adjust for a different Gemini model or temperature). Paste it into Gemini along with this `GUI_ARCHITECTURE.md` file and any screenshots you want to share.

```text
You are a senior product designer and PySide6/Qt UI engineer.
Your task is to propose a **visual and UX redesign only** for the Aquila OS desktop app,
keeping all behaviors, data flows, and hooks exactly as described in the attached
`GUI_ARCHITECTURE.md` document.

Constraints (do NOT break these):
- The core agent logic, tool loop, and memory live in `main.py` and related modules.
- The GUI talks to the agent **only** via `AgentWorker(QThread)` and its signals
  (`ledger_signal`, `finished_signal`, `ask_user_signal`).
- Mode pages under `agent/gui/gui_pages/` must continue to implement the `BaseModePage`
  interface (`append_chat_html`, `clear_chat_display`, `begin_assistant_stream`,
  `stream_chat_token`, `finalize_streamed_message`, `get_chat_input_text`,
  `clear_chat_input`, `set_run_buttons_running`, `update_ledger`, `refresh_state`,
  `get_extra_run_context`, `get_extra_text_chunks`, etc.).
- The attachments pipeline (file dialog → `process_local_attachments` →
  `attached_chunks` / `attached_images` → optional `format_attachment_context`) must
  continue to work, even if the visual layout changes.
- Ledger and state rendering must still use `gui_state.py` helpers
  (`resolve_ledger_path`, `render_step_ledger_html`, `render_writing_draft_html`,
  `render_code_canvas_html`). You may change how and where these are displayed,
  but not how they are computed.
- Code Mode (`CodeIdePage`) must preserve its integrations with
  `tool_library.code_canvas_tools` (open/import/new/sync project, apply_user_buffer_edit,
  patch review queue, lint/tests/state panes).

Goals:
1. Make the app feel like a modern IDE/workbench for local AI agents, with a clean,
   minimal aesthetic that works in both light and dark modes.
2. Improve information hierarchy and reduce clutter in the Task, Research, Writing,
   and Code workspaces (clear primary vs secondary panels, better use of whitespace).
3. Make attachments, journal notes, and ledgers more discoverable and readable.
4. For Code Mode, emphasize TDD workflow: where to run tests, see failures, and view
   pending patches.
5. Keep the app comprehensible to new users: include labels, hints, and empty-state
   messages where helpful.

Deliverables (in text form, no code yet):
1. A high-level **layout proposal** for each workspace (Chat, Task, Research, Writing,
   Code, Character, Learn, Home). For each, describe:
   - Major regions (left/right/top/bottom/center) and their responsibilities.
   - How panels are grouped (tabs vs splitters vs collapsible sections).
   - How the user flows through a typical task in that workspace.
2. A **component and widget map** listing the key visual elements you recommend
   (e.g., sidebars, tab bars, status bars, prompts, cards), and how they should
   relate to existing classes (e.g., replacing AgentRail’s look, but keeping its role).
3. A **visual style guide**:
   - Color palette (with hex values), including background, surface, accent, success,
     warning, and error colors that work in dark and light themes.
   - Typography (font families, sizes, weights) and spacing scale (8px/4px increments).
   - Iconography guidance (where icons help vs where text labels are better).
4. A **migration plan** in 4–6 steps for a developer to implement your design
   incrementally, minimizing disruption:
   - Which files to touch first (e.g., gui_theme.py, gui_richtext.py).
   - How to refactor layouts one workspace at a time while keeping tests passing.
   - How to validate that all mode pages still satisfy the BaseModePage contract.

When you reference specific classes or files, use the names from the attached
GUI_ARCHITECTURE.md and try to keep changes localized to the GUI layer.
Do NOT propose changes to the agent core, tool loop, or memory system.
```

---

## 10. For implementers: how to use Gemini’s output

Once Gemini proposes a design:

- Apply styling and layout changes **only** in:\n  - `gui_theme.py`\n  - `gui_richtext.py`\n  - `gui_formatting.py`\n  - The `gui_pages/*` modules and `gui.py` where layout is constructed\n- After each incremental change, run:\n  - `pytest agent/tests/test_gui*.py -v`\n  - `pytest agent/tests/test_gui_state_tracker.py agent/tests/test_code_ide_page.py -v` (if present)\n  - Full health check: `./scripts/aquila-health-check.sh smoke` or `full`\n\nThis ensures the new UI remains **functionally equivalent** while gaining a better look and workflow.\n
