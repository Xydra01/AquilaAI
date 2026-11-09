// apps/aquila_gui/pages/settings_page.cpp
#include "settings_page.hpp"

#include <filesystem>
#include <QFileDialog>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QScrollArea>
#include <QSettings>

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
    connect(backendCombo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &SettingsPage::onBackendComboChanged);
    backendForm->addRow(QStringLiteral("Backend:"), backendCombo_);

    hostInput_ = new QLineEdit(QStringLiteral("http://127.0.0.1:11434"), backendGroup);
    backendForm->addRow(QStringLiteral("Ollama Host:"), hostInput_);

    auto* modelRow = new QHBoxLayout();
    modelInput_ = new QLineEdit(QStringLiteral("aquila"), backendGroup);
    modelInput_->setPlaceholderText(QStringLiteral("Model tag or path to .gguf file"));
    modelRow->addWidget(modelInput_, 1);
    browseModelBtn_ = new QPushButton(QStringLiteral("Browse..."), backendGroup);
    connect(browseModelBtn_, &QPushButton::clicked, this, &SettingsPage::onBrowseModel);
    modelRow->addWidget(browseModelBtn_);
    backendForm->addRow(QStringLiteral("Model / Weights:"), modelRow);

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
    connect(tierCombo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &SettingsPage::onTierComboChanged);
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

    // Group 4: Web Search & Knowledge Ingestion Settings
    auto* searchGroup = new QGroupBox(QStringLiteral("Web Search & Knowledge Ingestion Settings"), container);
    auto* searchForm = new QFormLayout(searchGroup);

    searchProviderCombo_ = new QComboBox(searchGroup);
    searchProviderCombo_->addItems({
        QStringLiteral("DuckDuckGo Lite (Free / Zero Docker / Built-in)"),
        QStringLiteral("Local SearXNG (http://127.0.0.1:8888)"),
        QStringLiteral("Wikipedia OpenSearch")
    });
    searchForm->addRow(QStringLiteral("Default Search Engine:"), searchProviderCombo_);

    searxngEndpointInput_ = new QLineEdit(searchGroup);
    searxngEndpointInput_->setText(QStringLiteral("http://127.0.0.1:8888"));
    searchForm->addRow(QStringLiteral("SearXNG Endpoint:"), searxngEndpointInput_);

    autoScrapeCheck_ = new QCheckBox(QStringLiteral("Auto-scrape and extract clean text from top-ranked authoritative pages"), searchGroup);
    autoScrapeCheck_->setChecked(true);
    searchForm->addRow(QStringLiteral("Smart Scraping:"), autoScrapeCheck_);

    layout->addWidget(searchGroup);

    // Save Button
    saveBtn_ = new QPushButton(QStringLiteral("✓ Save & Apply Settings"), container);
    saveBtn_->setProperty("accent", true);
    saveBtn_->setFixedHeight(36);
    connect(saveBtn_, &QPushButton::clicked, this, &SettingsPage::onSaveClicked);
    layout->addWidget(saveBtn_);

    layout->addStretch(1);

    scrollArea->setWidget(container);
    contentLayout()->addWidget(scrollArea);

    loadSettings();
}

void SettingsPage::onBrowseWorkspace() {
    const QString dir = QFileDialog::getExistingDirectory(this, QStringLiteral("Select Workspace Directory"));
    if (!dir.isEmpty()) {
        workspaceInput_->setText(dir);
    }
}

void SettingsPage::onBrowseModel() {
    const QString file = QFileDialog::getOpenFileName(
        this, QStringLiteral("Select Model Weights (.gguf)"),
        QStringLiteral("D:/aquila-models"),
        QStringLiteral("GGUF Model Files (*.gguf);;All Files (*.*)"));
    if (!file.isEmpty()) {
        modelInput_->setText(file);
    }
}

void SettingsPage::onBackendComboChanged(int index) {
    const bool isLlama = (index == 1);
    hostInput_->setEnabled(!isLlama);
    if (isLlama) {
        const QString cur = modelInput_->text().trimmed();
        if (cur.isEmpty() || cur == QStringLiteral("aquila")) {
            if (computeTier() == QStringLiteral("gpu") &&
                std::filesystem::exists("D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")) {
                modelInput_->setText(QStringLiteral("D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"));
            } else if (std::filesystem::exists("D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf")) {
                modelInput_->setText(QStringLiteral("D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"));
            }
        }
    }
}

void SettingsPage::onTierComboChanged(int index) {
    if (index == 1) { // GPU
        contextSpin_->setValue(8192);
        if (backendCombo_->currentIndex() == 1 &&
            std::filesystem::exists("D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")) {
            modelInput_->setText(QStringLiteral("D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"));
        }
    } else { // CPU
        contextSpin_->setValue(2048);
        if (backendCombo_->currentIndex() == 1 &&
            std::filesystem::exists("D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf")) {
            modelInput_->setText(QStringLiteral("D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"));
        }
    }
}

