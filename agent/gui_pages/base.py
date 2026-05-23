"""Base class for Aquila mode-specific workspace pages."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget


class BaseModePage(QWidget):
    """Thin shell around a mode layout; brain/loop stay in main.AgentWorker."""

    MODE: str = ""
    MODE_LABEL: str = ""

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self._worker = None

    def mode_flag(self) -> str:
        return self.MODE

    def on_activate(self) -> None:
        pass

    def on_deactivate(self) -> None:
        pass

    def bind_worker(self, worker) -> None:
        self._worker = worker

    def append_chat_html(self, html: str) -> None:
        pass

    def clear_chat_display(self) -> None:
        pass

    def get_chat_input_text(self) -> str:
        return ""

    def clear_chat_input(self) -> None:
        pass

    def set_run_buttons_running(self, running: bool) -> None:
        pass

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        pass

    def refresh_state(self) -> None:
        pass

    def stream_chat_token(self, token: str) -> None:
        pass

    def begin_assistant_stream(self) -> None:
        pass

    def finalize_streamed_message(self, raw_text: str) -> None:
        pass

    def get_extra_run_context(self) -> str:
        """Optional context merged into task prompt (journal, selection, etc.)."""
        return ""

    def get_extra_text_chunks(self) -> list[str]:
        """Optional extra attachment chunks for AgentWorker."""
        return []

    def on_task_started(self) -> None:
        pass

    def on_task_finished(self) -> None:
        pass

    def refresh_theme(self, *, dark: bool) -> None:
        pass
