// apps/aquila_gui/pages/character_page.cpp
#include "character_page.hpp"
#include "../theme/markdown_renderer.hpp"

#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QInputDialog>
#include <QMessageBox>

namespace aquila::gui {

CharacterPage::CharacterPage(QWidget* parent)
    : BasePage(QStringLiteral("Character AI"),
               QStringLiteral("Immersive Roleplay, Persona Lore, and Strict 800+ Character Initialization Gate"),
               QStringLiteral("👤"), parent) {
    auto* layout = contentLayout();

    // Top Persona Bar
    auto* topBar = new QHBoxLayout();
    topBar->setSpacing(8);

    auto* lblPersona = new QLabel(QStringLiteral("Active Persona:"), this);
    lblPersona->setStyleSheet(QStringLiteral("font-weight:bold;"));
    topBar->addWidget(lblPersona);

    personaCombo_ = new QComboBox(this);
    personaCombo_->setMinimumWidth(200);
    connect(personaCombo_, &QComboBox::currentTextChanged, this, &CharacterPage::personaSelected);
    topBar->addWidget(personaCombo_);

    newPersonaBtn_ = new QPushButton(QStringLiteral("+ New Persona"), this);
    connect(newPersonaBtn_, &QPushButton::clicked, this, [this]() {
        bool ok = false;
        QString name = QInputDialog::getText(this, QStringLiteral("New Persona"),
                                             QStringLiteral("Enter persona name or ID:"),
                                             QLineEdit::Normal, QStringLiteral("mentor_elena"), &ok);
        if (ok && !name.trimmed().isEmpty()) {
            personaCombo_->addItem(name.trimmed());
            personaCombo_->setCurrentText(name.trimmed());
        }
    });
    topBar->addWidget(newPersonaBtn_);

    savePersonaBtn_ = new QPushButton(QStringLiteral("💾 Save Persona"), this);
    savePersonaBtn_->setProperty("accent", true);
    connect(savePersonaBtn_, &QPushButton::clicked, this, &CharacterPage::onSaveClicked);
    topBar->addWidget(savePersonaBtn_);
    topBar->addStretch(1);

    layout->addLayout(topBar);

    // Splitter: Left = Persona Bible & Quality Gate, Right = Roleplay Dialogue
    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Left: Initialization Bible
    auto* bibleGroup = new QGroupBox(QStringLiteral("Persona Bible (Initialization Profile)"), splitter);
    auto* bibleLayout = new QVBoxLayout(bibleGroup);
    bibleLayout->setContentsMargins(6, 10, 6, 6);

    // 800-char Quality Gate Progress Bar
    auto* gateHeader = new QHBoxLayout();
    charCountLabel_ = new QLabel(QStringLiteral("Length: 0 / 800 characters (Quality Gate: ≥ 800)"), bibleGroup);
    charCountLabel_->setStyleSheet(QStringLiteral("font-size: 11px; color: #f85149; font-weight:bold;"));
    gateHeader->addWidget(charCountLabel_);
    gateHeader->addStretch(1);
    bibleLayout->addLayout(gateHeader);

    charCountBar_ = new QProgressBar(bibleGroup);
    charCountBar_->setRange(0, 800);
    charCountBar_->setValue(0);
    charCountBar_->setFixedHeight(8);
    charCountBar_->setTextVisible(false);
    charCountBar_->setStyleSheet(QStringLiteral(
        "QProgressBar { background-color: #2d2d30; border: none; border-radius: 4px; }"
        "QProgressBar::chunk { background-color: #f85149; border-radius: 4px; }"
    ));
    bibleLayout->addWidget(charCountBar_);

    bibleEditor_ = new QPlainTextEdit(bibleGroup);
    bibleEditor_->setFont(QFont(QStringLiteral("Segoe UI"), 10));
    bibleEditor_->setPlaceholderText(QStringLiteral("Write detailed character background, tone of voice, goals, and behavioral constraints (must be at least 800 characters before finalization)..."));
    connect(bibleEditor_, &QPlainTextEdit::textChanged, this, &CharacterPage::onBibleTextChanged);
    bibleLayout->addWidget(bibleEditor_, 1);

    // Traits Table
    traitsTree_ = new QTreeWidget(bibleGroup);
    traitsTree_->setColumnCount(2);
    traitsTree_->setHeaderLabels({QStringLiteral("Trait / Dimension"), QStringLiteral("Setting")});
    traitsTree_->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    traitsTree_->header()->setSectionResizeMode(1, QHeaderView::Stretch);
    traitsTree_->setMaximumHeight(100);

    auto* t1 = new QTreeWidgetItem(traitsTree_, {QStringLiteral("Tone"), QStringLiteral("Empathetic, analytical, calm")});
    auto* t2 = new QTreeWidgetItem(traitsTree_, {QStringLiteral("Domain"), QStringLiteral("Systems Architecture, C++")});
    traitsTree_->addTopLevelItems({t1, t2});
    bibleLayout->addWidget(traitsTree_);

    splitter->addWidget(bibleGroup);

    // Right: Roleplay Dialogue
    auto* dialogGroup = new QGroupBox(QStringLiteral("Interactive Character Dialogue"), splitter);
    auto* dialogLayout = new QVBoxLayout(dialogGroup);
    dialogLayout->setContentsMargins(6, 10, 6, 6);

    dialogueTranscript_ = new QTextEdit(dialogGroup);
    dialogueTranscript_->setReadOnly(true);
    dialogueTranscript_->setStyleSheet(QStringLiteral(
        "background-color: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 6px; padding: 10px;"
    ));
    dialogLayout->addWidget(dialogueTranscript_, 1);

    auto* inputRow = new QHBoxLayout();
    dialogueInput_ = new QPlainTextEdit(dialogGroup);
    dialogueInput_->setPlaceholderText(QStringLiteral("Talk with character..."));
    dialogueInput_->setMaximumHeight(60);
    inputRow->addWidget(dialogueInput_, 1);

    sendChatBtn_ = new QPushButton(QStringLiteral("Chat"), dialogGroup);
    sendChatBtn_->setProperty("accent", true);
    sendChatBtn_->setFixedSize(60, 40);
    connect(sendChatBtn_, &QPushButton::clicked, this, &CharacterPage::onSendChatClicked);
    inputRow->addWidget(sendChatBtn_);

    dialogLayout->addLayout(inputRow);
    splitter->addWidget(dialogGroup);

    splitter->setSizes({500, 500});
    layout->addWidget(splitter, 1);

    setPersonaList({QStringLiteral("mentor_elena"), QStringLiteral("senior_architect_marcus")});
}

void CharacterPage::setPersonaList(const QStringList& personas) {
    personaCombo_->clear();
    for (const auto& p : personas) {
        personaCombo_->addItem(p);
    }
}

void CharacterPage::setInitializationBible(const QString& text) {
    bibleEditor_->setPlainText(text);
    onBibleTextChanged();
}

QString CharacterPage::initializationBible() const {
    return bibleEditor_->toPlainText();
}

void CharacterPage::appendCharacterReply(const QString& personaId, const QString& reply) {
    const QString formattedHtml = MarkdownRenderer::toHtml(reply);
    dialogueTranscript_->append(QStringLiteral(
        "<div style='text-align:left; margin:6px 0;'>"
        "  <div style='background-color:#252526; color:#e0e0e0; border:1px solid #3c3c3c; border-radius:10px; padding:8px 12px; display:inline-block; max-width:85%%;'>"
        "    <div style='font-size:11px; font-weight:bold; color:#79c0ff; margin-bottom:4px;'>👤 %1</div>"
        "    <div>%2</div>"
        "  </div>"
        "</div>"
    ).arg(personaId.toHtmlEscaped(), formattedHtml));
}

void CharacterPage::onBibleTextChanged() {
    const int len = bibleEditor_->toPlainText().length();
    charCountBar_->setValue(std::min(len, 800));

    if (len >= 800) {
        charCountLabel_->setText(QStringLiteral("Length: %1 / 800 characters (✓ Quality Gate Passed)").arg(len));
        charCountLabel_->setStyleSheet(QStringLiteral("font-size: 11px; color: #7ee787; font-weight:bold;"));
        charCountBar_->setStyleSheet(QStringLiteral(
            "QProgressBar { background-color: #2d2d30; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background-color: #2ea043; border-radius: 4px; }"
        ));
    } else {
        charCountLabel_->setText(QStringLiteral("Length: %1 / 800 characters (Need %2 more characters)").arg(len).arg(800 - len));
        charCountLabel_->setStyleSheet(QStringLiteral("font-size: 11px; color: #f85149; font-weight:bold;"));
        charCountBar_->setStyleSheet(QStringLiteral(
            "QProgressBar { background-color: #2d2d30; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background-color: #f85149; border-radius: 4px; }"
        ));
    }
}

void CharacterPage::onSaveClicked() {
    const QString text = bibleEditor_->toPlainText();
    const QString pid = personaCombo_->currentText();
    if (text.length() < 800) {
        QMessageBox::warning(this, QStringLiteral("Quality Gate Refusal"),
                             QStringLiteral("Persona initialization must be at least 800 characters long (currently %1 chars). Please add more background lore and personality detail.").arg(text.length()));
        return;
    }
    setStatus(QStringLiteral("Saving persona '%1'...").arg(pid));
    emit savePersonaRequested(pid, text);
}

void CharacterPage::onSendChatClicked() {
    const QString msg = dialogueInput_->toPlainText().trimmed();
    if (msg.isEmpty()) return;

    dialogueTranscript_->append(QStringLiteral(
        "<div style='text-align:right; margin:6px 0;'><span style='background-color:#0078d4; color:#ffffff; padding:6px 12px; border-radius:10px;'>%1</span></div>"
    ).arg(msg.toHtmlEscaped()));

    dialogueInput_->clear();
    emit chatMessageSent(personaCombo_->currentText(), msg);
}

}  // namespace aquila::gui

