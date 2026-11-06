// apps/aquila_gui/dialogs/setup_wizard.cpp
#include "setup_wizard.hpp"

#include <QFileDialog>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

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
    setSubTitle(QStringLiteral("Configure local model weights (Ollama or native GGUF)"));

    auto* layout = new QVBoxLayout(this);
    auto* info = new QLabel(QStringLiteral("Detected local Ollama instance at http://127.0.0.1:11434.\nEnter model tag or GGUF path:"), this);
    layout->addWidget(info);

    modelEdit_ = new QLineEdit(QStringLiteral("aquila"), this);
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
