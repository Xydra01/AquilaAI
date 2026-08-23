"""Aquila OS 3.5 — instance picker (home screen)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGridLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QComboBox,
)

from ..gui_modes import (
    INSTANCE_DEFAULT_MODE_IDS,
    WORKSPACE_MODE_FLAGS,
    data_processing_enabled,
    normalize_default_mode_id,
)
from agent.storage import (
    create_instance,
    delete_instance,
    ensure_default_instance,
    get_instance,
    list_instances,
    set_active_instance_id,
)
from ..gui_dialogs import information, question, warning


class HomePage(QWidget):
    """Select or create a specialized Aquila instance before entering a workspace."""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout(self)
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(16)
        
        title = QLabel("🦅 Aquila OS 3.5 — Choose your instance")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 8px;")
        main_layout.addWidget(title)
        
        desc = QLabel("Select an instance below to load its memory, or jump straight into a workspace.")
        desc.setStyleSheet("font-size: 14px; color: #7f8c8d; margin-bottom: 16px;")
        main_layout.addWidget(desc)

        self.instance_list = QListWidget()
        self.instance_list.setMinimumHeight(150)
        main_layout.addWidget(self.instance_list, stretch=1)

        form = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("New instance name")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(INSTANCE_DEFAULT_MODE_IDS))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        form.addWidget(self.name_input, stretch=2)
        form.addWidget(self.mode_combo)
        form.addWidget(self.model_combo)
        main_layout.addLayout(form)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_list)
        self.new_btn = QPushButton("New instance")
        self.new_btn.clicked.connect(self._create_instance)
        self.open_btn = QPushButton("Open selected")
        self.open_btn.clicked.connect(self._open_selected)
        self.delete_btn = QPushButton("Delete selected")
        self.delete_btn.clicked.connect(self._delete_selected)
        self.delete_btn.setEnabled(False)
        self.instance_list.currentItemChanged.connect(self._on_instance_selection_changed)
        buttons.addWidget(self.refresh_btn)
        buttons.addWidget(self.new_btn)
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.delete_btn)
        main_layout.addLayout(buttons)

        shortcuts_label = QLabel("Workspace shortcuts")
        shortcuts_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 24px;")
        main_layout.addWidget(shortcuts_label)
        
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        card_specs = [
            ("Chat Mode", "Conversational"),
            ("Autonomous Task", "Step-by-step"),
            ("Research Mode", "Gather & plan"),
            ("Writing Mode", "Draft focused"),
            ("Code Mode", "IDE & TDD"),
            ("Character Mode", "Roleplay"),
            ("Learn Mode", "Classroom & archives"),
        ]
        if data_processing_enabled():
            card_specs.insert(2, ("Data Processing", "Batch ingest & sort"))
        
        cols = 3
        for i, (mode_label, desc) in enumerate(card_specs):
            row = i // cols
            col = i % cols
            btn = QPushButton(f"{mode_label}\n{desc}")
            btn.setMinimumHeight(80)
            btn.setStyleSheet("text-align: left; padding: 12px; font-size: 13px;")
            btn.clicked.connect(lambda _checked=False, ml=mode_label: self._launch_workspace(ml))
            grid.addWidget(btn, row, col)
        main_layout.addLayout(grid)

        # Center the main container in the actual page layout
        outer_layout = QHBoxLayout()
        outer_layout.addStretch()
        outer_layout.addWidget(main_container, stretch=2)
        outer_layout.addStretch()
        layout.addLayout(outer_layout)

        self.refresh_list()

    def _selected_instance_id(self) -> str | None:
        item = self.instance_list.currentItem()
        if not item:
            return None
        return item.data(256)

    def _launch_workspace(self, mode_label: str) -> None:
        """Open the selected instance, then switch to the chosen workspace card."""
        iid = self._selected_instance_id()
        if not iid:
            warning(self, "Instance", "Select an instance first.")
            return

        # Ensure the instance is fully opened (agent instance cache reset + workspace entry).
        self._open_instance(iid, mode_label=mode_label)

    def _on_instance_selection_changed(self) -> None:
        iid = self._selected_instance_id()
        self.delete_btn.setEnabled(bool(iid) and iid != "default")

    def refresh_list(self) -> None:
        ensure_default_instance()
        self.instance_list.clear()
        for inst in list_instances():
            item = QListWidgetItem(
                f"{inst.display_name}  [{inst.id}] — {inst.specialty or inst.default_mode}"
            )
            item.setData(256, inst.id)
            self.instance_list.addItem(item)
        self._refresh_model_combo()
        self._on_instance_selection_changed()

    def _refresh_model_combo(self) -> None:
        from agent.core import client
        from agent.storage import load_runtime_settings

        settings = load_runtime_settings()
        current = self.model_combo.currentData() if self.model_combo.count() else ""
        self.model_combo.clear()
        self.model_combo.addItem("(use global default)", "")
        detail = client.discover_aquila_models(primary_base_url=settings.ollama_base_url)
        models = detail.get("models") or []
        if not models:
            hint = detail.get("error") or "No aquila models — check Settings"
            self.model_combo.addItem(f"({hint})", "")
        else:
            for name in models:
                self.model_combo.addItem(name, name)
        if current:
            idx = self.model_combo.findData(current)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)

    def _create_instance(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            warning(self, "Instance", "Enter a display name.")
            return
        model_override = self.model_combo.currentData()
        inst = create_instance(
            display_name=name,
            specialty="",
            default_mode=normalize_default_mode_id(self.mode_combo.currentText()),
            ollama_model=model_override or None,
        )
        self.name_input.clear()
        self.refresh_list()
        self._open_instance(inst.id)

    def _open_selected(self) -> None:
        item = self.instance_list.currentItem()
        if not item:
            warning(self, "Instance", "Select an instance to open.")
            return
        iid = item.data(256)
        self._open_instance(iid)

    def _delete_selected(self) -> None:
        iid = self._selected_instance_id()
        if not iid:
            warning(self, "Instance", "Select an instance to delete.")
            return
        if iid == "default":
            warning(self, "Instance", "The default instance cannot be deleted.")
            return
        inst = get_instance(iid)
        label = inst.display_name if inst else iid
        from PySide6.QtWidgets import QMessageBox

        answer = question(
            self,
            "Delete instance",
            (
                f"Delete instance “{label}” [{iid}]?\n\n"
                "This permanently removes its chat threads, personas, learn data, "
                "and workspace memory. This cannot be undone."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_instance(iid)
        except ValueError as exc:
            warning(self, "Instance", str(exc))
            return

        from agent.core import _agent_instances

        _agent_instances.pop(iid, None)
        if getattr(self.main_window, "active_instance_id", None) == iid:
            self.main_window.active_instance_id = "default"
            if hasattr(self.main_window, "_update_instance_label"):
                self.main_window._update_instance_label()
        self.refresh_list()
        information(self, "Instance", f"Deleted “{label}”.")

    def _open_instance(self, instance_id: str, mode_label: str | None = None) -> None:
        set_active_instance_id(instance_id)
        from agent.core import _agent_instances

        _agent_instances.pop(instance_id, None)
        if hasattr(self.main_window, "enter_workspace"):
            self.main_window.enter_workspace(instance_id, mode_label=mode_label)
