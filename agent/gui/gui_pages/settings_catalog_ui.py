"""Catalog-driven preference widgets for Settings GUI."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from agent.storage.config_catalog import CatalogSection, SettingDef


class PreferenceWidgets:
    """Maps catalog keys to Qt widgets."""

    def __init__(self) -> None:
        self.widgets: dict[str, dict] = {}
        self._hint_labels: list[QLabel] = []

    def add_section(self, form: QFormLayout, section: CatalogSection) -> None:
        if section.description:
            desc = QLabel(section.description)
            desc.setWordWrap(True)
            desc.setProperty("aquilaHint", True)
            self._hint_labels.append(desc)
            form.addRow(desc)

        for setting in section.settings:
            self._add_field(form, setting)

    def _add_field(self, form: QFormLayout, setting: SettingDef) -> None:
        label = QLabel(setting.label)
        label.setToolTip(setting.key)
        if setting.description:
            desc = QLabel(setting.description)
            desc.setWordWrap(True)
            desc.setProperty("aquilaHint", True)
            self._hint_labels.append(desc)
        else:
            desc = None

        if setting.type == "bool":
            inp: QWidget = QCheckBox()
        elif setting.type == "int":
            spin = QSpinBox()
            spin.setRange(0, 999_999_999)
            if setting.default.isdigit():
                spin.setValue(int(setting.default))
            inp = spin
        elif setting.type == "float":
            inp = QLineEdit()
            if setting.default:
                inp.setPlaceholderText(setting.default)
        else:
            inp = QLineEdit()
            if setting.default:
                inp.setPlaceholderText(setting.default)

        self.widgets[setting.key] = {
            "widget": inp,
            "type": setting.type,
            "default": setting.default,
            "label": setting.label,
            "section_label": setting.label,
        }

        vbox = QVBoxLayout()
        vbox.addWidget(inp)
        if desc:
            vbox.addWidget(desc)
        wrap = QWidget()
        wrap.setLayout(vbox)
        wrap.setProperty("aquilaPanel", True)
        form.addRow(label, wrap)

    def load_values(self, values: dict[str, str]) -> None:
        for key, meta in self.widgets.items():
            widget = meta["widget"]
            typ = meta["type"]
            val = values.get(key, meta["default"])
            if typ == "bool":
                widget.setChecked(val in ("1", "true", "yes", "on"))
            elif typ == "int":
                try:
                    widget.setValue(int(val))
                except ValueError:
                    pass
            else:
                widget.setText(val)

    def collect_updates(self) -> dict[str, str]:
        updates: dict[str, str] = {}
        for key, meta in self.widgets.items():
            widget = meta["widget"]
            typ = meta["type"]
            if typ == "bool":
                val = "1" if widget.isChecked() else "0"
            elif typ == "int":
                val = str(widget.value())
            else:
                val = widget.text().strip()
            updates[key] = val
        return updates

    def filter_text(self, query: str) -> set[str]:
        """Return keys matching query (for search highlight)."""
        q = query.strip().lower()
        if not q:
            return set(self.widgets)
        matched: set[str] = set()
        for key, meta in self.widgets.items():
            hay = f"{key} {meta.get('label', '')}".lower()
            if q in hay:
                matched.add(key)
        return matched
