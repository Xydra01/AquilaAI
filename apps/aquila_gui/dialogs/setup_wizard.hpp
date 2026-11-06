// apps/aquila_gui/dialogs/setup_wizard.hpp
#pragma once

#include <QLineEdit>
#include <QWizard>

namespace aquila::gui {

class SetupWizard : public QWizard {
    Q_OBJECT
public:
    explicit SetupWizard(QWidget* parent = nullptr);

    QString selectedWorkspace() const;
    QString selectedModel() const;
};

class IntroPage : public QWizardPage {
    Q_OBJECT
public:
    explicit IntroPage(QWidget* parent = nullptr);
};

class ModelDetectionPage : public QWizardPage {
    Q_OBJECT
public:
    explicit ModelDetectionPage(QWidget* parent = nullptr);

    QLineEdit* modelEdit() const { return modelEdit_; }

private:
    QLineEdit* modelEdit_ = nullptr;
};

class WorkspacePage : public QWizardPage {
    Q_OBJECT
public:
    explicit WorkspacePage(QWidget* parent = nullptr);

    QLineEdit* workspaceEdit() const { return wsEdit_; }

private:
    QLineEdit* wsEdit_ = nullptr;
};

class ConclusionPage : public QWizardPage {
    Q_OBJECT
public:
    explicit ConclusionPage(QWidget* parent = nullptr);
};

}  // namespace aquila::gui
