// apps/aquila_gui/widgets/code_editor.hpp
#pragma once

#include <QPlainTextEdit>
#include <QSyntaxHighlighter>
#include <QRegularExpression>
#include <QWidget>
#include <vector>

namespace aquila::gui {

class CodeEditor;
class InlinePromptBar;
class InlineDiffOverlay;

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

    bool hasPendingPatch() const;
    void showInlinePrompt();
    void hideInlinePrompt();
    void applyInlinePendingPatch(const QString& replacementText);
    void acceptInlinePatch();
    void rejectInlinePatch();

signals:
    void subcallRequested(const QString& selectedText);
    void inlinePromptSubmitted(const QString& prompt, const QString& selectedText, const QString& filePath);
    void inlinePatchAccepted(const QString& filePath);
    void inlinePatchRejected(const QString& filePath);

protected:
    void resizeEvent(QResizeEvent* event) override;
    void contextMenuEvent(QContextMenuEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;

private slots:
    void updateLineNumberAreaWidth(int newBlockCount);
    void highlightCurrentLine();
    void updateLineNumberArea(const QRect& rect, int dy);
    void onPromptSubmitted(const QString& prompt);

private:
    void repositionPromptBar();

    QWidget* lineNumberArea_ = nullptr;
    CodeSyntaxHighlighter* highlighter_ = nullptr;
    InlinePromptBar* promptBar_ = nullptr;
    InlineDiffOverlay* diffOverlay_ = nullptr;
    QString filePath_;
    int activeSelectionStart_ = 0;
    int activeSelectionLength_ = 0;
    QString activeSelectedText_;
};

}  // namespace aquila::gui

