# GUI framework evaluation for Aquila-cpp (decision D3)

Question: keep the PySide6 GUI on top of the C++ core, or move to a framework that is a better fit **and keeps all current GUI functionality**?

Method: (1) inventory what the current GUI actually uses, from code at `Aquila-3.5@759212a`; (2) add the two GUI features the user has asked for (D8 builder, D10 canvas); (3) score each candidate against every row. "Keeps all functionality" means no row is a gap. Framework facts come from the sources at the bottom (checked 2026-11-02).

## 1. What the current GUI uses [measured]

Commands (from the Python checkout):

```bash
rg -o --no-filename 'from PySide6\.(\w+)' agent scripts --glob '*.py' --glob '!agent/tests/**' -r '$1' | sort | uniq -c
rg -o --no-filename '\bQ[A-Z][A-Za-z]+\b' agent/gui --glob '*.py' | sort | uniq -c | sort -rn
rg -n 'qfluentwidgets' agent --glob '*.py' --glob '!agent/tests/**'
```

- Qt modules: QtWidgets (25 imports), QtCore (15), QtGui (7), QtWebEngineCore (1, the browser *tool*, not the GUI).
- Third-party GUI deps: `qfluentwidgets` in **2 places only**: `MSFluentWindow`/`NavigationItemPosition`/`FluentIcon`/`setTheme` (`agent/gui/gui.py:33-39`) and `FlowLayout` (`agent/gui/gui_widgets/wrapping_layout.py:5`). `markdown` (Python lib, extensions `fenced_code`, `tables`, `nl2br`, `agent/gui/gui_formatting.py:13`).
- Versions in `ai-agent-env`: PySide6 6.11.0, qfluentwidgets 1.11.2.

| # | Capability | Evidence |
|---|---|---|
| G1 | Shell: Fluent nav window, light/dark theme, mode stack (9 workspaces + Home/Settings) | `gui.py:33-39`, `QStackedWidget`×9 |
| G2 | Streaming chat transcript as rich HTML (markdown → HTML, smart scroll, stream finalize) | `QTextEdit`×35, `gui_formatting.py`, `gui_richtext.py` |
| G3 | Editable code and writing buffers (tabs, file tree → tab) | `QPlainTextEdit`×25, `QTabWidget`×19, `QTreeWidget` |
| G4 | **Selection → agent edit** (highlight text, send it to an agent sub-call) | `code_ide_page.py:263`, `writing_page.py:521` `cursor.selectedText()` → `ChatSubcallWorker` (`gui.py:429`) |
| G5 | Pending-patch diff cards, accept/reject | `code_ide_page.py:426-464` |
| G6 | Markdown preview (writing canvas) | `writing_page.py:481` |
| G7 | Lists/trees/tabs/splitters/toolbox/scroll areas | `QListWidget`×21, `QSplitter`×24, `QToolBox`×15, `QScrollArea`×13 |
| G8 | Dialogs: file, message, input, setup wizard | `QMessageBox`×109, `QFileDialog`×14, `QInputDialog`×9, `QWizard`×5 |
| G9 | Settings forms (spin/check/radio/combo/group/form layouts) | `QSpinBox`, `QCheckBox`×23, `QRadioButton`×10, `QFormLayout` |
| G10 | Background workers + signals (agent runs, streaming tokens, ask-user bridge) | `QThread`×15, 37 QThread/Signal refs |
| G11 | QSS theming (existing stylesheet strings) | `agent/gui/gui_theme.py` (30 widget selectors) |
| G12 | Headless web page rendering for the browser tool | `agent/tool_library/browser_tools.py:9` `QWebEnginePage` |

Requested additions:

| # | Capability | Source |
|---|---|---|
| F1 | **Gemini-style live canvas** (code *and* writing): agent edits the open document live from a highlight or prompt; inline change highlighting; accept/reject; undo | D10 |
| F2 | **GUI recipe builder**: visual editor for recipe cartridges (modules, exposed actions, hooks, checklist) | D8; prior plan in Python `docs/workflow-editor-vision.md` (block-style editor) |
| F3 | Works on the CPU-first 8 GB tier: low GUI RAM next to a ~4.5-5.2 GB model budget | design doc R16, D:L740 |

