// apps/aquila_gui/theme/theme.hpp
#pragma once

#include <QApplication>
#include <QString>

namespace aquila::gui {

enum class ThemeMode { Dark, Light };

QString dark_theme_qss();
QString light_theme_qss();

void apply_theme(QApplication* app, ThemeMode mode);
ThemeMode current_theme();
void toggle_theme(QApplication* app);

}  // namespace aquila::gui

