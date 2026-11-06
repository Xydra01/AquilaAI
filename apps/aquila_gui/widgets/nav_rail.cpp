// apps/aquila_gui/widgets/nav_rail.cpp
#include "nav_rail.hpp"

#include <QFrame>
#include <QLabel>
#include <QStyle>

namespace aquila::gui {

NavRailWidget::NavRailWidget(QWidget* parent) : QWidget(parent) {
    setObjectName(QStringLiteral("navRail"));
    setFixedWidth(72);

    auto* mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(6, 12, 6, 12);
    mainLayout->setSpacing(8);

    // App Logo / Title
    auto* logoLabel = new QLabel(QStringLiteral("🦅"), this);
    logoLabel->setAlignment(Qt::AlignCenter);
    logoLabel->setStyleSheet(QStringLiteral("font-size: 24px; padding: 4px;"));
    mainLayout->addWidget(logoLabel);

    auto* sep1 = new QFrame(this);
    sep1->setFrameShape(QFrame::HLine);
    sep1->setStyleSheet(QStringLiteral("color: #333333;"));
    mainLayout->addWidget(sep1);

    // Mode Buttons:
    // 0: Home, 1: Chat, 2: Task, 3: Code, 4: Writing, 5: Research, 6: Character, 7: Learn
    const struct {
        const char* icon;
        const char* label;
    } modes[] = {
        {"🏠", "Home"},
        {"💬", "Chat"},
        {"⚡", "Tasks"},
        {"💻", "Code"},
        {"📝", "Writing"},
        {"🔍", "Research"},
        {"👤", "Character"},
        {"🎓", "Learn"},
    };

    int idx = 0;
    for (const auto& m : modes) {
        auto* btn = createNavButton(QString::fromUtf8(m.icon), QString::fromUtf8(m.label), idx);
        modeButtons_.push_back(btn);
        mainLayout->addWidget(btn);
        idx++;
    }

    mainLayout->addStretch(1);

    auto* sep2 = new QFrame(this);
    sep2->setFrameShape(QFrame::HLine);
    sep2->setStyleSheet(QStringLiteral("color: #333333;"));
    mainLayout->addWidget(sep2);

    // Bottom utility buttons
    themeButton_ = createNavButton(QStringLiteral("🌙"), QStringLiteral("Theme"), -1);
    connect(themeButton_, &QPushButton::clicked, this, &NavRailWidget::themeToggleRequested);
    mainLayout->addWidget(themeButton_);

    sleepButton_ = createNavButton(QStringLiteral("💤"), QStringLiteral("Sleep Cycle"), -2);
    connect(sleepButton_, &QPushButton::clicked, this, &NavRailWidget::sleepRequested);
    mainLayout->addWidget(sleepButton_);

    settingsButton_ = createNavButton(QStringLiteral("⚙️"), QStringLiteral("Settings"), -3);
    connect(settingsButton_, &QPushButton::clicked, this, &NavRailWidget::settingsRequested);
    mainLayout->addWidget(settingsButton_);

    setCurrentMode(0);
}

QPushButton* NavRailWidget::createNavButton(const QString& icon, const QString& label, int index) {
    auto* btn = new QPushButton(this);
    btn->setText(icon);
    btn->setToolTip(label);
    btn->setFixedSize(56, 46);
    btn->setCursor(Qt::PointingHandCursor);
    btn->setStyleSheet(QStringLiteral(
        "QPushButton {"
        "    font-size: 20px;"
        "    background-color: transparent;"
        "    border: 1px solid transparent;"
        "    border-radius: 8px;"
        "    padding: 0px;"
        "}"
        "QPushButton:hover {"
        "    background-color: rgba(255, 255, 255, 0.08);"
        "    border: 1px solid rgba(255, 255, 255, 0.12);"
        "}"
        "QPushButton[selected=\"true\"] {"
        "    background-color: rgba(0, 120, 212, 0.25);"
        "    border: 1px solid #0078d4;"
        "}"
    ));

    if (index >= 0) {
        connect(btn, &QPushButton::clicked, this, [this, index]() {
            onModeButtonClicked(index);
        });
    }
    return btn;
}

void NavRailWidget::onModeButtonClicked(int index) {
    setCurrentMode(index);
    emit modeChanged(index);
}

void NavRailWidget::setCurrentMode(int index) {
    currentIndex_ = index;
    for (std::size_t i = 0; i < modeButtons_.size(); ++i) {
        const bool sel = (static_cast<int>(i) == index);
        modeButtons_[i]->setProperty("selected", sel);
        modeButtons_[i]->style()->unpolish(modeButtons_[i]);
        modeButtons_[i]->style()->polish(modeButtons_[i]);
    }
}

int NavRailWidget::currentMode() const {
    return currentIndex_;
}

}  // namespace aquila::gui

