// apps/aquila_gui/dialogs/setup_wizard.cpp
#include "setup_wizard.hpp"

#include <QFileDialog>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>
#include <filesystem>

namespace aquila::gui {

SetupWizard::SetupWizard(QWidget* parent) : QWizard(parent) {
    setWindowTitle(QStringLiteral("Aquila AI - First Run Setup"));
    resize(580, 400);

    addPage(new IntroPage(this));
    addPage(new ModelDetectionPage(this));
    addPage(new WorkspacePage(this));
    addPage(new ConclusionPage(this));
}

QString SetupWizard::selectedWorkspace() const {
    return field(QStringLiteral("workspacePath")).toString();
}

QString SetupWizard::selectedModel() const {
    return field(QStringLiteral("modelName")).toString();
}

IntroPage::IntroPage(QWidget* parent) : QWizardPage(parent) {
    setTitle(QStringLiteral("Welcome to Aquila AI"));
    setSubTitle(QStringLiteral("High-Performance C++20 Autonomous Multi-Domain Agent"));

    auto* layout = new QVBoxLayout(this);
    auto* lbl = new QLabel(QStringLiteral(
        "This quick setup wizard will configure your local inference backend and working directory.\n\n"
        "• Rebuilt from the ground up in modern C++20\n"
        "• Single-threaded deterministic core with native zero-allocation pipelines\n"
        "• Value-managed Single-Action-per-Context (SAC) context condensation\n"
        "• Interactive Qt 6 desktop environment with Live Canvas authoring"
    ), this);
    lbl->setWordWrap(true);
    layout->addWidget(lbl);
}

ModelDetectionPage::ModelDetectionPage(QWidget* parent) : QWizardPage(parent) {
    setTitle(QStringLiteral("Inference Engine & Model"));
    setSubTitle(QStringLiteral("Configure local Qwen 3.5 weights (native GGUF or Ollama)"));

    auto* layout = new QVBoxLayout(this);
    QString detected = QStringLiteral("qwen3.5:4b");
    std::error_code ec;
    for (const char* p : {
             "F:/aquila-models/Qwen3.5-4B-Q4_K_M.gguf",
             "F:/aquila-models/Qwen3.5-9B-Q4_K_M.gguf",
             "F:/Users/myfri/agent-projects/Qwen3.5-4B-Q4_K_M.gguf",
             "F:/Users/myfri/agent-projects/Qwen3.5-9B-Q4_K_M.gguf",
             "D:/aquila-models/Qwen3.5-4B-Q4_K_M.gguf",
             "D:/aquila-models/Qwen3.5-9B-Q4_K_M.gguf",
         }) {
        if (std::filesystem::is_regular_file(p, ec)) {
            detected = QString::fromUtf8(p);
            break;
        }
    }

    auto* info = new QLabel(
        QStringLiteral("Recommended local models: Qwen3.5-4B (CPU 16K default) or Qwen3.5-9B (GPU 32K).\n"
                       "Enter GGUF file path or Ollama model tag:"),
        this);
    layout->addWidget(info);

    modelEdit_ = new QLineEdit(detected, this);
    registerField(QStringLiteral("modelName*"), modelEdit_);
    layout->addWidget(modelEdit_);
    layout->addStretch(1);
}

WorkspacePage::WorkspacePage(QWidget* parent) : QWizardPage(parent) {
    setTitle(QStringLiteral("Workspace Directory"));
    setSubTitle(QStringLiteral("Select the root directory for your code and document projects"));

    auto* layout = new QVBoxLayout(this);
    auto* row = new QHBoxLayout();

    wsEdit_ = new QLineEdit(QStringLiteral("."), this);
    registerField(QStringLiteral("workspacePath*"), wsEdit_);
    row->addWidget(wsEdit_, 1);

    auto* browse = new QPushButton(QStringLiteral("Browse..."), this);
    connect(browse, &QPushButton::clicked, this, [this]() {
        const QString dir = QFileDialog::getExistingDirectory(this, QStringLiteral("Select Workspace Root"));
        if (!dir.isEmpty()) {
            wsEdit_->setText(dir);
        }
    });
    row->addWidget(browse);

    layout->addLayout(row);
    layout->addStretch(1);
}

ConclusionPage::ConclusionPage(QWidget* parent) : QWizardPage(parent) {
    setTitle(QStringLiteral("Setup Complete"));
    setSubTitle(QStringLiteral("Aquila is configured and ready to launch"));

    auto* layout = new QVBoxLayout(this);
    auto* lbl = new QLabel(QStringLiteral("Click 'Finish' to launch the Aquila desktop shell."), this);
    layout->addWidget(lbl);
}

}  // namespace aquila::gui