## 2. Candidates

| | A. Keep PySide6 GUI, C++ core via bindings/IPC | **B. Qt 6 Widgets (C++)** | C. Qt Quick/QML (C++) | D. Web UI (HTML/JS in WebView2/QtWebEngine) + local API | E. Slint (C++) | F. Dear ImGui | G. wxWidgets |
|---|---|---|---|---|---|---|---|
| G1 shell/theme | ✓ (qfluentwidgets) | ✓ `windows11` style built in since Qt 6.7 (dark mode) [S3] + custom nav rail | ✓ FluentWinUI3 style since 6.8 [S2], but SplitView/StackView/TreeViewDelegate fall back to Fusion | ✓ | ✓ Fluent is default style [S4] | ✗ not a document-app look | ~ native but dated |
| G2 rich HTML transcript | ✓ | ✓ same `QTextEdit` | ~ `TextEdit` rich-text subset | ✓ best | ~ `StyledText` markdown is "a first step" (1.16) [S4] | ✗ | ~ wxHtmlWindow subset |
| G3/G7/G8/G9 standard widgets | ✓ | ✓ same classes (PySide6 *is* Qt) | ~ rewrite; trees/splitters weaker | ✓ rewrite | ~ rewrite; no tree/rich editors | ✗ | ✓ different API |
| G4/F1 live canvas | ~ (Python side) | ✓ `QPlainTextEdit` + `QSyntaxHighlighter` + extra selections natively; optional Monaco in `QWebEngineView` (decorations track edits, built-in diff editor) [S6][S7] | ~ | ✓ Monaco native | ✗ no code editor | ~ ImGuiColorTextEdit | ✓ wxStyledTextCtrl |
| G5 diff/patch | ✓ | ✓ | ~ | ✓ | ✗ | ✗ | ~ |
| G6 markdown | ✓ (Python lib) | ✓ `QTextDocument::setMarkdown` (GitHub dialect: tables, fenced code) [S5]. Gap: no `nl2br` → preprocess single newlines | ✓ same engine | ✓ | ~ | ✗ | ✗ |
| G10 workers/signals | ✓ | ✓ native; core events → queued signals | ✓ | ~ via IPC | ✓ | ✓ | ✓ |
| G11 reuse QSS | ✓ | ✓ **reuse `gui_theme.py` strings as-is** | ✗ | ✗ | ✗ | ✗ | ✗ |
| G12 browser tool | ✓ | ✓ QtWebEngine in the same app | ✓ | ✓ | ✗ | ✗ | ~ wxWebView |
| F2 recipe builder | ~ | ✓ **QtNodes** (BSD-3, Qt6 Widgets, JSON save, undo/redo, embedded widgets) [S8] | ~ third-party | ✓ JS node libs | ✗ | ~ imnodes | ✗ |
| F3 low RAM | ✗ Python runtime + Qt | ✓ native. Monaco adds a Chromium process (≈ +100-200 MB RSS) [S7], so keep it optional | ✓ | ✗ Chromium for the whole UI | ✓ | ✓ | ✓ |
| Core integration | bindings (nanobind/pybind11) or IPC; two languages forever | **in-process, direct C++ calls** | in-process | IPC (HTTP/WS) | in-process | in-process | in-process |
| Licensing | ⚠ qfluentwidgets: GPLv3 for non-commercial only, commercial needs a paid license [S1] | Qt LGPLv3; QtNodes BSD-3; **qfluentwidgets dropped** (its C++ edition is closed-source and paid even for non-commercial use [S1]) | Qt LGPLv3 | MIT libs + Chromium | Royalty-free w/ attribution, GPLv3, or commercial [S4] | MIT | wxWindows licence |
| Port effort for 9,052 GUI LOC | none | **mechanical** (same class names, signals/slots, QSS) | rewrite in QML | full rewrite in JS | full rewrite | full rewrite | full rewrite |