void SettingsPage::saveSettings() {
    QSettings s(QStringLiteral("Aquila"), QStringLiteral("AquilaGui"));
    s.setValue(QStringLiteral("backendIndex"), backendCombo_->currentIndex());
    s.setValue(QStringLiteral("ollamaHost"), hostInput_->text());
    s.setValue(QStringLiteral("modelPath"), modelInput_->text());
    s.setValue(QStringLiteral("tierIndex"), tierCombo_->currentIndex());
    s.setValue(QStringLiteral("contextWindow"), contextSpin_->value());
    s.setValue(QStringLiteral("temperature"), tempSpin_->value());
    s.setValue(QStringLiteral("gbnf"), gbnfCheck_->isChecked());
    s.setValue(QStringLiteral("kvRollback"), kvRollbackCheck_->isChecked());
    s.setValue(QStringLiteral("ngram"), ngramCheck_->isChecked());
    s.setValue(QStringLiteral("workspacePath"), workspaceInput_->text());
    s.setValue(QStringLiteral("themeIndex"), themeCombo_->currentIndex());
    s.setValue(QStringLiteral("searchProviderIndex"), searchProviderCombo_->currentIndex());
    s.setValue(QStringLiteral("searxngEndpoint"), searxngEndpointInput_->text());
    s.setValue(QStringLiteral("autoScrape"), autoScrapeCheck_->isChecked());
    s.sync();
}

void SettingsPage::loadSettings() {
    QSignalBlocker bBlock(backendCombo_);
    QSignalBlocker tBlock(tierCombo_);
    QSignalBlocker thBlock(themeCombo_);
    QSignalBlocker spBlock(searchProviderCombo_);

    QSettings s(QStringLiteral("Aquila"), QStringLiteral("AquilaGui"));
    if (s.contains(QStringLiteral("backendIndex"))) {
        backendCombo_->setCurrentIndex(s.value(QStringLiteral("backendIndex"), 0).toInt());
        hostInput_->setText(s.value(QStringLiteral("ollamaHost"), QStringLiteral("http://127.0.0.1:11434")).toString());
        modelInput_->setText(s.value(QStringLiteral("modelPath")).toString());
        tierCombo_->setCurrentIndex(s.value(QStringLiteral("tierIndex"), 0).toInt());
        contextSpin_->setValue(s.value(QStringLiteral("contextWindow"), 2048).toInt());
        tempSpin_->setValue(s.value(QStringLiteral("temperature"), 0.2).toDouble());
        gbnfCheck_->setChecked(s.value(QStringLiteral("gbnf"), true).toBool());
        kvRollbackCheck_->setChecked(s.value(QStringLiteral("kvRollback"), true).toBool());
        ngramCheck_->setChecked(s.value(QStringLiteral("ngram"), true).toBool());
        workspaceInput_->setText(s.value(QStringLiteral("workspacePath"), QStringLiteral(".")).toString());
        themeCombo_->setCurrentIndex(s.value(QStringLiteral("themeIndex"), 0).toInt());
        searchProviderCombo_->setCurrentIndex(s.value(QStringLiteral("searchProviderIndex"), 0).toInt());
        searxngEndpointInput_->setText(s.value(QStringLiteral("searxngEndpoint"), QStringLiteral("http://127.0.0.1:8888")).toString());
        autoScrapeCheck_->setChecked(s.value(QStringLiteral("autoScrape"), true).toBool());
    } else {
        // Auto-detect optimal hardware profile on initial run
        if (std::filesystem::exists("D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")) {
            backendCombo_->setCurrentIndex(1); // Llama.cpp (Direct C++ in-process)
            tierCombo_->setCurrentIndex(1);    // GPU Boost (RTX 4070 VRAM offload)
            modelInput_->setText(QStringLiteral("D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"));
            contextSpin_->setValue(8192);
            saveSettings();
        } else if (std::filesystem::exists("D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf")) {
            backendCombo_->setCurrentIndex(1); // Llama.cpp
            tierCombo_->setCurrentIndex(0);    // CPU Base
            modelInput_->setText(QStringLiteral("D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"));
            contextSpin_->setValue(2048);
            saveSettings();
        }
    }
    hostInput_->setEnabled(backendCombo_->currentIndex() == 0);
}

void SettingsPage::onSaveClicked() {
    saveSettings();
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

QString SettingsPage::searchProvider() const {
    if (searchProviderCombo_->currentIndex() == 1) return QStringLiteral("searxng");
    if (searchProviderCombo_->currentIndex() == 2) return QStringLiteral("wikipedia");
    return QStringLiteral("duckduckgo");
}

QString SettingsPage::searxngEndpoint() const {
    return searxngEndpointInput_->text().trimmed();
}

bool SettingsPage::autoScrapeEnabled() const {
    return autoScrapeCheck_->isChecked();
}

void SettingsPage::setModelName(const QString& name) {
    modelInput_->setText(name);
}

void SettingsPage::setWorkspacePath(const QString& path) {
    workspaceInput_->setText(path);
}

}  // namespace aquila::gui
