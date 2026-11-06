// apps/aquila_gui/widgets/inline_diff_overlay.cpp
#include "inline_diff_overlay.hpp"

#include <QColor>
#include <QScrollBar>
#include <QTextBlock>
#include <QTextCursor>

namespace aquila::gui {

InlinePatchPill::InlinePatchPill(QWidget* parent) : QFrame(parent) {
    setObjectName(QStringLiteral("inlinePatchPill"));
    setStyleSheet(QStringLiteral(
        "QFrame#inlinePatchPill {"
        "  background-color: #2d2d30;"
        "  border: 1px solid #3e3e42;"
        "  border-radius: 5px;"
        "  padding: 2px 6px;"
        "}"
        "QLabel {"
        "  color: #cccccc;"
        "  font-size: 11px;"
        "  font-weight: bold;"
        "  background: transparent;"
        "}"
        "QPushButton {"
        "  border-radius: 3px;"
        "  padding: 3px 8px;"
        "  font-size: 11px;"
        "  font-weight: bold;"
        "}"
        "QPushButton#acceptBtn {"
        "  background-color: #238636;"
        "  color: #ffffff;"
        "  border: none;"
        "}"
        "QPushButton#acceptBtn:hover {"
        "  background-color: #2ea043;"
        "}"
        "QPushButton#rejectBtn {"
        "  background-color: #444444;"
        "  color: #f85149;"
        "  border: 1px solid #555555;"
        "}"
        "QPushButton#rejectBtn:hover {"
        "  background-color: #555555;"
        "}"
    ));

    auto* layout = new QHBoxLayout(this);
    layout->setContentsMargins(6, 3, 6, 3);
    layout->setSpacing(8);

    statsLabel_ = new QLabel(QStringLiteral("Pending Patch"), this);
    layout->addWidget(statsLabel_);

    acceptBtn_ = new QPushButton(QStringLiteral("Accept (Ctrl+Enter)"), this);
    acceptBtn_->setObjectName(QStringLiteral("acceptBtn"));
    layout->addWidget(acceptBtn_);

    rejectBtn_ = new QPushButton(QStringLiteral("Reject (Esc)"), this);
    rejectBtn_->setObjectName(QStringLiteral("rejectBtn"));
    layout->addWidget(rejectBtn_);

    connect(acceptBtn_, &QPushButton::clicked, this, &InlinePatchPill::acceptRequested);
    connect(rejectBtn_, &QPushButton::clicked, this, &InlinePatchPill::rejectRequested);
}

void InlinePatchPill::setDiffSummary(int additions, int deletions) {
    statsLabel_->setText(QStringLiteral("<span style='color:#3fb950;'>+%1</span> <span style='color:#f85149;'>-%2</span>")
        .arg(additions).arg(deletions));
}

InlineDiffOverlay::InlineDiffOverlay(QPlainTextEdit* editor, QObject* parent)
    : QObject(parent), editor_(editor) {
    pill_ = new InlinePatchPill(editor_);
    pill_->hide();

    connect(pill_, &InlinePatchPill::acceptRequested, this, &InlineDiffOverlay::acceptPatch);
    connect(pill_, &InlinePatchPill::rejectRequested, this, &InlineDiffOverlay::rejectPatch);

    if (editor_->verticalScrollBar()) {
        connect(editor_->verticalScrollBar(), &QScrollBar::valueChanged, this, &InlineDiffOverlay::repositionPill);
    }
}

InlineDiffOverlay::~InlineDiffOverlay() {
    active_ = false;
}

void InlineDiffOverlay::startPendingPatch(int selectionStart, int selectionLength,
                                         const QString& originalText, const QString& replacementText) {
    active_ = true;
    selectionStart_ = selectionStart;
    selectionLength_ = selectionLength;
    originalText_ = originalText;
    replacementText_ = replacementText;

    // Replace document text at selection with replacement text
    QTextCursor cursor(editor_->document());
    cursor.setPosition(selectionStart_);
    cursor.setPosition(selectionStart_ + selectionLength_, QTextCursor::KeepAnchor);
    cursor.beginEditBlock();
    cursor.insertText(replacementText_);
    cursor.endEditBlock();

    // Compute diff stats
    const QStringList origLines = originalText_.split(QLatin1Char('\n'));
    const QStringList repLines = replacementText_.split(QLatin1Char('\n'));
    pill_->setDiffSummary(repLines.size(), origLines.size());

    applyDiffSelections();
    repositionPill();
    pill_->show();
    pill_->raise();
}

void InlineDiffOverlay::applyDiffSelections() {
    if (!active_ || !editor_) return;

    QList<QTextEdit::ExtraSelection> selections = editor_->extraSelections();

    // Add green highlight for inserted/modified replacement range
    QTextEdit::ExtraSelection sel;
    sel.format.setBackground(QColor(30, 70, 45, 160)); // Soft dark green
    sel.cursor = QTextCursor(editor_->document());
    sel.cursor.setPosition(selectionStart_);
    sel.cursor.setPosition(selectionStart_ + static_cast<int>(replacementText_.length()), QTextCursor::KeepAnchor);
    selections.append(sel);

    editor_->setExtraSelections(selections);
}

void InlineDiffOverlay::repositionPill() {
    if (!active_ || !editor_ || !pill_->isVisible()) return;

    QTextCursor cursor(editor_->document());
    cursor.setPosition(selectionStart_ + static_cast<int>(replacementText_.length()));
    const QRect rect = editor_->cursorRect(cursor);

    const int pillX = qMax(10, rect.left() - pill_->width() / 2);
    const int pillY = qMin(editor_->height() - pill_->height() - 10, rect.bottom() + 6);

    pill_->move(pillX, pillY);
}

void InlineDiffOverlay::acceptPatch() {
    if (!active_) return;
    const QString rep = replacementText_;
    clear();
    emit patchAccepted(rep);
}

void InlineDiffOverlay::rejectPatch() {
    if (!active_) return;

    // Revert replacement text back to original
    QTextCursor cursor(editor_->document());
    cursor.setPosition(selectionStart_);
    cursor.setPosition(selectionStart_ + static_cast<int>(replacementText_.length()), QTextCursor::KeepAnchor);
    cursor.beginEditBlock();
    cursor.insertText(originalText_);
    cursor.endEditBlock();

    clear();
    emit patchRejected();
}

void InlineDiffOverlay::clear() {
    active_ = false;
    pill_->hide();
    if (editor_) {
        // Clear diff extra selections
        editor_->setExtraSelections({});
    }
}

}  // namespace aquila::gui
