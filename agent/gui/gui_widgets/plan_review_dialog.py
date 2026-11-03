"""Plan review dialog — workshop before task execution."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from agent.core.task_artifacts import (
    implementation_plan_md_path,
    plan_md_path,
    read_plan_dict,
    render_plan_markdown,
)
from agent.gui.gui_dialogs import apply_dialog_theme
from agent.gui.markdown_utils import escape_markdown_for_qt


class PlanReviewDialog(QDialog):
    approved = Signal()
    revise_requested = Signal(str)

    def __init__(
        self,
        parent,
        *,
        task_name: str,
        mode: str,
        user_request: str = "",
    ):
        super().__init__(parent)
        self.task_name = task_name
        self.mode = mode
        self.user_request = user_request
        self.setWindowTitle(f"Review plan — {task_name}")
        self.setMinimumSize(640, 480)
        apply_dialog_theme(self, parent=parent)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Review the living implementation plan (design) and OS ledger steps. "
                "Approve to start execution, or send feedback to revise."
            )
        )

        tabs = QTabWidget()
        plan = read_plan_dict(task_name, mode)

        impl_path = implementation_plan_md_path(task_name, mode)
        if impl_path.exists():
            impl_view = QTextEdit()
            impl_view.setReadOnly(True)
            impl_view.setMarkdown(
                escape_markdown_for_qt(impl_path.read_text(encoding="utf-8"))
            )
            tabs.addTab(impl_view, "Implementation")

        plan_view = QTextEdit()
        plan_view.setReadOnly(True)
        md_file = plan_md_path(task_name, mode)
        if md_file.exists():
            plan_view.setMarkdown(
                escape_markdown_for_qt(md_file.read_text(encoding="utf-8"))
            )
        else:
            plan_view.setMarkdown(
                escape_markdown_for_qt(render_plan_markdown(plan))
            )
        tabs.addTab(plan_view, "OS Plan" if impl_path.exists() else "Plan")

        self.feedback_edit = QPlainTextEdit()
        self.feedback_edit.setPlaceholderText(
            "Optional: describe changes (scope, checklist, risks) before revising..."
        )
        tabs.addTab(self.feedback_edit, "Feedback")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox()
        approve_btn = buttons.addButton("Approve && Run", QDialogButtonBox.AcceptRole)
        revise_btn = buttons.addButton("Revise plan", QDialogButtonBox.ActionRole)
        cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        approve_btn.clicked.connect(self._on_approve)
        revise_btn.clicked.connect(self._on_revise)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _on_approve(self):
        self.approved.emit()
        self.accept()

    def _on_revise(self):
        text = self.feedback_edit.toPlainText().strip()
        if not text:
            text = "Please simplify and clarify the plan steps."
        self.revise_requested.emit(text)
        self.accept()
