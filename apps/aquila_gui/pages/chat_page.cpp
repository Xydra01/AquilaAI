// apps/aquila_gui/pages/chat_page.cpp
#include "chat_page.hpp"

#include <QDragEnterEvent>
#include <QDropEvent>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QMimeData>
#include <QScrollBar>
#include <QUrl>

namespace aquila::gui {

ChatPage::ChatPage(QWidget* parent)
    : BasePage(QStringLiteral("Chat Mode"),
               QStringLiteral("Conversational AI with Live Token Streaming and Markdown"),
               QStringLiteral("💬"), parent) {
    setAcceptDrops(true);
    auto* layout = contentLayout();

    // Transcript view
    transcript_ = new QTextEdit(this);
    transcript_->setReadOnly(true);
    transcript_->setFrameShape(QFrame::NoFrame);
    transcript_->setStyleSheet(QStringLiteral(
        "QTextEdit {"
        "    background-color: #1e1e1e;"
        "    border: 1px solid #333333;"
        "    border-radius: 8px;"
        "    padding: 12px;"
        "    font-size: 13px;"
        "}"
    ));
    layout->addWidget(transcript_, 1);

    // Follow-up suggestions container
    suggestionsContainer_ = new QWidget(this);
    suggestionsLayout_ = new FlowLayout(suggestionsContainer_, 0, 6, 6);
    layout->addWidget(suggestionsContainer_);

    // Attachments container
    attachmentsContainer_ = new QWidget(this);
    attachmentsLayout_ = new FlowLayout(attachmentsContainer_, 0, 6, 6);
    layout->addWidget(attachmentsContainer_);

    // Input row
    auto* inputRow = new QHBoxLayout();
    inputRow->setSpacing(8);

    promptInput_ = new QPlainTextEdit(this);
    promptInput_->setPlaceholderText(QStringLiteral("Type a message or instruction... (Enter to send, Shift+Enter for newline)"));
    promptInput_->setMaximumHeight(80);
    promptInput_->setMinimumHeight(44);
    promptInput_->installEventFilter(this);
    inputRow->addWidget(promptInput_, 1);

    auto* btnCol = new QVBoxLayout();
    btnCol->setSpacing(4);

    attachButton_ = new QPushButton(QStringLiteral("📎"), this);
    attachButton_->setToolTip(QStringLiteral("Attach file..."));
    attachButton_->setFixedSize(38, 36);
    connect(attachButton_, &QPushButton::clicked, this, &ChatPage::onAttachClicked);
    btnCol->addWidget(attachButton_);

    sendButton_ = new QPushButton(QStringLiteral("Send"), this);
    sendButton_->setProperty("accent", true);
    sendButton_->setFixedSize(64, 36);
    connect(sendButton_, &QPushButton::clicked, this, &ChatPage::onSendClicked);
    btnCol->addWidget(sendButton_);

    stopButton_ = new QPushButton(QStringLiteral("Stop"), this);
    stopButton_->setStyleSheet(QStringLiteral("background-color: #a80000; color: #ffffff;"));
    stopButton_->setFixedSize(64, 36);
    stopButton_->setVisible(false);
    connect(stopButton_, &QPushButton::clicked, this, &ChatPage::cancelRequested);
    btnCol->addWidget(stopButton_);

    inputRow->addLayout(btnCol);
    layout->addLayout(inputRow);

    appendSystemMessage(QStringLiteral("Welcome to Aquila Chat. Ask questions, explore code, or request assistance."));
    setFollowupSuggestions({
        QStringLiteral("Can you explain the system architecture?"),
        QStringLiteral("List all available recipe workflows"),
        QStringLiteral("How does the context condenser work?")
    });
}

void ChatPage::appendUserMessage(const QString& text, const QStringList& attachments) {
    finalizeAssistantMessage();

    QString attachHtml;
    if (!attachments.isEmpty()) {
        attachHtml += QStringLiteral("<div style='margin-bottom: 6px;'>");
        for (const auto& a : attachments) {
            QFileInfo fi(a);
            attachHtml += QStringLiteral(
                "<span style='background-color: rgba(255,255,255,0.18); border-radius: 6px; padding: 2px 7px; margin-right: 4px; font-size: 11px;'>"
                "📎 %1"
                "</span>"
            ).arg(fi.fileName().toHtmlEscaped());
        }
        attachHtml += QStringLiteral("</div>");
    }

    const QString html = QStringLiteral(
        "<div style='margin-bottom: 12px; text-align: right;'>"
        "  <div style='background-color: #0078d4; color: #ffffff; border-radius: 12px; "
        "               padding: 8px 14px; display: inline-block; max-width: 80%%; text-align: left;'>"
        "    %1"
        "    <div>%2</div>"
        "  </div>"
        "</div>"
    ).arg(attachHtml, text.toHtmlEscaped());

    transcript_->append(html);
    auto* bar = transcript_->verticalScrollBar();
    bar->setValue(bar->maximum());
}

bool ChatPage::eventFilter(QObject* watched, QEvent* event) {
    if (watched == promptInput_ && event->type() == QEvent::KeyPress) {
        auto* keyEvent = static_cast<QKeyEvent*>(event);
        if (keyEvent->key() == Qt::Key_Return || keyEvent->key() == Qt::Key_Enter) {
            if (keyEvent->modifiers() & Qt::ShiftModifier) {
                return false; // let QPlainTextEdit insert newline
            } else {
                onSendClicked();
                return true; // handled
            }
        }
    }
    return BasePage::eventFilter(watched, event);
}

void ChatPage::dragEnterEvent(QDragEnterEvent* event) {
    if (event->mimeData() && event->mimeData()->hasUrls()) {
        event->acceptProposedAction();
    } else {
        BasePage::dragEnterEvent(event);
    }
}

void ChatPage::dropEvent(QDropEvent* event) {
    if (event->mimeData() && event->mimeData()->hasUrls()) {
        for (const auto& url : event->mimeData()->urls()) {
            if (url.isLocalFile()) {
                addAttachment(url.toLocalFile());
            }
        }
        event->acceptProposedAction();
    } else {
        BasePage::dropEvent(event);
    }
}

void ChatPage::addAttachment(const QString& file) {
    if (file.isEmpty() || currentAttachments_.contains(file)) return;
    currentAttachments_.append(file);
    QFileInfo fi(file);
    QString sizeStr;
    const qint64 sz = fi.size();
    if (sz < 1024) sizeStr = QStringLiteral("%1 B").arg(sz);
    else if (sz < 1024 * 1024) sizeStr = QStringLiteral("%1 KB").arg(sz / 1024);
    else sizeStr = QStringLiteral("%1 MB").arg(sz / (1024 * 1024));

    auto* chip = new QPushButton(QStringLiteral("📎 %1 (%2) ✕").arg(fi.fileName(), sizeStr), attachmentsContainer_);
    chip->setStyleSheet(QStringLiteral(
        "background-color: #333333; color: #79c0ff; border: 1px solid #444444; border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: bold;"
    ));
    connect(chip, &QPushButton::clicked, this, [this, chip, file]() {
        currentAttachments_.removeAll(file);
        attachmentsLayout_->removeWidget(chip);
        delete chip;
    });
    attachmentsLayout_->addWidget(chip);
}

void ChatPage::appendAssistantMessage(const QString& text) {
    finalizeAssistantMessage();
    currentAssistantReply_ = text;
    const QString html = QStringLiteral(
        "<div style='margin-bottom: 12px; text-align: left;'>"
        "  <div style='background-color: #252526; color: #e0e0e0; border: 1px solid #3c3c3c; "
        "              border-radius: 12px; padding: 10px 14px; display: inline-block; max-width: 85%%;'>"
        "    <div style='font-size: 11px; font-weight: bold; color: #79c0ff; margin-bottom: 4px;'>🦅 Aquila</div>"
        "    <div>%1</div>"
        "  </div>"
        "</div>"
    ).arg(text.toHtmlEscaped());

    transcript_->append(html);
    auto* bar = transcript_->verticalScrollBar();
    bar->setValue(bar->maximum());
}

void ChatPage::appendToken(const QString& token) {
    if (!isStreaming_) {
        isStreaming_ = true;
        currentAssistantReply_.clear();
        transcript_->append(QStringLiteral(
            "<div id='streamingBubble' style='margin-bottom: 12px; text-align: left;'>"
            "  <div style='background-color: #252526; color: #e0e0e0; border: 1px solid #3c3c3c; "
            "              border-radius: 12px; padding: 10px 14px; display: inline-block; max-width: 85%%;'>"
            "    <div style='font-size: 11px; font-weight: bold; color: #79c0ff; margin-bottom: 4px;'>🦅 Aquila</div>"
            "    <span id='streamingText'></span>"
            "  </div>"
            "</div>"
        ));
    }

    currentAssistantReply_ += token;
    // Fast append into document
    auto cursor = transcript_->textCursor();
    cursor.movePosition(QTextCursor::End);
    cursor.insertText(token);
    transcript_->setTextCursor(cursor);

    auto* bar = transcript_->verticalScrollBar();
    bar->setValue(bar->maximum());
}

void ChatPage::finalizeAssistantMessage() {
    if (isStreaming_) {
        isStreaming_ = false;
        currentAssistantReply_.clear();
    }
}

void ChatPage::appendSystemMessage(const QString& text) {
    finalizeAssistantMessage();
    const QString html = QStringLiteral(
        "<div style='margin: 8px 0; text-align: center; color: #888888; font-size: 11px; font-style: italic;'>"
        "  %1"
        "</div>"
    ).arg(text.toHtmlEscaped());
    transcript_->append(html);
}

void ChatPage::clearTranscript() {
    transcript_->clear();
    currentAssistantReply_.clear();
    isStreaming_ = false;
}

void ChatPage::setFollowupSuggestions(const QStringList& suggestions) {
    QLayoutItem* item = nullptr;
    while ((item = suggestionsLayout_->takeAt(0)) != nullptr) {
        delete item->widget();
        delete item;
    }

    for (const auto& s : suggestions) {
        auto* chip = new QPushButton(s, suggestionsContainer_);
        chip->setStyleSheet(QStringLiteral(
            "QPushButton {"
            "    background-color: #252526;"
            "    border: 1px solid #3c3c3c;"
            "    border-radius: 12px;"
            "    padding: 4px 10px;"
            "    font-size: 11px;"
            "    color: #79c0ff;"
            "}"
            "QPushButton:hover {"
            "    background-color: #0078d4;"
            "    color: #ffffff;"
            "}"
        ));
        connect(chip, &QPushButton::clicked, this, [this, s]() {
            promptInput_->setPlainText(s);
            onSendClicked();
        });
        suggestionsLayout_->addWidget(chip);
    }
}

void ChatPage::onSendClicked() {
    const QString text = promptInput_->toPlainText().trimmed();
    if (text.isEmpty() && currentAttachments_.isEmpty()) return;

    QStringList attach = currentAttachments_;
    currentAttachments_.clear();
    QLayoutItem* it = nullptr;
    while ((it = attachmentsLayout_->takeAt(0)) != nullptr) {
        delete it->widget();
        delete it;
    }

    promptInput_->clear();
    emit sendRequested(text, attach);
}

void ChatPage::onAttachClicked() {
    const QStringList files = QFileDialog::getOpenFileNames(this, QStringLiteral("Select Files to Attach"));
    for (const auto& file : files) {
        addAttachment(file);
    }
}

QString ChatPage::currentPrompt() const {
    return promptInput_->toPlainText();
}

void ChatPage::clearPrompt() {
    promptInput_->clear();
}

void ChatPage::setRunning(bool running) {
    sendButton_->setVisible(!running);
    stopButton_->setVisible(running);
    promptInput_->setEnabled(!running);
    attachButton_->setEnabled(!running);
}

}  // namespace aquila::gui
