# Aquila OS Desktop App - UI/UX Redesign Proposal

## 1. High-Level Layout Proposal

To achieve a modern IDE aesthetic, the app window will be standardized into a universal structural frame: a thin left-hand navigation rail (for mode switching), a central workspace area (controlled by the `QStackedWidget`), and contextual sidebars or bottom panels depending on the mode.

### Home Page
* **Center Hero:** A clean, centralized welcome screen to select the active Aquila instance.
* **Grid Layout:** A visually appealing grid of "Workspace Cards" mapping to `gui_modes.py` to launch specific modes.

### Chat & Character Pages
* **Center Column:** A wide, readable conversation history area.
* **Bottom Anchor:** The `AgentRail` transformed into a floating "Command Bar" for prompt input and attachment previews.
* **Right Collapsible Sidebar:** A dedicated pane for viewing `format_attachment_context` payloads or Persona lore (for Character Mode) without cluttering the chat.

### Task & Research Pages
* **Left Sidebar:** A slimmed-down `AgentRail` acting as a persistent prompt/control column.
* **Center Workspace:** The primary focus area displaying `render_step_ledger_html` (Task) or Journal/References (Research).
* **Right Sidebar:** The `ExecutionLogPanel` formatted like a clean terminal output, capturing `ledger_signal` streams.

### Writing Page
* **Left Sidebar:** Document outline or structural notes.
* **Center Workspace:** A distraction-free canvas rendering `render_writing_draft_html`.
* **Right Sidebar / Bottom Dock:** The `AgentRail` and chat history, allowing side-by-side prompting while viewing the draft.

### Code Mode (`CodeIdePage`)
* **Left Sidebar:** The codebase file tree.
* **Center Top:** The main editor tabs (backed by `self._tab_paths` and buffer saves).
* **Center Bottom (Horizontal Split):** A tabbed panel containing the TDD lifeblood: **Tests**, **Problems** (Lint), and **Pending Patches**. The patch review queue must feature prominent "Accept/Reject" buttons.
* **Right Sidebar:** Chat, log, and `render_code_canvas_html` state. 

### Learn Page
* **Left Sidebar:** The Syllabus tree structure.
* **Center Column:** The active Tutor chat interface.
* **Right Sidebar:** Archive material viewer.

---

## 2. Component & Widget Map

| Existing Class / Concept | Proposed UI Component | Visual Behavior |
| :--- | :--- | :--- |
| `AgentRail` | **Contextual Command Bar** | Moves from a static left-column box to a dockable or bottom-anchored expanding text input with quick-action pill buttons for attachments. |
| `ExecutionLogPanel` | **Activity Terminal** | Styled with a monospace font and subtle background dimming to differentiate "agent thinking" from "final output." |
| `SmartScrollTextEdit` | **Markdown Canvas** | Removes heavy borders; relies on typography and whitespace. Uses syntax highlighting for code blocks. |
| Attachment Dialog | **Asset Drawer** | Visually groups `attached_chunks` into clickable chips above the text input before sending to the worker. |
| Patch Review Queue | **Diff Cards** | Presents diffs in distinct cards with clear green (Accept) and red (Reject) action buttons. |

---

## 3. Visual Style Guide

### Color Palette

| Role | Light Theme (Hex) | Dark Theme (Hex) |
| :--- | :--- | :--- |
| **App Background** | `#F8F9FA` | `#1E1E1E` |
| **Surface/Panels** | `#FFFFFF` | `#252526` |
| **Primary Accent** | `#0066FF` | `#3794FF` |
| **Text Primary** | `#1A1A1A` | `#CCCCCC` |
| **Success (Tests/Accept)** | `#28A745` | `#4CAF50` |
| **Warning/Error (Lint)** | `#DC3545` | `#F44336` |
| **Borders/Dividers** | `#E5E5E5` | `#333333` |

### Typography & Spacing
* **UI Font:** Inter or Roboto (Clean, highly legible sans-serif).
* **Code/Log Font:** JetBrains Mono or Fira Code.
* **Scale:** Base size 14px. Small text (hints/logs) 12px. Headers 18px-24px.
* **Spacing System:** Strict 8px grid. Margins are 16px or 24px; internal padding is 8px.

### Iconography
* Use outline-style icons (e.g., Phosphor Icons or Feather Icons).
* Use icons for actions (Run, Stop, Attach, Settings).
* Use text labels alongside icons for destructive actions (Reject Patch) or primary actions (Accept Patch) to prevent errors.

---

## 4. Migration Plan

1.  **Foundation (Theme & Typography):** Update `agent/gui/gui_theme.py` with the new color palettes and 8px spacing metrics. Modify `agent/gui/gui_richtext.py` to apply the new fonts and remove legacy borders. Run tests to ensure basic rendering survives.
2.  **Component Facelift (`AgentRail` & Logs):** Refactor the visual layout of `AgentRail` and `ExecutionLogPanel` in isolation. Ensure `get_chat_input_text()` and `set_run_buttons_running()` still target the correct internal `QLineEdit` or `QPushButton` objects.
3.  **Basic Workspace Rollout (Home & Chat):** Apply the new layouts to `HomePage` and `ChatPage`. Verify the `QStackedWidget` transitions smoothly and `AgentWorker` signals (`ledger_signal`, `finished_signal`) still populate the chat views.
4.  **Complex Workspace Rollout (Task, Research, Writing):** Reorganize the splitter panels. Ensure `refresh_state()` accurately pulls data from `resolve_ledger_path` and pipes it into the updated HTML generators in `gui_state.py`.
5.  **Code Mode Revamp (`CodeIdePage`):** Rebuild the layout strictly adhering to the new IDE blueprint. Verify the TDD flow by testing the `_save_buffer` timers, tool loop integration, and ensuring the pending patch queue correctly routes "Accept/Reject" clicks to the backend tools.
