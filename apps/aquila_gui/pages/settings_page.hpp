// apps/aquila_gui/pages/settings_page.hpp
#pragma once

#include "base_page.hpp"

#include <QCheckBox>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QLineEdit>
#include <QPushButton>
#include <QSpinBox>

namespace aquila::gui {

class SettingsPage : public BasePage {
    Q_OBJECT
public:
    explicit SettingsPage(QWidget* parent = nullptr);

    QString backendType() const;
    QString ollamaHost() const;
    QString modelName() const;
    QString computeTier() const;
    int contextWindow() const;
    double temperature() const;
    QString workspacePath() const;

    void setModelName(const QString& name);
    void setWorkspacePath(const QString& path);

signals:
    void settingsApplied();
    void themeChanged(bool isDark);

private slots:
    void onBrowseWorkspace();
    void onBrowseModel();
    void onBackendComboChanged(int index);
    void onTierComboChanged(int index);
    void onSaveClicked();
    void onThemeComboChanged(int index);

private:
    QComboBox* backendCombo_ = nullptr;
    QLineEdit* hostInput_ = nullptr;
    QLineEdit* modelInput_ = nullptr;
    QPushButton* browseModelBtn_ = nullptr;
    QComboBox* tierCombo_ = nullptr;
    QSpinBox* contextSpin_ = nullptr;
    QDoubleSpinBox* tempSpin_ = nullptr;

    QCheckBox* gbnfCheck_ = nullptr;
    QCheckBox* kvRollbackCheck_ = nullptr;
    QCheckBox* ngramCheck_ = nullptr;

    QComboBox* themeCombo_ = nullptr;
    QLineEdit* workspaceInput_ = nullptr;
    QPushButton* browseWsBtn_ = nullptr;
    QPushButton* saveBtn_ = nullptr;
};

}  // namespace aquila::gui
