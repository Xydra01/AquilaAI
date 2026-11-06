// apps/aquila_gui/theme/markdown_renderer.hpp
#pragma once

#include <QString>

namespace aquila::gui {

class MarkdownRenderer {
public:
    static QString toHtml(const QString& markdown);
};

}  // namespace aquila::gui

