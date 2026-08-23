# Aquila OS Desktop App - Structural UI Wireframes

This document contains the structural text-based wireframes mapping out the component arrangements for the PySide6 UI redesign.

---

### 1. Home Page Layout
The Home page serves as the entry point. It removes sidebars entirely to focus on instance selection and mode launching via a centralized grid, acting as the primary controller for the `QStackedWidget`.

```text
+-------------------------------------------------------------------------+
|                                                                         |
|                                                                         |
|                              [ Aquila OS ]                              |
|                      Select Active Instance: [Default ▼]                |
|                                                                         |
|                                                                         |
|       +-------------------+  +-------------------+  +-------------------+
|       |    Chat Mode      |  |    Task Mode      |  |  Research Mode    |
|       |  (Conversational) |  |  (Step-by-step)   |  | (Gather & Plan)   |
|       +-------------------+  +-------------------+  +-------------------+
|                                                                         |
|       +-------------------+  +-------------------+  +-------------------+
|       |   Writing Mode    |  |    Code Mode      |  |  Character Mode   |
|       |  (Draft focused)  |  |   (IDE & TDD)     |  |   (Roleplay)      |
|       +-------------------+  +-------------------+  +-------------------+
|                                                                         |
|       +-------------------+  +-------------------+                      |
|       |   Learn Mode      |  |    Settings       |                      |
|       | (Classroom/Arch.) |  | (Ollama, MCP, …)  |                      |
|       +-------------------+  +-------------------+                      |
|                                                                         |
|  (Data Processing — batch ingest — hidden unless AQUILA_ENABLE_DATA_   |
|   PROCESSING=1; see docs/data-processing-mode.md)                       |
|                                                                         |
+-------------------------------------------------------------------------+
```

---

### 2. Chat, Character, & Learn Pages
These modes prioritize reading and conversational back-and-forth. The `AgentRail` is transformed from a bulky side-panel into a sleek, bottom-anchored command bar. A collapsible right panel holds contextual metadata (like attachments or Character Lore).

```text
+---+---------------------------------------------------+-----------------+
|   |                                                   |                 |
| N |  Assistant: Hello! I'm ready to help.             |  Context Pane   |
| a |                                                   |  (Collapsible)  |
| v |                                                   |                 |
|   |  User: Let's review the new architecture.         |  - Lore         |
| R |                                                   |  - Course Data  |
| a |  Assistant: Okay, I have loaded the docs...       |  - Attachments  |
| i |                                                   |                 |
| l |                                                   |                 |
|   +---------------------------------------------------+                 |
|   | [📎 Attach]  Type your message here...      [Run] |                 |
+---+---------------------------------------------------+-----------------+
```

---

### 3. Task & Research Pages
These modes are heavily structured. The UI uses a `QSplitter` to divide the screen into a central canvas (showing the `render_step_ledger_html` state) and a right-hand sidebar for the streaming execution logs. 

```text
+---+-----------------------------------------+---------------------------+
|   | Workspace State (Center Canvas)         | Execution Log (Terminal)  |
| N |                                         |                           |
| a |  Current Plan:                          | > Starting task...        |
| v |  [✓] 1. Analyze user request            | > Tool: search_web        |
|   |  [ ] 2. Gather data                     | > Parsing results...      |
| R |  [ ] 3. Synthesize findings             | > Writing to ledger...    |
| a |                                         |                           |
| i |                                         |                           |
| l +-----------------------------------------+---------------------------+
|   | [📎 Attach]  Update plan or prompt...                         [Run] |
+---+---------------------------------------------------------------------+
```

---

### 4. Writing Page
Writing mode focuses entirely on a distraction-free document. The chat/prompt interface is relegated to a sidebar so the user can instruct the agent without covering up the text editor rendering `render_writing_draft_html`.

```text
+---+-----------------------------------------------+---------------------+
|   |                                               |                     |
| N |  ## Draft Title                               |  Chat & Commands    |
| a |                                               |                     |
| v |  This is the main body of the generated       |  User: Make the     |
|   |  text. It takes up the majority of the        |  intro punchier.    |
| R |  screen space. There are no heavy borders.    |                     |
| a |                                               |                     |
| i |  Whitespace is prioritized to make            |                     |
| l |  reading comfortable.                         +---------------------+
|   |                                               | Prompt...     [Run] |
+---+-----------------------------------------------+---------------------+
```

---

### 5. Code Mode (IDE Layout)
This is the most complex layout, mimicking a standard IDE. It utilizes a 3-way `QSplitter` to balance the file tree, the active code editors, and the critical testing/patching tools from `tool_library.code_canvas_tools`.

```text
+---+---------------+-----------------------------------------------------+
|   |               | main.py (Tab) | tests.py (Tab) |                    |
| N |  File Tree    +-----------------------------------------------------+
| a |               | def main():                                         |
| v |  > src/       |     print("Hello from Aquila OS")                   |
|   |    main.py    |     return True                                     |
| R |    utils.py   |                                                     |
| a |               |                                                     |
| i |  > tests/     +-----------------------------------------------------+
| l |    test_main  | [Tests] [Lint Problems] [Pending Patches]           |
|   |               |                                                     |
|   |               | Patch #1: Add error handling    [ACCEPT] [REJECT]   |
+---+---------------+-----------------------------------------------------+
```
