"""GUI helpers for ledger path resolution and state rendering."""
from pathlib import Path


def resolve_ledger_path(mode: str, task_name: str) -> Path | None:
    """Return the filesystem path for the active ledger given mode and task name."""
    mode = (mode or "").lower()
    if mode == "writing":
        draft = Path("Agent-Drafts/active_draft_state.json")
        return draft if draft.exists() else Path(f"Agent-Tasks/{task_name}.json")
    if mode == "code":
        code_buf = Path("Agent-Code/active_code_state.json")
        return code_buf if code_buf.exists() else Path(f"Agent-Tasks/{task_name}.json")
    if mode == "research":
        return Path(f"Agent-Plans/{task_name}.json")
    if mode in ("autonomous", "task", ""):
        return Path(f"Agent-Tasks/{task_name}.json")
    return Path(f"Agent-Tasks/{task_name}.json")


def render_step_ledger_html(state: dict) -> str:
    """Render step checklist HTML for autonomous/research task ledgers."""
    steps = state.get("steps", [])
    current_idx = state.get("current_step_index", 0)
    status = state.get("status", "in_progress")

    html = (
        f"<h2 style='color: #3498db; border-bottom: 1px solid #555; padding-bottom: 5px;'>"
        f"Task Progress ({status.upper()})</h2>"
    )
    html += "<ul style='list-style-type: none; padding-left: 0;'>"

    for i, step in enumerate(steps):
        desc = step.get("description", f"Step {i + 1}")
        step_status = step.get("status", "pending")
        if step_status == "completed" or i < current_idx:
            icon = "&#10003;"
            color = "#27ae60"
            style = "text-decoration: line-through; opacity: 0.7;"
        elif i == current_idx and status != "completed":
            icon = "&#9654;"
            color = "#f39c12"
            style = "font-weight: bold;"
        else:
            icon = "&#9711;"
            color = "#95a5a6"
            style = ""

        max_iter = step.get("max_iterations", "?")
        html += (
            f"<li style='margin-bottom: 10px; padding: 8px; border-left: 4px solid {color};'>"
            f"<span style='color: {color};'>{icon}</span> "
            f"<span style='{style}'>{desc}</span>"
            f"<br><i style='color: #7f8c8d; font-size: 0.85em;'>max_iterations: {max_iter}</i>"
            f"</li>"
        )

    html += "</ul>"
    return html


def render_writing_draft_html(state_data: dict) -> str:
    """Render writing-mode draft state for the Task State Tracker tab."""
    title = state_data.get("title", "Draft")
    synopsis = state_data.get("synopsis", "")

    html_state = (
        f"<h2 style='color: #9b59b6; border-bottom: 1px solid #555; padding-bottom: 5px;'>"
        f"Active Document: {title}</h2>"
    )
    if synopsis:
        html_state += f"<p style='font-style: italic; color: #7f8c8d;'>{synopsis}</p>"

    html_state += "<ul style='list-style-type: none; padding-left: 0;'>"
    for i, sec in enumerate(state_data.get("sections", [])):
        word_count = len(sec.get("content", "").split())
        html_state += (
            f"<li style='margin-bottom: 12px; padding: 10px; "
            f"background-color: rgba(155, 89, 182, 0.05); border-left: 4px solid #9b59b6;'>"
            f"<b style='color: #9b59b6;'>Section {i + 1}:</b> {sec.get('header', '')}"
            f"<br><i style='color: #bdc3c7; font-size: 0.9em;'>"
            f"Content: {word_count} words written</i></li>"
        )
    html_state += "</ul>"
    return html_state


def render_code_canvas_html(state_data: dict, task_ledger: dict | None = None) -> str:
    """Render code buffer metadata for the Task State Tracker."""
    project = state_data.get("project_name", "Code Project")
    primary = state_data.get("language_primary", "?")
    html = (
        f"<h2 style='color: #2ecc71; border-bottom: 1px solid #555; padding-bottom: 5px;'>"
        f"Code Canvas: {project}</h2>"
        f"<p style='color: #7f8c8d;'>Primary language: {primary}</p>"
    )
    if task_ledger:
        idx = task_ledger.get("current_step_index", 0)
        steps = task_ledger.get("steps", [])
        if idx < len(steps):
            sk = steps[idx].get("step_kind", "code")
            html += f"<p><b>Current step kind:</b> {sk}</p>"

    html += "<ul style='list-style-type: none; padding-left: 0;'>"
    for f in state_data.get("files", []):
        path = f.get("path", "?")
        lint = f.get("lint_status", "?")
        test = f.get("last_test", "?")
        dirty = " *" if f.get("dirty") else ""
        icon = "#e74c3c" if lint == "error" else "#f39c12" if lint == "warn" else "#2ecc71"
        html += (
            f"<li style='margin-bottom: 8px; padding: 8px; border-left: 4px solid {icon};'>"
            f"<code>{path}</code>{dirty}<br>"
            f"<i style='font-size: 0.85em; color: #bdc3c7;'>"
            f"{f.get('line_count', 0)} lines | lint={lint} | test={test}</i></li>"
        )
    html += "</ul>"
    targets = state_data.get("test_targets", [])
    if targets:
        html += f"<p><b>pytest targets:</b> {', '.join(targets)}</p>"
    return html
