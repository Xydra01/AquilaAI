// apps/aquila_gui/widgets/nav_rail.hpp
#pragma once

#include <QPushButton>
#include <QVBoxLayout>
#include <QWidget>
#include <vector>

namespace aquila::gui {

class NavRailWidget : public QWidget {
    Q_OBJECT
public:
    explicit NavRailWidget(QWidget* parent = nullptr);

    void setCurrentMode(int index);
    int currentMode() const;

signals:
    void modeChanged(int index);
    void themeToggleRequested();
    void sleepRequested();
    void settingsRequested();

private:
    void onModeButtonClicked(int index);
    QPushButton* createNavButton(const QString& icon, const QString& label, int index);

    int currentIndex_ = 0;
    std::vector<QPushButton*> modeButtons_;
    QPushButton* themeButton_ = nullptr;
    QPushButton* sleepButton_ = nullptr;
    QPushButton* settingsButton_ = nullptr;
};

}  // namespace aquila::gui

