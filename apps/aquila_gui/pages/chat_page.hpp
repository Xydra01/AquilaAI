// apps/aquila_gui/pages/chat_page.hpp
#pragma once

#include "base_page.hpp"
#include "../widgets/flow_layout.hpp"

#include <QPlainTextEdit>
#include <QPushButton>
#include <QTextEdit>
#include <vector>

namespace aquila::gui {

class ChatPage : public BasePage {
    Q_OBJECT
public:
    explicit ChatPage(QWidget* parent = nullptr);

    void appendUserMessage(const QString& text);
    void appendAssistantMessage(const QString& text);
    void appendToken(const QString& token);
    void appendSystemMessage(const QString& text);
    void finalizeAssistantMessage();
    void clearTranscript();
    void setFollowupSuggestions(const QStringList& suggestions);

    QString currentPrompt() const;
    void clearPrompt();
    void setRunning(bool running);

signals:
    void sendRequested(const QString& prompt, const QStringList& attachments);
    void cancelRequested();

private:
    void onSendClicked();
    void onAttachClicked();

    QTextEdit* transcript_ = nullptr;
    QPlainTextEdit* promptInput_ = nullptr;
    QPushButton* sendButton_ = nullptr;
    QPushButton* attachButton_ = nullptr;
    QPushButton* stopButton_ = nullptr;
    QWidget* attachmentsContainer_ = nullptr;
    FlowLayout* attachmentsLayout_ = nullptr;
    QWidget* suggestionsContainer_ = nullptr;
    FlowLayout* suggestionsLayout_ = nullptr;

    QString currentAssistantReply_;
    bool isStreaming_ = false;
    QStringList currentAttachments_;
};

}  // namespace aquila::gui
