// apps/aquila_gui/pages/home_page.cpp
#include "home_page.hpp"

#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QScrollArea>

namespace aquila::gui {

HomePage::HomePage(QWidget* parent)
    : BasePage(QStringLiteral("Aquila AI Dashboard"),
               QStringLiteral("Console-First Autonomous Multi-Domain Agent Rebuild"),
               QStringLiteral("🦅"), parent) {
    auto* scrollArea = new QScrollArea(this);
    scrollArea->setWidgetResizable(true);
    scrollArea->setFrameShape(QFrame::NoFrame);

    auto* container = new QWidget(scrollArea);
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(16);

    // Banner card: Workspace & Hardware Profile
    auto* bannerGroup = new QGroupBox(QStringLiteral("System & Workspace Overview"), container);
    auto* bannerLayout = new QVBoxLayout(bannerGroup);

    workspaceLabel_ = new QLabel(QStringLiteral("Active Workspace: (not set)"), bannerGroup);
    workspaceLabel_->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff;"));
    bannerLayout->addWidget(workspaceLabel_);

    specsLabel_ = new QLabel(QStringLiteral("Hardware: CPU-first baseline (8GB RAM tier) + GPU accelerator auto-detect"), bannerGroup);
    specsLabel_->setStyleSheet(QStringLiteral("color: #8b949e;"));
    bannerLayout->addWidget(specsLabel_);

    auto* quickBtnLayout = new QHBoxLayout();
    auto* newChatBtn = new QPushButton(QStringLiteral("💬 Start New Chat"), bannerGroup);
    newChatBtn->setProperty("accent", true);
    connect(newChatBtn, &QPushButton::clicked, this, &HomePage::newChatRequested);
    quickBtnLayout->addWidget(newChatBtn);

    auto* openWsBtn = new QPushButton(QStringLiteral("📁 Switch Workspace"), bannerGroup);
    connect(openWsBtn, &QPushButton::clicked, this, &HomePage::openWorkspaceRequested);
    quickBtnLayout->addWidget(openWsBtn);
    quickBtnLayout->addStretch(1);

    bannerLayout->addLayout(quickBtnLayout);
    layout->addWidget(bannerGroup);

    // Mode Tiles Grid
    auto* gridGroup = new QGroupBox(QStringLiteral("Workspaces & Modes"), container);
    auto* gridLayout = new QGridLayout(gridGroup);
    gridLayout->setSpacing(12);

    const struct {
        const char* icon;
        const char* title;
        const char* desc;
        int modeIndex;
    } tiles[] = {
        {"💬", "Chat Mode", "Interactive streaming chat with multi-turn context and reasoning.", 1},
        {"⚡", "Tasks Mode", "Autonomous recipe runner with deterministic exit gates and scratchpad.", 2},
        {"💻", "Code IDE", "Live code canvas, file explorer, syntax highlighting, and pending-patch reviews.", 3},
        {"📝", "Writing Studio", "Document outline tree, section editor, and live GitHub markdown preview.", 4},
        {"🔍", "Research Lab", "Local markdown vector search, SQLite fact graph, and persistent page cache.", 5},
        {"👤", "Character AI", "Persona management with strict 800+ character initialization quality gates.", 6},
        {"🎓", "Learn & Archive", "Hierarchical course syllabus generation, quizzes, and 0-5 mastery tracking.", 7},
        {"🧩", "Recipe Builder", "Visual graph workflow editor for assembling and validating custom recipe cartridges.", 8},
    };

    int row = 0;
    int col = 0;
    for (const auto& t : tiles) {
        auto* tile = createModeTile(QString::fromUtf8(t.icon),
                                    QString::fromUtf8(t.title),
                                    QString::fromUtf8(t.desc),
                                    t.modeIndex);
        gridLayout->addWidget(tile, row, col);
        col++;
        if (col >= 2) {
            col = 0;
            row++;
        }
    }

    layout->addWidget(gridGroup);
    layout->addStretch(1);

    scrollArea->setWidget(container);
    contentLayout()->addWidget(scrollArea);
}

QWidget* HomePage::createModeTile(const QString& icon, const QString& title, const QString& description, int modeIndex) {
    auto* card = new QWidget(this);
    card->setObjectName(QStringLiteral("modeCard"));
    card->setStyleSheet(QStringLiteral(
        "#modeCard {"
        "    background-color: #252526;"
        "    border: 1px solid #3c3c3c;"
        "    border-radius: 8px;"
        "    padding: 10px;"
        "}"
        "#modeCard:hover {"
        "    background-color: #2d2d30;"
        "    border-color: #0078d4;"
        "}"
    ));

    auto* layout = new QVBoxLayout(card);
    layout->setSpacing(6);

    auto* topLayout = new QHBoxLayout();
    auto* iconLabel = new QLabel(icon, card);
    iconLabel->setStyleSheet(QStringLiteral("font-size: 22px;"));
    topLayout->addWidget(iconLabel);

    auto* titleLabel = new QLabel(title, card);
    titleLabel->setStyleSheet(QStringLiteral("font-weight: bold; font-size: 14px; color: #ffffff;"));
    topLayout->addWidget(titleLabel);
    topLayout->addStretch(1);
    layout->addLayout(topLayout);

    auto* descLabel = new QLabel(description, card);
    descLabel->setWordWrap(true);
    descLabel->setStyleSheet(QStringLiteral("color: #8b949e; font-size: 12px;"));
    layout->addWidget(descLabel);

    auto* launchBtn = new QPushButton(QStringLiteral("Open %1 →").arg(title), card);
    connect(launchBtn, &QPushButton::clicked, this, [this, modeIndex]() {
        emit modeRequested(modeIndex);
    });
    layout->addWidget(launchBtn);

    return card;
}

void HomePage::setSystemSpecs(const QString& specsText) {
    if (specsLabel_) {
        specsLabel_->setText(specsText);
    }
}

void HomePage::setWorkspacePath(const QString& path) {
    if (workspaceLabel_) {
        workspaceLabel_->setText(QStringLiteral("Active Workspace: %1").arg(path));
    }
}

}  // namespace aquila::gui

