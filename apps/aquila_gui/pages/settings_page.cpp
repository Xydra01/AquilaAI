// apps/aquila_gui/pages/settings_page.cpp
#include "settings_page.hpp"

#include <QFileDialog>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QScrollArea>

namespace aquila::gui {

SettingsPage::SettingsPage(QWidget* parent)
    : BasePage(QStringLiteral("Settings"),
               QStringLiteral("Engine, Hardware Tier, Inference, and Appearance Preferences"),
               QStringLiteral("⚙️"), parent) {
    auto* scrollArea = new QScrollArea(this);
    scrollArea->setWidgetResizable(true);
    scrollArea->setFrameShape(QFrame::NoFrame);

    auto* container = new QWidget(scrollArea);
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(16);

    // Group 1: LLM Inference Backend
    auto* backendGroup = new QGroupBox(QStringLiteral("Inference Engine & Model"), container);
    auto* backendForm = new QFormLayout(backendGroup);
    backendForm->setSpacing(10);

    backendCombo_ = new QComboBox(backendGroup);
    backendCombo_->addItems({QStringLiteral("Ollama (HTTP localhost:11434)"), QStringLiteral("Llama.cpp (Direct C++ In-Process)")});
    backendForm->addRow(QStringLiteral("Backend:"), backendCombo_);

    hostInput_ = new QLineEdit(QStringLiteral("http://127.0.0.1:11434"), backendGroup);
    backendForm->addRow(QStringLiteral("Ollama Host:"), hostInput_);

    modelInput_ = new QLineEdit(QStringLiteral("aquila"), backendGroup);
    modelInput_->setPlaceholderText(QStringLiteral("Model tag or path to .gguf file"));
    backendForm->addRow(QStringLiteral("Model / Weights:"), modelInput_);

    layout->addWidget(backendGroup);

    // Group 2: Hardware Tier & Optimization
    auto* tierGroup = new QGroupBox(QStringLiteral("Hardware Tier & Context Budget (R16)"), container);
    auto* tierForm = new QFormLayout(tierGroup);
    tierForm->setSpacing(10);

    tierCombo_ = new QComboBox(tierGroup);
    tierCombo_->addItems({
        QStringLiteral("CPU Base (8GB RAM tier, tight 2048 token window)"),
        QStringLiteral("GPU Boost (RTX 4070 VRAM offload, 8192 token window)")
    });
    tierForm->addRow(QStringLiteral("Compute Profile:"), tierCombo_);

    contextSpin_ = new QSpinBox(tierGroup);
    contextSpin_->setRange(512, 131072);
    contextSpin_->setValue(2048);
    contextSpin_->setSingleStep(512);
    tierForm->addRow(QStringLiteral("Context Window:"), contextSpin_);

    tempSpin_ = new QDoubleSpinBox(tierGroup);
    tempSpin_->setRange(0.0, 1.5);
    tempSpin_->setValue(0.2);
    tempSpin_->setSingleStep(0.05);
    tierForm->addRow(QStringLiteral("Temperature:"), tempSpin_);

    gbnfCheck_ = new QCheckBox(QStringLiteral("Enforce GBNF action grammar on tool outputs (R14)"), tierGroup);
    gbnfCheck_->setChecked(true);
    tierForm->addRow(gbnfCheck_);

    kvRollbackCheck_ = new QCheckBox(QStringLiteral("Enable Single-Action-per-Context (SAC) context condenser"), tierGroup);
    kvRollbackCheck_->setChecked(true);
    tierForm->addRow(kvRollbackCheck_);

    ngramCheck_ = new QCheckBox(QStringLiteral("Speculative N-Gram prompt lookup acceleration"), tierGroup);
    ngramCheck_->setChecked(true);
    tierForm->addRow(ngramCheck_);

    layout->addWidget(tierGroup);

    // Group 3: Workspace & Appearance
    auto* appGroup = new QGroupBox(QStringLiteral("Workspace & Appearance"), container);
    auto* appForm = new QFormLayout(appGroup);
    appForm->setSpacing(10);

    auto* wsRow = new QHBoxLayout();
    workspaceInput_ = new QLineEdit(QStringLiteral("."), appGroup);
    wsRow->addWidget(workspaceInput_, 1);
    browseWsBtn_ = new QPushButton(QStringLiteral("Browse..."), appGroup);
    connect(browseWsBtn_, &QPushButton::clicked, this, &SettingsPage::onBrowseWorkspace);
    wsRow->addWidget(browseWsBtn_);
    appForm->addRow(QStringLiteral("Workspace Path:"), wsRow);

    themeCombo_ = new QComboBox(appGroup);
    themeCombo_->addItems({QStringLiteral("Dark Theme (Fluent Windows 11)"), QStringLiteral("Light Theme")});
    connect(themeCombo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &SettingsPage::onThemeComboChanged);
    appForm->addRow(QStringLiteral("Theme:"), themeCombo_);

    layout->addWidget(appGroup);

    // Save Button
    saveBtn_ = new QPushButton(QStringLiteral("✓ Save & Apply Settings"), container);
    saveBtn_->setProperty("accent", true);
    saveBtn_->setFixedHeight(36);
    connect(saveBtn_, &QPushButton::clicked, this, &SettingsPage::onSaveClicked);
    layout->addWidget(saveBtn_);

    layout->addStretch(1);

    scrollArea->setWidget(container);
    contentLayout()->addWidget(scrollArea);
}

void SettingsPage::onBrowseWorkspace() {
    const QString dir = QFileDialog::getExistingDirectory(this, QStringLiteral("Select Workspace Directory"));
    if (!dir.isEmpty()) {
        workspaceInput_->setText(dir);
    }
}

void SettingsPage::onSaveClicked() {
    setStatus(QStringLiteral("Settings saved successfully."));
    emit settingsApplied();
}

void SettingsPage::onThemeComboChanged(int index) {
    emit themeChanged(index == 0);
}

QString SettingsPage::backendType() const {
    return backendCombo_->currentIndex() == 0 ? QStringLiteral("ollama") : QStringLiteral("llama");
}

QString SettingsPage::ollamaHost() const {
    return hostInput_->text();
}

QString SettingsPage::modelName() const {
    return modelInput_->text();
}

QString SettingsPage::computeTier() const {
    return tierCombo_->currentIndex() == 0 ? QStringLiteral("cpu") : QStringLiteral("gpu");
}

int SettingsPage::contextWindow() const {
    return contextSpin_->value();
}

double SettingsPage::temperature() const {
    return tempSpin_->value();
}

QString SettingsPage::workspacePath() const {
    return workspaceInput_->text();
}

}  // namespace aquila::gui
