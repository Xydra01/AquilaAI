// apps/aquila_gui/widgets/inline_prompt_bar.cpp
#include "inline_prompt_bar.hpp"

namespace aquila::gui {

InlinePromptBar::InlinePromptBar(QWidget* parent) : QFrame(parent) {
    setObjectName(QStringLiteral("inlinePromptBar"));
    setStyleSheet(QStringLiteral(
        "QFrame#inlinePromptBar {"
        "  background-color: #252526;"
        "  border: 1px solid #007acc;"
        "  border-radius: 6px;"
        "  padding: 4px;"
        "}"
        "QLineEdit {"
        "  background-color: #1e1e1e;"
        "  color: #cccccc;"
        "  border: 1px solid #3c3c3c;"
        "  border-radius: 4px;"
        "  padding: 4px 8px;"
        "  font-size: 13px;"
        "}"
        "QLineEdit:focus {"
        "  border: 1px solid #007acc;"
        "}"
        "QPushButton {"
        "  border-radius: 4px;"
        "  padding: 4px 10px;"
        "  font-size: 12px;"
        "  font-weight: bold;"
        "}"
        "QPushButton#submitBtn {"
        "  background-color: #007acc;"
        "  color: #ffffff;"
        "  border: none;"
        "}"
        "QPushButton#submitBtn:hover {"
        "  background-color: #0098ff;"
        "}"
        "QPushButton#cancelBtn {"
        "  background-color: #333333;"
        "  color: #cccccc;"
        "  border: 1px solid #444444;"
        "}"
        "QPushButton#cancelBtn:hover {"
        "  background-color: #444444;"
        "}"
    ));

    auto* layout = new QHBoxLayout(this);
    layout->setContentsMargins(6, 4, 6, 4);
    layout->setSpacing(8);

    iconLabel_ = new QLabel(QStringLiteral("✨"), this);
    iconLabel_->setStyleSheet(QStringLiteral("font-size: 16px; background: transparent;"));
    layout->addWidget(iconLabel_);

    promptInput_ = new QLineEdit(this);
    promptInput_->setPlaceholderText(QStringLiteral("Ask Aquila to edit selection... (Enter to submit, Esc to cancel)"));
    layout->addWidget(promptInput_, 1);

    submitButton_ = new QPushButton(QStringLiteral("Edit"), this);
    submitButton_->setObjectName(QStringLiteral("submitBtn"));
    layout->addWidget(submitButton_);

    cancelButton_ = new QPushButton(QStringLiteral("Cancel"), this);
    cancelButton_->setObjectName(QStringLiteral("cancelBtn"));
    layout->addWidget(cancelButton_);

    connect(submitButton_, &QPushButton::clicked, this, &InlinePromptBar::onSubmitClicked);
    connect(cancelButton_, &QPushButton::clicked, this, &InlinePromptBar::onCancelClicked);
    connect(promptInput_, &QLineEdit::returnPressed, this, &InlinePromptBar::onSubmitClicked);
}

void InlinePromptBar::setPromptText(const QString& text) {
    promptInput_->setText(text);
}

QString InlinePromptBar::promptText() const {
    return promptInput_->text();
}

void InlinePromptBar::focusInput() {
    promptInput_->setFocus();
    promptInput_->selectAll();
}

void InlinePromptBar::clearInput() {
    promptInput_->clear();
}

void InlinePromptBar::keyPressEvent(QKeyEvent* event) {
    if (event->key() == Qt::Key_Escape) {
        onCancelClicked();
        event->accept();
    } else {
        QFrame::keyPressEvent(event);
    }
}

void InlinePromptBar::onSubmitClicked() {
    const QString text = promptInput_->text().trimmed();
    if (!text.isEmpty()) {
        emit submitRequested(text);
    }
}

void InlinePromptBar::onCancelClicked() {
    emit cancelRequested();
}

}  // namespace aquila::gui
