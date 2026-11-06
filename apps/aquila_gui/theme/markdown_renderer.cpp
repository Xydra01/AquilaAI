// apps/aquila_gui/theme/markdown_renderer.cpp
#include "markdown_renderer.hpp"

#include <QRegularExpression>
#include <QStringList>

namespace aquila::gui {

QString MarkdownRenderer::toHtml(const QString& markdown) {
    if (markdown.trimmed().isEmpty()) {
        return {};
    }

    const QStringList lines = markdown.split(QLatin1Char('\n'));
    QString result;
    bool inCodeBlock = false;
    QString codeBlockLang;
    QString codeBlockContent;

    auto formatInline = [](QString text) -> QString {
        // Escape HTML
        text = text.toHtmlEscaped();

        // Inline code: `code`
        static const QRegularExpression inlineCodeRe(QStringLiteral("`([^`]+)`"));
        text.replace(inlineCodeRe, QStringLiteral("<code style='background-color: rgba(255, 255, 255, 0.12); color: #79c0ff; border-radius: 4px; padding: 1px 5px; font-family: Consolas, monospace; font-size: 11px;'>\\1</code>"));

        // Bold: **text** or __text__
        static const QRegularExpression boldRe(QStringLiteral("\\*\\*(.+?)\\*\\*"));
        text.replace(boldRe, QStringLiteral("<b>\\1</b>"));

        // Italic: *text* (when not bold)
        static const QRegularExpression italicRe(QStringLiteral("(?<!\\*)\\*(?!\\*)(.+?)(?<!\\*)\\*(?!\\*)"));
        text.replace(italicRe, QStringLiteral("<i>\\1</i>"));

        return text;
    };

    for (int i = 0; i < lines.size(); ++i) {
        const QString& rawLine = lines[i];
        const QString trimmed = rawLine.trimmed();

        // Code block start / end
        if (trimmed.startsWith(QLatin1String("```"))) {
            if (!inCodeBlock) {
                inCodeBlock = true;
                codeBlockLang = trimmed.mid(3).trimmed();
                codeBlockContent.clear();
            } else {
                inCodeBlock = false;
                QString langHeader;
                if (!codeBlockLang.isEmpty()) {
                    langHeader = QStringLiteral("<div style='font-size: 10px; color: #858585; margin-bottom: 6px; text-transform: uppercase; font-weight: bold;'>%1</div>")
                                     .arg(codeBlockLang.toHtmlEscaped());
                }
                result += QStringLiteral(
                    "<div style='background-color: #161618; border: 1px solid #3c3c3c; border-radius: 6px; "
                    "            margin: 8px 0; padding: 10px 12px; font-family: Consolas, monospace; font-size: 12px; "
                    "            color: #d4d4d4; white-space: pre-wrap;'>"
                    "%1<code>%2</code>"
                    "</div>"
                ).arg(langHeader, codeBlockContent.toHtmlEscaped());
            }
            continue;
        }

        if (inCodeBlock) {
            if (!codeBlockContent.isEmpty()) {
                codeBlockContent += QLatin1Char('\n');
            }
            codeBlockContent += rawLine;
            continue;
        }

        // Horizontal rule
        if (trimmed == QLatin1String("---") || trimmed == QLatin1String("***") || trimmed == QLatin1String("___")) {
            result += QStringLiteral("<hr style='border: none; border-top: 1px solid #3c3c3c; margin: 10px 0;'/>");
            continue;
        }

        // Headings
        if (trimmed.startsWith(QLatin1String("### "))) {
            result += QStringLiteral("<h3 style='color: #e6edf3; font-size: 13px; font-weight: bold; margin: 8px 0 4px 0;'>%1</h3>")
                          .arg(formatInline(trimmed.mid(4)));
            continue;
        }
        if (trimmed.startsWith(QLatin1String("## "))) {
            result += QStringLiteral("<h2 style='color: #79c0ff; font-size: 14px; font-weight: bold; margin: 10px 0 6px 0;'>%1</h2>")
                          .arg(formatInline(trimmed.mid(3)));
            continue;
        }
        if (trimmed.startsWith(QLatin1String("# "))) {
            result += QStringLiteral("<h1 style='color: #58a6ff; font-size: 16px; font-weight: bold; margin: 12px 0 6px 0; border-bottom: 1px solid #333; padding-bottom: 4px;'>%1</h1>")
                          .arg(formatInline(trimmed.mid(2)));
            continue;
        }

        // Blockquote
        if (trimmed.startsWith(QLatin1String("> "))) {
            result += QStringLiteral("<div style='border-left: 3px solid #0078d4; padding-left: 10px; margin: 6px 0; color: #8b949e; font-style: italic;'>%1</div>")
                          .arg(formatInline(trimmed.mid(2)));
            continue;
        }

        // Bullet lists
        if (trimmed.startsWith(QLatin1String("- ")) || trimmed.startsWith(QLatin1String("* "))) {
            result += QStringLiteral("<div style='margin-left: 14px; margin-bottom: 3px; color: #e0e0e0;'>• %1</div>")
                          .arg(formatInline(trimmed.mid(2)));
            continue;
        }

        // Numbered lists
        static const QRegularExpression numberedListRe(QStringLiteral("^(\\d+\\.)\\s+(.*)$"));
        auto match = numberedListRe.match(trimmed);
        if (match.hasMatch()) {
            result += QStringLiteral("<div style='margin-left: 14px; margin-bottom: 3px; color: #e0e0e0;'><b>%1</b> %2</div>")
                          .arg(match.captured(1).toHtmlEscaped(), formatInline(match.captured(2)));
            continue;
        }

        // Empty line
        if (trimmed.isEmpty()) {
            result += QStringLiteral("<div style='height: 6px;'></div>");
            continue;
        }

        // Normal paragraph text
        result += QStringLiteral("<div style='margin-bottom: 4px; line-height: 1.4;'>%1</div>")
                      .arg(formatInline(rawLine));
    }

    // Unclosed code block guard
    if (inCodeBlock) {
        result += QStringLiteral(
            "<div style='background-color: #161618; border: 1px solid #3c3c3c; border-radius: 6px; "
            "            margin: 8px 0; padding: 10px 12px; font-family: Consolas, monospace; font-size: 12px; "
            "            color: #d4d4d4; white-space: pre-wrap;'>"
            "<code>%1</code>"
            "</div>"
        ).arg(codeBlockContent.toHtmlEscaped());
    }

    return result;
}

}  // namespace aquila::gui

