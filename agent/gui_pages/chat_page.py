"""Chat-only workspace (single column)."""
from PySide6.QtWidgets import QVBoxLayout, QLabel

from gui_pages.base import BaseModePage
from gui_theme import mode_accent_style
from gui_widgets.agent_rail import AgentRail


class ChatPage(BaseModePage):
    MODE = "chat"
    MODE_LABEL = "Chat Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        layout = QVBoxLayout(self)
        header = QLabel("Chat Workspace")
        header.setStyleSheet(mode_accent_style("chat"))
        layout.addWidget(header)
        self.agent_rail = AgentRail(
            main_window,
            placeholder="Say hello or ask a question...",
            show_resume=False,
            show_clear=True,
            compact_buttons=False,
        )
        self.agent_rail.run_btn.setText("▶️ Send")
        layout.addWidget(self.agent_rail)

    @property
    def chat_history(self):
        return self.agent_rail.chat_history

    @property
    def chat_input(self):
        return self.agent_rail.chat_input

    @property
    def attach_button(self):
        return self.agent_rail.attach_button

    @property
    def run_btn(self):
        return self.agent_rail.run_btn

    @property
    def stop_btn(self):
        return self.agent_rail.stop_btn

    @property
    def clear_chat_btn(self):
        return self.agent_rail.clear_chat_btn

    def refresh_theme(self, *, dark: bool) -> None:
        self.agent_rail.refresh_theme(dark=dark)

    def append_chat_html(self, html: str) -> None:
        self.agent_rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        self.agent_rail.clear_chat_display()

    def get_chat_input_text(self) -> str:
        return self.agent_rail.get_chat_input_text()

    def clear_chat_input(self) -> None:
        self.agent_rail.clear_chat_input()

    def set_run_buttons_running(self, running: bool) -> None:
        self.agent_rail.set_run_buttons_running(running)

    def begin_assistant_stream(self) -> None:
        self.agent_rail.begin_assistant_stream()

    def stream_chat_token(self, token: str) -> None:
        self.agent_rail.stream_chat_token(token)

    def finalize_streamed_message(self, raw_text: str) -> None:
        self.agent_rail.finalize_streamed_message(raw_text)
