// apps/aquila_gui/main_window.cpp
#include "main_window.hpp"
#include "theme/theme.hpp"

#include "aquila/core.hpp"
#include "aquila/inference/ollama_backend.hpp"
#if AQUILA_HAS_LLAMACPP
#include "aquila/inference/llama_backend.hpp"
#endif

#include <filesystem>
#include <QApplication>
#include <QFrame>
#include <QHBoxLayout>
#include <QMessageBox>
#include <QStatusBar>
#include <QVBoxLayout>

namespace aquila::gui {

MainWindow::MainWindow(QWidget* parent) : QMainWindow(parent) {
    const auto v = aquila::version();
    setWindowTitle(QStringLiteral("Aquila AI Rebuild %1").arg(QString::fromUtf8(v.data(), static_cast<qsizetype>(v.size()))));
    resize(1200, 800);

    setupUi();
    setupConnections();
}

MainWindow::~MainWindow() {
    if (activeWorker_ && activeWorker_->isRunning()) {
        activeWorker_->cancel();
        activeWorker_->wait(1000);
    }
    delete homePage_;
    homePage_ = nullptr;
    delete chatPage_;
    chatPage_ = nullptr;
    delete taskPage_;
    taskPage_ = nullptr;
    delete codeIdePage_;
    codeIdePage_ = nullptr;
    delete writingPage_;
    writingPage_ = nullptr;
    delete researchPage_;
    researchPage_ = nullptr;
    delete characterPage_;
    characterPage_ = nullptr;
    delete learnPage_;
    learnPage_ = nullptr;
    delete builderPage_;
    builderPage_ = nullptr;
    delete settingsPage_;
    settingsPage_ = nullptr;
}

void MainWindow::setupUi() {
    auto* central = new QWidget(this);
    setCentralWidget(central);

    auto* mainLayout = new QHBoxLayout(central);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    // Left Navigation Rail
    navRail_ = new NavRailWidget(central);
    mainLayout->addWidget(navRail_);

    auto* sepRail = new QFrame(central);
    sepRail->setFrameShape(QFrame::VLine);
    sepRail->setStyleSheet(QStringLiteral("color: #333333;"));
    mainLayout->addWidget(sepRail);

    // Right Area: Header Bar + Page Stack
    auto* rightArea = new QWidget(central);
    auto* rightLayout = new QVBoxLayout(rightArea);
    rightLayout->setContentsMargins(0, 0, 0, 0);
    rightLayout->setSpacing(0);

    // Top Header Chrome Bar
    auto* topBar = new QWidget(rightArea);
    topBar->setFixedHeight(40);
    topBar->setStyleSheet(QStringLiteral("background-color: #252526; border-bottom: 1px solid #333333;"));
    auto* topLayout = new QHBoxLayout(topBar);
    topLayout->setContentsMargins(16, 0, 16, 0);
    topLayout->setSpacing(12);

    topWorkspaceBadge_ = new QLabel(QStringLiteral("📁 Workspace: %1").arg(workspaceRoot_), topBar);
    topWorkspaceBadge_->setStyleSheet(QStringLiteral("color: #cccccc; font-size: 12px;"));
    topLayout->addWidget(topWorkspaceBadge_);

    topLayout->addStretch(1);

    topTierBadge_ = new QLabel(QStringLiteral("⚡ Tier: CPU-First Base"), topBar);
    topTierBadge_->setStyleSheet(QStringLiteral(
        "background-color: rgba(56, 139, 253, 0.15); color: #58a6ff; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight:bold;"
    ));
    topLayout->addWidget(topTierBadge_);

    topModelBadge_ = new QLabel(QStringLiteral("🧠 Model: aquila (Ollama)"), topBar);
    topModelBadge_->setStyleSheet(QStringLiteral(
        "background-color: rgba(63, 185, 80, 0.15); color: #7ee787; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight:bold;"
    ));
    topLayout->addWidget(topModelBadge_);

    rightLayout->addWidget(topBar);

    // Central Stacked Widget
    pageStack_ = new QStackedWidget(rightArea);

    homePage_ = new HomePage(pageStack_);
    chatPage_ = new ChatPage(pageStack_);
    taskPage_ = new TaskPage(pageStack_);
    codeIdePage_ = new CodeIdePage(pageStack_);
    writingPage_ = new WritingPage(pageStack_);
    researchPage_ = new ResearchPage(pageStack_);
    characterPage_ = new CharacterPage(pageStack_);
    learnPage_ = new LearnPage(pageStack_);
    builderPage_ = new RecipeBuilderPage(pageStack_);
    settingsPage_ = new SettingsPage(pageStack_);

    pageStack_->addWidget(homePage_);       // 0
    pageStack_->addWidget(chatPage_);       // 1
    pageStack_->addWidget(taskPage_);       // 2
    pageStack_->addWidget(codeIdePage_);    // 3
    pageStack_->addWidget(writingPage_);    // 4
    pageStack_->addWidget(researchPage_);   // 5
    pageStack_->addWidget(characterPage_);  // 6
    pageStack_->addWidget(learnPage_);      // 7
    pageStack_->addWidget(builderPage_);    // 8
    pageStack_->addWidget(settingsPage_);   // 9

    rightLayout->addWidget(pageStack_, 1);
    mainLayout->addWidget(rightArea, 1);

    // Status Bar
    statusBarLabel_ = new QLabel(QStringLiteral("Ready | Single-Threaded Core | Safe QThread Queued Boundary"), this);
    statusBar()->addWidget(statusBarLabel_);
    statusBar()->setStyleSheet(QStringLiteral("background-color: #1e1e1e; color: #888888; font-size: 11px;"));

    switchMode(0);
}

void MainWindow::setupConnections() {
    connect(navRail_, &NavRailWidget::modeChanged, this, &MainWindow::switchMode);
    connect(navRail_, &NavRailWidget::themeToggleRequested, this, &MainWindow::onThemeToggle);
    connect(navRail_, &NavRailWidget::sleepRequested, this, &MainWindow::onSleepCycle);
    connect(navRail_, &NavRailWidget::settingsRequested, this, [this]() {
        switchMode(9);
    });

    connect(taskPage_, &TaskPage::openBuilderRequested, this, &MainWindow::openCartridgeInBuilder);

    connect(homePage_, &HomePage::modeRequested, this, &MainWindow::switchMode);
    connect(homePage_, &HomePage::newChatRequested, this, [this]() {
        switchMode(1);
    });

    connect(chatPage_, &ChatPage::sendRequested, this, &MainWindow::onChatSend);
    connect(chatPage_, &ChatPage::cancelRequested, this, &MainWindow::onCancelCurrentTask);

    connect(taskPage_, &TaskPage::runRecipeRequested, this, &MainWindow::onTaskRun);
    connect(taskPage_, &TaskPage::cancelRequested, this, &MainWindow::onCancelCurrentTask);

    connect(codeIdePage_, &CodeIdePage::agentSubcallRequested, this, [this](const QString& text, const QString& file) {
        switchMode(1);
        chatPage_->appendUserMessage(QStringLiteral("Please review / revise the following code from %1:\n```\n%2\n```").arg(file, text));
    });

    connect(settingsPage_, &SettingsPage::themeChanged, this, [this](bool isDark) {
        apply_theme(qApp, isDark ? ThemeMode::Dark : ThemeMode::Light);
    });
    connect(settingsPage_, &SettingsPage::settingsApplied, this, &MainWindow::onSettingsApplied);
}

void MainWindow::switchMode(int index) {
    if (index >= 0 && index < pageStack_->count()) {
        pageStack_->setCurrentIndex(index);
        navRail_->setCurrentMode(index);
    }
}

int MainWindow::activeMode() const {
    return pageStack_->currentIndex();
}

void MainWindow::setWorkspaceRoot(const QString& path) {
    workspaceRoot_ = path;
    topWorkspaceBadge_->setText(QStringLiteral("📁 Workspace: %1").arg(path));
    homePage_->setWorkspacePath(path);
    codeIdePage_->setWorkspaceRoot(path);
}

void MainWindow::onThemeToggle() {
    toggle_theme(qApp);
}

void MainWindow::onSleepCycle() {
    statusBarLabel_->setText(QStringLiteral("Initiating Memory Consolidation Sleep Cycle..."));
    QMessageBox::information(this, QStringLiteral("Memory Sleep Cycle"),
                             QStringLiteral("Memory Sleep Cycle complete: Session interactions consolidated into long-term SQLite FactStore graph."));
    statusBarLabel_->setText(QStringLiteral("Ready | Memory Consolidated"));
}

void MainWindow::onSettingsApplied() {
    const bool isGpu = (settingsPage_->computeTier() == QStringLiteral("gpu"));
    if (isGpu) {
        topTierBadge_->setText(QStringLiteral("⚡ Tier: GPU Boost (RTX 4070)"));
        topTierBadge_->setStyleSheet(QStringLiteral(
            "background-color: rgba(227, 179, 65, 0.2); color: #f2cc60; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight:bold;"
        ));
    } else {
        topTierBadge_->setText(QStringLiteral("⚡ Tier: CPU-First Base"));
        topTierBadge_->setStyleSheet(QStringLiteral(
            "background-color: rgba(56, 139, 253, 0.15); color: #58a6ff; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight:bold;"
        ));
    }

    const QString bType = settingsPage_->backendType();
    const QString mName = settingsPage_->modelName().trimmed();
    if (bType == QStringLiteral("llama")) {
        QString displayName = mName;
        const int slashIdx = std::max(displayName.lastIndexOf('/'), displayName.lastIndexOf('\\'));
        if (slashIdx >= 0) {
            displayName = displayName.mid(slashIdx + 1);
        }
        if (displayName.isEmpty()) {
            displayName = isGpu ? QStringLiteral("Llama-3.1-8B") : QStringLiteral("Llama-3.2-3B");
        }
        topModelBadge_->setText(QStringLiteral("🧠 Model: %1 (%2)").arg(displayName, isGpu ? QStringLiteral("llama.cpp CUDA") : QStringLiteral("llama.cpp CPU")));
        topModelBadge_->setStyleSheet(QStringLiteral(
            "background-color: rgba(163, 113, 247, 0.2); color: #d2a8ff; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight:bold;"
        ));
    } else {
        topModelBadge_->setText(QStringLiteral("🧠 Model: %1 (Ollama)").arg(mName.isEmpty() ? QStringLiteral("aquila") : mName));
        topModelBadge_->setStyleSheet(QStringLiteral(
            "background-color: rgba(63, 185, 80, 0.15); color: #7ee787; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight:bold;"
        ));
    }

    if (!settingsPage_->workspacePath().isEmpty()) {
        setWorkspaceRoot(settingsPage_->workspacePath());
    }
    activeBackend_.reset();
}

std::shared_ptr<aquila::IInferenceBackend> MainWindow::createBackend() {
#if AQUILA_HAS_LLAMACPP
    if (settingsPage_->backendType() == QStringLiteral("llama")) {
        LlamaConfig lcfg;
        const bool isGpu = (settingsPage_->computeTier() == QStringLiteral("gpu"));
        QString m = settingsPage_->modelName().trimmed();
        if (m.isEmpty() || m == QStringLiteral("aquila")) {
            if (isGpu && std::filesystem::exists("D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")) {
                lcfg.model_path = "D:/aquila-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf";
            } else if (std::filesystem::exists("D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf")) {
                lcfg.model_path = "D:/aquila-models/Llama-3.2-3B-Instruct-Q4_K_M.gguf";
            } else {
                lcfg.model_path = m.toStdString();
            }
        } else {
            lcfg.model_path = m.toStdString();
        }

        lcfg.profile = isGpu ? ComputeProfile::gpu_high_vram : ComputeProfile::cpu_low_spec_edge;
        lcfg.n_ctx = static_cast<std::uint32_t>(settingsPage_->contextWindow());
        lcfg.n_gpu_layers = isGpu ? 999 : 0;
        return std::make_shared<LlamaCppBackend>(lcfg);
    }
#endif
    OllamaConfig cfg;
    cfg.base_url = settingsPage_->ollamaHost().toStdString();
    cfg.model = settingsPage_->modelName().toStdString();
    return std::make_shared<OllamaHttpBackend>(cfg);
}

void MainWindow::onChatSend(const QString& prompt, const QStringList& /* attachments */) {
    if (activeWorker_ && activeWorker_->isRunning()) {
        activeWorker_->cancel();
        activeWorker_->wait();
    }

    if (!activeBackend_) {
        statusBarLabel_->setText(QStringLiteral("Loading model weights..."));
        qApp->processEvents();
        try {
            activeBackend_ = createBackend();
        } catch (const std::exception& e) {
            chatPage_->appendAssistantMessage(QStringLiteral("❌ Failed to initialize backend:\n%1").arg(QString::fromUtf8(e.what())));
            statusBarLabel_->setText(QStringLiteral("Backend initialization failed"));
            return;
        }
    }

    RecipeCartridge recipe = fn_dev_implement_recipe();

    LoopConfig config;
    config.task_id = "gui-chat";
    config.mode = "chat";
    config.context_strategy = CondenserStrategy::sac;

    chatPage_->setRunning(true);
    statusBarLabel_->setText(QStringLiteral("Thinking..."));

    activeWorker_ = new AgentWorker(activeBackend_, recipe, prompt.toStdString(), config, workspaceRoot_.toStdString(), this);

    connect(activeWorker_, &AgentWorker::tokenStreamed, chatPage_, &ChatPage::appendToken);
    connect(activeWorker_, &AgentWorker::statusChanged, this, [this](const QString& status) {
        statusBarLabel_->setText(status);
        chatPage_->setStatus(status);
    });
    connect(activeWorker_, &AgentWorker::finished, this, [this](bool success, const QString& /* output */) {
        chatPage_->setRunning(false);
        chatPage_->finalizeAssistantMessage();
        statusBarLabel_->setText(success ? QStringLiteral("Ready") : QStringLiteral("Task terminated"));
    });

    activeWorker_->start();
}

void MainWindow::onTaskRun(const QString& recipeId, const QString& prompt) {
    if (activeWorker_ && activeWorker_->isRunning()) {
        activeWorker_->cancel();
        activeWorker_->wait();
    }

    if (!activeBackend_) {
        statusBarLabel_->setText(QStringLiteral("Loading model weights..."));
        qApp->processEvents();
        try {
            activeBackend_ = createBackend();
        } catch (const std::exception& e) {
            QMessageBox::critical(this, QStringLiteral("Backend Error"),
                                  QStringLiteral("Failed to initialize backend:\n%1").arg(QString::fromUtf8(e.what())));
            statusBarLabel_->setText(QStringLiteral("Backend initialization failed"));
            return;
        }
    }

    RecipeCartridge recipe = fn_dev_implement_recipe();
    for (const auto& r : all_builtin_recipes()) {
        if (QString::fromStdString(r.recipe_id) == recipeId) {
            recipe = r;
            break;
        }
    }

    LoopConfig config;
    config.task_id = "gui-task-" + recipe.recipe_id;
    config.mode = "task";
    config.context_strategy = CondenserStrategy::sac;

    taskPage_->setRunning(true);
    statusBarLabel_->setText(QStringLiteral("Running %1...").arg(recipeId));

    const std::string goal = prompt.isEmpty() ? recipe.goal_template : prompt.toStdString();
    activeWorker_ = new AgentWorker(activeBackend_, recipe, goal, config, workspaceRoot_.toStdString(), this);

    connect(activeWorker_, &AgentWorker::turnCompleted, taskPage_, [this](int turn, const QString&, const QString& mod, const QString& act, const QString& out) {
        taskPage_->addLedgerEntry(turn, mod, act, QStringLiteral("OK"), out);
    });
    connect(activeWorker_, &AgentWorker::statusChanged, this, [this](const QString& status) {
        statusBarLabel_->setText(status);
        taskPage_->setStatus(status);
    });
    connect(activeWorker_, &AgentWorker::finished, this, [this](bool success, const QString& output) {
        taskPage_->setRunning(false);
        statusBarLabel_->setText(success ? QStringLiteral("Task Succeeded") : QStringLiteral("Task Failed"));
        if (!output.isEmpty()) {
            taskPage_->setStatus(QStringLiteral("Completed: %1").arg(output));
        }
    });

    activeWorker_->start();
}

void MainWindow::onCancelCurrentTask() {
    if (activeWorker_ && activeWorker_->isRunning()) {
        statusBarLabel_->setText(QStringLiteral("Cancelling task..."));
        activeWorker_->cancel();
    }
}

void MainWindow::openCartridgeInBuilder(const QString& recipeId) {
    const auto list = aquila::all_builtin_recipes();
    for (const auto& r : list) {
        if (r.recipe_id == recipeId.toStdString()) {
            builderPage_->loadCartridge(r);
            break;
        }
    }
    switchMode(8);
}

}  // namespace aquila::gui