✓ = covered, ~ = partial / extra work, ✗ = gap.

Only **A** and **B** cover every current row (G1-G12). **B** also covers F1-F3 without a gap and removes Python (D6: remake everything).

## 3. Decision: Qt 6 Widgets in C++ (D3, chosen by the user 2026-11-02)

**B: Qt 6 Widgets in C++**, in-process with the C++ core.

- Same toolkit as today (PySide6 6.11 = Qt 6.11), so each page ports class-for-class, and `gui_theme.py` QSS carries over unchanged.
- Replace `qfluentwidgets` (2 call sites) with the built-in `windows11` style plus a small custom navigation rail and a ~100-line `FlowLayout` (a standard Qt example pattern). This also removes the GPL/commercial licensing question.
- **Canvas (F1):** build it native first: `QPlainTextEdit`/`QTextEdit` plus `QSyntaxHighlighter`, live change marks via extra selections, a pending-patch overlay, and undo. Keep Monaco-in-`QWebEngineView` as a measured upgrade path only if the native editor falls short (it costs a Chromium process, F3).
- **Recipe builder (F2):** QtNodes.
- The browser tool keeps working on QtWebEngine in the same process.
- The phone PWA (`webapp/`, 2,566 LOC) stays the remote surface, served by the C++ remote server (D6). It is not the desktop UI.

**Why not A:** it covers today's rows, but keeps a Python runtime and the bindings layer forever, keeps the qfluentwidgets license issue, and runs against D6.
**Why not D:** strongest canvas, but a full JS rewrite, IPC for every interaction, and a Chromium-sized UI on the 8 GB CPU tier.

## 4. Prerequisites and risks

- **No Qt C++ SDK on this machine.** Only the PySide6 wheel's runtime is present; `qmake`/`qt-cmake` not found [measured]. M0 needs a Qt 6.11 MSVC 2022 x64 install (Qt online installer or `aqtinstall`) with the WebEngine module.
- **License:** the repo has no LICENSE file [measured]. Qt under LGPLv3 needs dynamic linking (the default) plus notice/relink obligations when distributing.
- **Windows 11 style:** early Qt 6.7 builds had palette bugs [S3 forum threads]. Re-check on 6.11; `fusion` + QSS is the fallback.
- **Thread model:** R2 makes the core single-threaded, so the GUI thread must not block on inference. The core runs in one worker thread and posts events to the GUI via queued signals. That is the one "edge" thread R2 allows (RECON_MAP section 2.2).

## Sources (checked 2026-11-02)

- [S1] QFluentWidgets licensing: https://qfluentwidgets.com/pages/about/ , https://qfluentwidgets.com/pages/faq/
- [S2] Qt Quick FluentWinUI3 style: https://doc.qt.io/qt-6.8/qtquickcontrols-fluentwinui3.html
- [S3] Qt 6.7 Windows 11 widget style: https://doc.qt.io/qt-6/whatsnew67.html ; bug reports: https://forum.qt.io/topic/157708
- [S4] Slint 1.16 (StyledText/markdown, Fluent default) and license: https://slint.dev/blog/slint-1.16-released , https://github.com/slint-ui/slint/blob/master/LICENSE.md
- [S5] `QTextDocument::setMarkdown` GitHub dialect: https://doc.qt.io/qt-6/qtextdocument.html
- [S6] Monaco decorations track edits: https://github.com/microsoft/monaco-editor/issues/442 ; Monaco in QWebEngineView: https://blog.suryatejak.in/gitraven-how-to-setup-monaco-editor-for-qwebengine
- [S7] Scintilla vs Monaco-in-WebEngine footprint comparison: https://github.com/borco/pyside6-scintilla/blob/master/docs/alternatives.md
- [S8] QtNodes (BSD-3, Qt6): https://github.com/paceholder/nodeeditor , https://qtnodes.readthedocs.io/en/master/
- QScintilla is GPLv3 or commercial (not recommended for that reason): https://riverbankcomputing.com/software/qscintilla
