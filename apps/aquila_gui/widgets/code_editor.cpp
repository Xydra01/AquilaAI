// apps/aquila_gui/widgets/code_editor.cpp
#include "code_editor.hpp"
#include "inline_prompt_bar.hpp"
#include "inline_diff_overlay.hpp"

#include <QAction>
#include <QMenu>
#include <QPainter>
#include <QTextBlock>

namespace aquila::gui {

LineNumberArea::LineNumberArea(CodeEditor* editor) : QWidget(editor), codeEditor_(editor) {}

QSize LineNumberArea::sizeHint() const {
    return QSize(codeEditor_->lineNumberAreaWidth(), 0);
}

void LineNumberArea::paintEvent(QPaintEvent* event) {
    codeEditor_->lineNumberAreaPaintEvent(event);
}

CodeSyntaxHighlighter::CodeSyntaxHighlighter(QTextDocument* parent)
    : QSyntaxHighlighter(parent) {
    HighlightingRule rule;

    // Keywords (C++, Python, JSON)
    QTextCharFormat keywordFormat;
    keywordFormat.setForeground(QColor(QStringLiteral("#569cd6")));
    keywordFormat.setFontWeight(QFont::Bold);
    const QStringList keywordPatterns = {
        QStringLiteral("\\bclass\\b"), QStringLiteral("\\bconst\\b"), QStringLiteral("\\benum\\b"),
        QStringLiteral("\\bexplicit\\b"), QStringLiteral("\\bfor\\b"), QStringLiteral("\\bif\\b"),
        QStringLiteral("\\belse\\b"), QStringLiteral("\\bnamespace\\b"), QStringLiteral("\\boperator\\b"),
        QStringLiteral("\\bpublic\\b"), QStringLiteral("\\bprivate\\b"), QStringLiteral("\\bprotected\\b"),
        QStringLiteral("\\breturn\\b"), QStringLiteral("\\bstruct\\b"), QStringLiteral("\\btemplate\\b"),
        QStringLiteral("\\btypename\\b"), QStringLiteral("\\bvirtual\\b"), QStringLiteral("\\bwhile\\b"),
        QStringLiteral("\\bauto\\b"), QStringLiteral("\\bint\\b"), QStringLiteral("\\bbool\\b"),
        QStringLiteral("\\bdef\\b"), QStringLiteral("\\bimport\\b"), QStringLiteral("\\bfrom\\b"),
        QStringLiteral("\\btrue\\b"), QStringLiteral("\\bfalse\\b"), QStringLiteral("\\bnull\\b")
    };
    for (const QString& pattern : keywordPatterns) {
        rule.pattern = QRegularExpression(pattern);
        rule.format = keywordFormat;
        rules_.push_back(rule);
    }

    // Types
    QTextCharFormat typeFormat;
    typeFormat.setForeground(QColor(QStringLiteral("#4ec9b0")));
    rule.pattern = QRegularExpression(QStringLiteral("\\b[A-Z][A-Za-z0-9_]*\\b"));
    rule.format = typeFormat;
    rules_.push_back(rule);

    // Strings
    QTextCharFormat stringFormat;
    stringFormat.setForeground(QColor(QStringLiteral("#ce9178")));
    rule.pattern = QRegularExpression(QStringLiteral("\".*?\"|'.*?'"));
    rule.format = stringFormat;
    rules_.push_back(rule);

    // Single line comments
    QTextCharFormat commentFormat;
    commentFormat.setForeground(QColor(QStringLiteral("#6a9955")));
    commentFormat.setFontItalic(true);
    rule.pattern = QRegularExpression(QStringLiteral("//[^\n]*|#[^\n]*"));
    rule.format = commentFormat;
    rules_.push_back(rule);

    multiLineCommentFormat_.setForeground(QColor(QStringLiteral("#6a9955")));
    multiLineCommentFormat_.setFontItalic(true);
    commentStartExpression_ = QRegularExpression(QStringLiteral("/\\*"));
    commentEndExpression_ = QRegularExpression(QStringLiteral("\\*/"));
}

void CodeSyntaxHighlighter::highlightBlock(const QString& text) {
    for (const HighlightingRule& rule : rules_) {
        QRegularExpressionMatchIterator matchIterator = rule.pattern.globalMatch(text);
        while (matchIterator.hasNext()) {
            QRegularExpressionMatch match = matchIterator.next();
            setFormat(static_cast<int>(match.capturedStart()),
                      static_cast<int>(match.capturedLength()), rule.format);
        }
    }

    setCurrentBlockState(0);
    int startIndex = 0;
    if (previousBlockState() != 1) {
        startIndex = static_cast<int>(text.indexOf(commentStartExpression_));
    }

    while (startIndex >= 0) {
        QRegularExpressionMatch match = commentEndExpression_.match(text, startIndex);
        int endIndex = static_cast<int>(match.capturedStart());
        int commentLength = 0;
        if (endIndex == -1) {
            setCurrentBlockState(1);
            commentLength = static_cast<int>(text.length()) - startIndex;
        } else {
            commentLength = endIndex - startIndex + static_cast<int>(match.capturedLength());
        }
        setFormat(startIndex, commentLength, multiLineCommentFormat_);
        startIndex = static_cast<int>(text.indexOf(commentStartExpression_, startIndex + commentLength));
    }
}

CodeEditor::CodeEditor(QWidget* parent) : QPlainTextEdit(parent) {
    lineNumberArea_ = new LineNumberArea(this);
    highlighter_ = new CodeSyntaxHighlighter(document());

    promptBar_ = new InlinePromptBar(this);
    promptBar_->hide();
    connect(promptBar_, &InlinePromptBar::submitRequested, this, &CodeEditor::onPromptSubmitted);
    connect(promptBar_, &InlinePromptBar::cancelRequested, this, &CodeEditor::hideInlinePrompt);

    diffOverlay_ = new InlineDiffOverlay(this, this);
    connect(diffOverlay_, &InlineDiffOverlay::patchAccepted, this, [this](const QString&) {
        emit inlinePatchAccepted(filePath_);
    });
    connect(diffOverlay_, &InlineDiffOverlay::patchRejected, this, [this]() {
        emit inlinePatchRejected(filePath_);
    });

    setFont(QFont(QStringLiteral("Consolas"), 11));
    setLineWrapMode(QPlainTextEdit::NoWrap);

    connect(this, &QPlainTextEdit::blockCountChanged, this, &CodeEditor::updateLineNumberAreaWidth);
    connect(this, &QPlainTextEdit::updateRequest, this, &CodeEditor::updateLineNumberArea);
    connect(this, &QPlainTextEdit::cursorPositionChanged, this, &CodeEditor::highlightCurrentLine);

    updateLineNumberAreaWidth(0);
    highlightCurrentLine();
}

bool CodeEditor::hasPendingPatch() const {
    return diffOverlay_ && diffOverlay_->hasPendingPatch();
}

void CodeEditor::showInlinePrompt() {
    QTextCursor cursor = textCursor();
    if (!cursor.hasSelection()) {
        cursor.select(QTextCursor::LineUnderCursor);
        setTextCursor(cursor);
    }
    activeSelectionStart_ = cursor.selectionStart();
    activeSelectionLength_ = cursor.selectionEnd() - cursor.selectionStart();
    activeSelectedText_ = cursor.selectedText();

    repositionPromptBar();
    promptBar_->clearInput();
    promptBar_->show();
    promptBar_->raise();
    promptBar_->focusInput();
}

void CodeEditor::hideInlinePrompt() {
    if (promptBar_) {
        promptBar_->hide();
    }
    setFocus();
}

void CodeEditor::repositionPromptBar() {
    if (!promptBar_) return;
    const QRect rect = cursorRect(textCursor());
    const int barWidth = qMin(650, qMax(350, width() - 80));
    const int barHeight = 44;
    const int barX = qMax(lineNumberAreaWidth() + 10, qMin(width() - barWidth - 20, rect.left()));
    int barY = rect.bottom() + 6;
    if (barY + barHeight > height()) {
        barY = qMax(10, rect.top() - barHeight - 6);
    }
    promptBar_->setGeometry(barX, barY, barWidth, barHeight);
}

void CodeEditor::onPromptSubmitted(const QString& prompt) {
    hideInlinePrompt();
    emit inlinePromptSubmitted(prompt, activeSelectedText_, filePath_);
}

void CodeEditor::applyInlinePendingPatch(const QString& replacementText) {
    if (diffOverlay_) {
        diffOverlay_->startPendingPatch(activeSelectionStart_, activeSelectionLength_,
                                        activeSelectedText_, replacementText);
    }
}

void CodeEditor::acceptInlinePatch() {
    if (diffOverlay_) {
        diffOverlay_->acceptPatch();
    }
}

void CodeEditor::rejectInlinePatch() {
    if (diffOverlay_) {
        diffOverlay_->rejectPatch();
    }
}

void CodeEditor::keyPressEvent(QKeyEvent* event) {
    if (event->modifiers() == Qt::ControlModifier && event->key() == Qt::Key_K) {
        showInlinePrompt();
        event->accept();
        return;
    }

    if (diffOverlay_ && diffOverlay_->hasPendingPatch()) {
        if ((event->modifiers() == Qt::ControlModifier && (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter)) ||
            (event->key() == Qt::Key_Return && event->modifiers() == Qt::NoModifier)) {
            acceptInlinePatch();
            event->accept();
            return;
        }
        if (event->key() == Qt::Key_Escape) {
            rejectInlinePatch();
            event->accept();
            return;
        }
    }

    QPlainTextEdit::keyPressEvent(event);
}

int CodeEditor::lineNumberAreaWidth() {
    int digits = 1;
    int maxBlock = std::max(1, blockCount());
    while (maxBlock >= 10) {
        maxBlock /= 10;
        ++digits;
    }
    const int space = 12 + fontMetrics().horizontalAdvance(QLatin1Char('9')) * digits;
    return space;
}

void CodeEditor::updateLineNumberAreaWidth(int /* newBlockCount */) {
    setViewportMargins(lineNumberAreaWidth(), 0, 0, 0);
}

void CodeEditor::updateLineNumberArea(const QRect& rect, int dy) {
    if (dy != 0) {
        lineNumberArea_->scroll(0, dy);
    } else {
        lineNumberArea_->update(0, rect.y(), lineNumberArea_->width(), rect.height());
    }

    if (rect.contains(viewport()->rect())) {
        updateLineNumberAreaWidth(0);
    }
}

void CodeEditor::resizeEvent(QResizeEvent* event) {
    QPlainTextEdit::resizeEvent(event);
    const QRect cr = contentsRect();
    lineNumberArea_->setGeometry(QRect(cr.left(), cr.top(), lineNumberAreaWidth(), cr.height()));
}

void CodeEditor::highlightCurrentLine() {
    QList<QTextEdit::ExtraSelection> extraSelections;

    if (!isReadOnly()) {
        QTextEdit::ExtraSelection selection;
        const QColor lineColor = QColor(QStringLiteral("#2a2d2e"));
        selection.format.setBackground(lineColor);
        selection.format.setProperty(QTextFormat::FullWidthSelection, true);
        selection.cursor = textCursor();
        selection.cursor.clearSelection();
        extraSelections.append(selection);
    }

    setExtraSelections(extraSelections);
}

void CodeEditor::lineNumberAreaPaintEvent(QPaintEvent* event) {
    QPainter painter(lineNumberArea_);
    painter.fillRect(event->rect(), QColor(QStringLiteral("#1e1e1e")));

    QTextBlock block = firstVisibleBlock();
    int blockNumber = block.blockNumber();
    int top = static_cast<int>(blockBoundingGeometry(block).translated(contentOffset()).top());
    int bottom = top + static_cast<int>(blockBoundingRect(block).height());

    while (block.isValid() && top <= event->rect().bottom()) {
        if (block.isVisible() && bottom >= event->rect().top()) {
            const QString number = QString::number(blockNumber + 1);
            painter.setPen(QColor(QStringLiteral("#858585")));
            painter.setFont(font());
            painter.drawText(0, top, lineNumberArea_->width() - 6, fontMetrics().height(),
                             Qt::AlignRight, number);
        }

        block = block.next();
        top = bottom;
        bottom = top + static_cast<int>(blockBoundingRect(block).height());
        ++blockNumber;
    }
}

void CodeEditor::contextMenuEvent(QContextMenuEvent* event) {
    std::unique_ptr<QMenu> menu(createStandardContextMenu());
    menu->addSeparator();

    auto* inlineAct = menu->addAction(QStringLiteral("✨ Edit Selection with Agent... (Ctrl+K)"));
    const QString sel = textCursor().selectedText();
    inlineAct->setEnabled(!sel.isEmpty());
    connect(inlineAct, &QAction::triggered, this, &CodeEditor::showInlinePrompt);

    auto* subcallAct = menu->addAction(QStringLiteral("⚡ Ask Agent about Selection"));
    subcallAct->setEnabled(!sel.isEmpty());

    connect(subcallAct, &QAction::triggered, this, [this, sel]() {
        emit subcallRequested(sel);
    });

    menu->exec(event->globalPos());
}

}  // namespace aquila::gui

