// apps/aquila_gui/pages/home_page.hpp
#pragma once

#include "base_page.hpp"
#include <QPushButton>

namespace aquila::gui {

class HomePage : public BasePage {
    Q_OBJECT
public:
    explicit HomePage(QWidget* parent = nullptr);

    void setSystemSpecs(const QString& specsText);
    void setWorkspacePath(const QString& path);

signals:
    void modeRequested(int modeIndex);
    void newChatRequested();
    void openWorkspaceRequested();

private:
    QWidget* createModeTile(const QString& icon, const QString& title, const QString& description, int modeIndex);

    QLabel* workspaceLabel_ = nullptr;
    QLabel* specsLabel_ = nullptr;
};

}  // namespace aquila::gui

