// apps/aquila_gui/widgets/code_editor.hpp
#pragma once

#include <QPlainTextEdit>
#include <QSyntaxHighlighter>
#include <QRegularExpression>
#include <QWidget>
#include <vector>

namespace aquila::gui {

class CodeEditor;

class LineNumberArea : public QWidget {
    Q_OBJECT
public:
    explicit LineNumberArea(CodeEditor* editor);
    QSize sizeHint() const override;

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    CodeEditor* codeEditor_ = nullptr;
};

class CodeSyntaxHighlighter : public QSyntaxHighlighter {
    Q_OBJECT
public:
    explicit CodeSyntaxHighlighter(QTextDocument* parent = nullptr);

protected:
    void highlightBlock(const QString& text) override;

private:
    struct HighlightingRule {
        QRegularExpression pattern;
        QTextCharFormat format;
    };
    std::vector<HighlightingRule> rules_;
    QTextCharFormat multiLineCommentFormat_;
    QRegularExpression commentStartExpression_;
    QRegularExpression commentEndExpression_;
};

class CodeEditor : public QPlainTextEdit {
    Q_OBJECT
public:
    explicit CodeEditor(QWidget* parent = nullptr);

    void lineNumberAreaPaintEvent(QPaintEvent* event);
    int lineNumberAreaWidth();

    QString filePath() const { return filePath_; }
    void setFilePath(const QString& path) { filePath_ = path; }

signals:
    void subcallRequested(const QString& selectedText);

protected:
    void resizeEvent(QResizeEvent* event) override;
    void contextMenuEvent(QContextMenuEvent* event) override;

private slots:
    void updateLineNumberAreaWidth(int newBlockCount);
    void highlightCurrentLine();
    void updateLineNumberArea(const QRect& rect, int dy);

private:
    QWidget* lineNumberArea_ = nullptr;
    CodeSyntaxHighlighter* highlighter_ = nullptr;
    QString filePath_;
};

}  // namespace aquila::gui

