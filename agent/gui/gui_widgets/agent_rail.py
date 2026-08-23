"""Reusable agent chat rail: history, input, run controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
    QLabel,
    QToolButton,
    QTextEdit,
    QApplication,
)

from ..gui_richtext import (
    SmartScrollTextEdit,
    apply_panel_style,
    apply_thinking_panel_style,
    finalize_streamed_message,
    insert_assistant_stream_shell,
)


def _format_thinking_count(n: int) -> str:
    if n < 1000:
        return str(n)
    return f"{n / 1000:.1f}k"


class AgentRail(QWidget):
    """Left or right column: chat history + input + standard task buttons."""

    def __init__(
        self,
        main_window,
        *,
        placeholder: str = "Assign a task or say hello...",
        show_resume: bool = True,
        show_clear: bool = True,
        compact_buttons: bool = False,
        layout_variant: str = "left",
        show_history: bool = True,
    ):
        super().__init__()
        self.main = main_window
        self._layout_variant = layout_variant
        self._show_history = show_history
        self._answer_started = False
        self._thinking_from_content = False
        self._last_assistant_raw_text = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._thinking_container = QWidget()
        thinking_layout = QVBoxLayout(self._thinking_container)
        thinking_layout.setContentsMargins(0, 0, 0, 4)
        thinking_layout.setSpacing(2)

        self.thinking_toggle = QToolButton()
        self.thinking_toggle.setText("▸ Thinking")
        self.thinking_toggle.setCheckable(True)
        self.thinking_toggle.setChecked(False)
        self.thinking_toggle.setVisible(False)
        self.thinking_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.thinking_toggle.toggled.connect(self._on_thinking_toggled)
        thinking_layout.addWidget(self.thinking_toggle)

        self.thinking_view = QTextEdit()
        self.thinking_view.setReadOnly(True)
        self.thinking_view.setMaximumHeight(120)
        self.thinking_view.setVisible(False)
        apply_thinking_panel_style(self.thinking_view, dark=main_window.dark_mode)
        thinking_layout.addWidget(self.thinking_view)

        self.chat_history = SmartScrollTextEdit()
        apply_panel_style(self.chat_history, "chat", dark=main_window.dark_mode)
        try:
            # Handle custom "copy://" links embedded in code blocks.
            self.chat_history.setOpenExternalLinks(False)
            self.chat_history.anchorClicked.connect(self._on_anchor_clicked)
        except Exception:
            pass
        if show_history:
            layout.addWidget(self._thinking_container, stretch=0)
            layout.addWidget(self.chat_history, stretch=1)

        self.command_bar = QWidget()
        cmd_layout = QVBoxLayout(self.command_bar)
        cmd_layout.setContentsMargins(0, 12, 0, 0)

        self.attachments_preview = QLabel("")
        self.attachments_preview.setWordWrap(True)
        self.attachments_preview.setStyleSheet("font-size: 9pt; color: #7f8c8d; padding-bottom: 4px;")
        cmd_layout.addWidget(self.attachments_preview)

        # Primary Input and Actions
        primary_layout = QHBoxLayout()
        primary_layout.setSpacing(8)
        
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText(placeholder)
        self.chat_input.returnPressed.connect(main_window.execute_task)
        primary_layout.addWidget(self.chat_input, stretch=1)

        attach_label = "📎" if compact_buttons else "📎 Attach"
        self.attach_button = QPushButton(attach_label)
        self.attach_button.clicked.connect(main_window.open_attachment_dialog)
        primary_layout.addWidget(self.attach_button)

        self.run_btn = QPushButton("▶️" if compact_buttons else "▶️ Run")
        self.run_btn.clicked.connect(main_window.execute_task)
        self.run_btn.setProperty("primary", True)
        primary_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("🛑" if compact_buttons else "🛑 Stop")
        self.stop_btn.clicked.connect(main_window.stop_task)
        self.stop_btn.setDisabled(True)
        primary_layout.addWidget(self.stop_btn)
        
        cmd_layout.addLayout(primary_layout)

        # Secondary Actions
        sec_layout = QHBoxLayout()
        sec_layout.setSpacing(8)
        
        self.copy_btn = QPushButton("📋" if compact_buttons else "📋 Copy Response")
        self.copy_btn.setToolTip("Copy the last assistant response markdown to the clipboard.")
        self.copy_btn.clicked.connect(self._copy_last_response)
        sec_layout.addWidget(self.copy_btn)
        
        self.resume_btn = QPushButton("📂" if compact_buttons else "📂 Resume Task")
        self.resume_btn.clicked.connect(main_window.resume_task_dialog)
        
        eject_label = "⏏️" if compact_buttons else "⏏️ Eject model"
        self.eject_btn = QPushButton(eject_label)
        self.eject_btn.setToolTip("Unload the Ollama model from VRAM.")
        self.eject_btn.clicked.connect(main_window.eject_ollama_model)
        
        if show_resume:
            sec_layout.addWidget(self.resume_btn)
        sec_layout.addWidget(self.eject_btn)
        
        if show_clear:
            self.clear_chat_btn = QPushButton("🧹" if compact_buttons else "🧹 Clear View")
            self.clear_chat_btn.clicked.connect(main_window.clear_chat_display)
            sec_layout.addWidget(self.clear_chat_btn)
        else:
            self.clear_chat_btn = None
            
        sec_layout.addStretch()
        cmd_layout.addLayout(sec_layout)

        layout.addWidget(self.command_bar, stretch=0)

        self.refresh_attachment_preview()

    def _thinking_label(self, *, expanded: bool) -> str:
        n = len(self.thinking_view.toPlainText())
        arrow = "▾" if expanded else "▸"
        count = f" ({_format_thinking_count(n)})" if n else ""
        source = " — content stream" if self._thinking_from_content else ""
        return f"{arrow} Thinking{count}{source}"

    def _on_thinking_toggled(self, checked: bool) -> None:
        self.thinking_view.setVisible(checked)
        self.thinking_toggle.setText(self._thinking_label(expanded=checked))

    def _collapse_thinking_pane(self) -> None:
        """Hide thinking body when answer starts; keep toggle for re-open."""
        self.thinking_toggle.setChecked(False)
        self.thinking_view.setVisible(False)
        if self.thinking_toggle.isVisible():
            self.thinking_toggle.setText(self._thinking_label(expanded=False))

    def set_thinking_from_content(self, from_content: bool) -> None:
        self._thinking_from_content = from_content
        if self.thinking_toggle.isVisible():
            self.thinking_toggle.setText(
                self._thinking_label(expanded=self.thinking_toggle.isChecked())
            )

    def _reset_thinking_pane(self) -> None:
        self._thinking_from_content = False
        self.thinking_toggle.setVisible(False)
        self.thinking_toggle.setChecked(False)
        self.thinking_toggle.setText("▸ Thinking")
        self.thinking_view.clear()
        self.thinking_view.setVisible(False)

    def refresh_theme(self, *, dark: bool) -> None:
        apply_panel_style(self.chat_history, "chat", dark=dark)
        apply_thinking_panel_style(self.thinking_view, dark=dark)
        hint_color = "#7f8c8d" if not dark else "#8e8e8e"
        self.attachments_preview.setStyleSheet(f"font-size: 9pt; color: {hint_color};")

    def append_chat_html(self, html: str) -> None:
        self.chat_history.append_smart(html)

    def clear_chat_display(self) -> None:
        self.chat_history.clear()
        self.chat_history.reset_scroll_follow()
        self.chat_history.setProperty("_stream_has_shell", False)
        self._reset_thinking_pane()

    def get_chat_input_text(self) -> str:
        return self.chat_input.text().strip()

    def clear_chat_input(self) -> None:
        self.chat_input.clear()

    def set_run_buttons_running(self, running: bool) -> None:
        self.run_btn.setDisabled(running)
        self.resume_btn.setDisabled(running)
        self.stop_btn.setDisabled(not running)

    def begin_assistant_stream(self) -> None:
        self._answer_started = False
        self._reset_thinking_pane()
        self.chat_history.setProperty("_stream_start_pos", None)
        self.chat_history.setProperty("_stream_has_shell", False)

    def stream_thinking_token(self, token: str) -> None:
        if not token:
            return
        if not self.thinking_toggle.isVisible():
            self._thinking_container.setVisible(True)
            self.thinking_toggle.setVisible(True)
            self.thinking_toggle.setChecked(True)
            self.thinking_view.setVisible(True)
        cursor = self.thinking_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(token)
        self.thinking_view.setTextCursor(cursor)
        bar = self.thinking_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.thinking_toggle.setText(self._thinking_label(expanded=True))

    def stream_chat_token(self, token: str) -> None:
        if token and not self._answer_started:
            self._answer_started = True
            self._collapse_thinking_pane()
            insert_assistant_stream_shell(self.chat_history)
        if token:
            self.chat_history.insert_text_smart(token)

    def finalize_streamed_message(self, raw_text: str) -> None:
        self._last_assistant_raw_text = raw_text
        finalize_streamed_message(self.chat_history, raw_text)

    def _copy_last_response(self) -> None:
        if self._last_assistant_raw_text:
            QApplication.clipboard().setText(self._last_assistant_raw_text)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """
        Support HTML links like `copy://<base64 urlencoded>`.
        QTextEdit will emit `anchorClicked` for these without any external navigation.
        """
        try:
            if not url:
                return
            if url.scheme().lower() != "copy":
                return
            data = (url.host() or "") + (url.path() or "")
            data = data.lstrip("/")
            import base64
            import urllib.parse

            # url in qt sometimes keeps the base64 in the path; decode safely.
            decoded = urllib.parse.unquote(data)
            raw = base64.b64decode(decoded.encode("ascii")).decode(
                "utf-8", errors="replace"
            )
            QApplication.clipboard().setText(raw)
        except Exception:
            # Copy shouldn't break rendering.
            return

    def refresh_attachment_preview(self) -> None:
        """Update the attachment hint label from the main window state."""
        file_names = list(getattr(self.main, "attached_file_names", []) or [])
        chunks = getattr(self.main, "attached_chunks", []) or []
        images = getattr(self.main, "attached_images", []) or []

        chunk_count = len(chunks)
        image_count = len(images)

        if not file_names and chunk_count == 0 and image_count == 0:
            self.attachments_preview.setText("")
            self.attachments_preview.setVisible(False)
            return

        self.attachments_preview.setVisible(True)
        names = ", ".join(file_names[:4]) + ("…" if len(file_names) > 4 else "")
        parts: list[str] = []
        if file_names:
            parts.append(f"{len(file_names)} file(s): {names}")
        if chunk_count:
            parts.append(f"{chunk_count} text chunk(s)")
        if image_count:
            parts.append(f"{image_count} image(s)")
        self.attachments_preview.setText("📎 Attached: " + " · ".join(parts))
