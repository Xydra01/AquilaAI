"""Wrapping button rows for narrow side panes."""
from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy, QWidget
from qfluentwidgets.components.layout.flow_layout import FlowLayout


def make_wrapping_row(
    *,
    h_spacing: int = 6,
    v_spacing: int = 6,
    parent: QWidget | None = None,
) -> tuple[QWidget, FlowLayout]:
    """Return a widget whose children wrap to the next line when space is tight."""
    container = QWidget(parent)
    layout = FlowLayout(container, needAni=False, isTight=True)
    layout.setHorizontalSpacing(h_spacing)
    layout.setVerticalSpacing(v_spacing)
    container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    return container, layout


def clear_layout(layout: FlowLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
