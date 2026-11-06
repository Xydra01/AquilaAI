// apps/aquila_gui/theme/theme.cpp
#include "theme.hpp"

namespace aquila::gui {

namespace {
ThemeMode g_current_theme = ThemeMode::Dark;
}

QString dark_theme_qss() {
    return QString::fromUtf8(R"QSS(
QMainWindow, QDialog, QWizard {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}
QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget, QListWidget {
    background-color: #252526;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}
QLineEdit {
    min-height: 24px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0078d4;
}
QPushButton {
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #3c3c3c;
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #383838;
    border-color: #555555;
}
QPushButton:pressed {
    background-color: #1f1f1f;
}
QPushButton:disabled {
    color: #6e6e6e;
    background-color: #252526;
    border-color: #303030;
}
QPushButton[accent="true"] {
    background-color: #0078d4;
    border-color: #0078d4;
    color: #ffffff;
}
QPushButton[accent="true"]:hover {
    background-color: #1084d8;
}
QTabWidget::pane {
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    background-color: #1e1e1e;
}
QTabBar::tab {
    background: #252526;
    color: #a0a0a0;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #1e1e1e;
    font-weight: 600;
    color: #ffffff;
    border-top: 2px solid #0078d4;
}
QLabel {
    color: #e0e0e0;
}
QCheckBox, QRadioButton {
    color: #e0e0e0;
    spacing: 6px;
}
QComboBox, QSpinBox {
    background: #252526;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    padding: 5px 10px;
    border-radius: 6px;
    min-height: 22px;
}
QComboBox QAbstractItemView {
    background-color: #252526;
    color: #e0e0e0;
    selection-background-color: #0078d4;
}
QGroupBox {
    color: #e0e0e0;
    font-weight: 600;
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}
QSplitter::handle {
    background: #333333;
    width: 2px;
    height: 2px;
}
QScrollBar:vertical {
    border: none;
    background: #1e1e1e;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #424242;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #555555;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QProgressBar {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
}
QProgressBar::chunk {
    background-color: #0078d4;
    border-radius: 3px;
}
QHeaderView::section {
    background-color: #252526;
    color: #e0e0e0;
    padding: 4px;
    border: 1px solid #333333;
    font-weight: 600;
}
)QSS");
}

QString light_theme_qss() {
    return QString::fromUtf8(R"QSS(
QMainWindow, QDialog, QWizard {
    background-color: #f3f3f3;
    color: #1c1c1c;
}
QWidget {
    background-color: #f3f3f3;
    color: #1c1c1c;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}
QTextEdit, QLineEdit, QPlainTextEdit, QTreeWidget, QListWidget {
    background-color: #ffffff;
    color: #1c1c1c;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}
QLineEdit {
    min-height: 24px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0078d4;
}
QPushButton {
    background-color: #fbfbfb;
    color: #1c1c1c;
    border: 1px solid #dcdcdc;
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #f0f0f0;
    border-color: #c0c0c0;
}
QPushButton:pressed {
    background-color: #e5e5e5;
}
QPushButton:disabled {
    color: #a0a0a0;
    background-color: #f0f0f0;
    border-color: #e0e0e0;
}
QPushButton[accent="true"] {
    background-color: #0078d4;
    border-color: #0078d4;
    color: #ffffff;
}
QPushButton[accent="true"]:hover {
    background-color: #1084d8;
}
QTabWidget::pane {
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    background-color: #ffffff;
}
QTabBar::tab {
    background: #e8e8e8;
    color: #555555;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #ffffff;
    font-weight: 600;
    color: #1c1c1c;
    border-top: 2px solid #0078d4;
}
QLabel {
    color: #1c1c1c;
}
QCheckBox, QRadioButton {
    color: #1c1c1c;
    spacing: 6px;
}
QComboBox, QSpinBox {
    background: #ffffff;
    color: #1c1c1c;
    border: 1px solid #dcdcdc;
    padding: 5px 10px;
    border-radius: 6px;
    min-height: 22px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1c1c1c;
    selection-background-color: #0078d4;
}
QGroupBox {
    color: #1c1c1c;
    font-weight: 600;
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}
QSplitter::handle {
    background: #e0e0e0;
    width: 2px;
    height: 2px;
}
QScrollBar:vertical {
    border: none;
    background: #f3f3f3;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #c8c8c8;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #a8a8a8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QProgressBar {
    background-color: #e8e8e8;
    border: 1px solid #dcdcdc;
    border-radius: 4px;
    text-align: center;
    color: #1c1c1c;
}
QProgressBar::chunk {
    background-color: #0078d4;
    border-radius: 3px;
}
QHeaderView::section {
    background-color: #f0f0f0;
    color: #1c1c1c;
    padding: 4px;
    border: 1px solid #e0e0e0;
    font-weight: 600;
}
)QSS");
}

void apply_theme(QApplication* app, ThemeMode mode) {
    g_current_theme = mode;
    if (app != nullptr) {
        if (mode == ThemeMode::Dark) {
            app->setStyleSheet(dark_theme_qss());
        } else {
            app->setStyleSheet(light_theme_qss());
        }
    }
}

ThemeMode current_theme() {
    return g_current_theme;
}

void toggle_theme(QApplication* app) {
    if (g_current_theme == ThemeMode::Dark) {
        apply_theme(app, ThemeMode::Light);
    } else {
        apply_theme(app, ThemeMode::Dark);
    }
}

}  // namespace aquila::gui

