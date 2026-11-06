// apps/aquila_gui/pages/character_page.hpp
#pragma once

#include "base_page.hpp"

#include <QComboBox>
#include <QLabel>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QSplitter>
#include <QTextEdit>
#include <QTreeWidget>

namespace aquila::gui {

class CharacterPage : public BasePage {
    Q_OBJECT
public:
    explicit CharacterPage(QWidget* parent = nullptr);

    void setPersonaList(const QStringList& personas);
    void setInitializationBible(const QString& text);
    QString initializationBible() const;

signals:
    void personaSelected(const QString& personaId);
    void savePersonaRequested(const QString& personaId, const QString& bibleText);
    void chatMessageSent(const QString& personaId, const QString& message);

private slots:
    void onBibleTextChanged();
    void onSaveClicked();
    void onSendChatClicked();

private:
    QComboBox* personaCombo_ = nullptr;
    QPushButton* newPersonaBtn_ = nullptr;
    QPushButton* savePersonaBtn_ = nullptr;

    QPlainTextEdit* bibleEditor_ = nullptr;
    QProgressBar* charCountBar_ = nullptr;
    QLabel* charCountLabel_ = nullptr;

    QTreeWidget* traitsTree_ = nullptr;
    QTextEdit* dialogueTranscript_ = nullptr;
    QPlainTextEdit* dialogueInput_ = nullptr;
    QPushButton* sendChatBtn_ = nullptr;
};

}  // namespace aquila::gui
