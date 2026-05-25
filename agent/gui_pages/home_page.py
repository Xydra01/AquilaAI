"""Aquila OS 3.4 — instance picker (home screen)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QComboBox,
    QMessageBox,
)

from instance_registry import (
    create_instance,
    ensure_default_instance,
    list_instances,
    set_active_instance_id,
)


class HomePage(QWidget):
    """Select or create a specialized Aquila instance before entering a workspace."""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout(self)
        title = QLabel("🦅 Aquila OS 3.4 — Choose your instance")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Each instance has isolated scratchpad, episodic memory, and workspace summary."))

        self.instance_list = QListWidget()
        layout.addWidget(self.instance_list, stretch=1)

        form = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("New instance name")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            ["chat", "research", "code", "writing", "character", "autonomous"]
        )
        form.addWidget(self.name_input, stretch=2)
        form.addWidget(self.mode_combo)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_list)
        self.new_btn = QPushButton("New instance")
        self.new_btn.clicked.connect(self._create_instance)
        self.open_btn = QPushButton("Open selected")
        self.open_btn.clicked.connect(self._open_selected)
        buttons.addWidget(self.refresh_btn)
        buttons.addWidget(self.new_btn)
        buttons.addWidget(self.open_btn)
        layout.addLayout(buttons)

        self.refresh_list()

    def refresh_list(self) -> None:
        ensure_default_instance()
        self.instance_list.clear()
        for inst in list_instances():
            item = QListWidgetItem(
                f"{inst.display_name}  [{inst.id}] — {inst.specialty or inst.default_mode}"
            )
            item.setData(256, inst.id)
            self.instance_list.addItem(item)

    def _create_instance(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Instance", "Enter a display name.")
            return
        inst = create_instance(
            display_name=name,
            specialty="",
            default_mode=self.mode_combo.currentText(),
        )
        self.name_input.clear()
        self.refresh_list()
        self._open_instance(inst.id)

    def _open_selected(self) -> None:
        item = self.instance_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Instance", "Select an instance to open.")
            return
        iid = item.data(256)
        self._open_instance(iid)

    def _open_instance(self, instance_id: str) -> None:
        set_active_instance_id(instance_id)
        from main import _agent_instances

        _agent_instances.pop(instance_id, None)
        if hasattr(self.main_window, "enter_workspace"):
            self.main_window.enter_workspace(instance_id)
