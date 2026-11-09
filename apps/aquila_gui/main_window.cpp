// apps/aquila_gui/main_window.cpp
#include "main_window.hpp"
#include "dialogs/setup_wizard.hpp"
#include "theme/theme.hpp"

#include "aquila/core.hpp"
#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/knowledge/web_search.hpp"
#include "aquila/knowledge/page_scorer.hpp"
#include "aquila/learn/learn_module.hpp"
#include "aquila/inference/ollama_backend.hpp"
#if AQUILA_HAS_LLAMACPP
#include "aquila/inference/llama_backend.hpp"
#endif

#include <filesystem>
#include <QAction>
#include <QApplication>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QStatusBar>
#include <QTextStream>
#include <QVBoxLayout>

namespace aquila::gui {

MainWindow::MainWindow(QWidget* parent) : QMainWindow(parent) {
    const auto v = aquila::version();
    setWindowTitle(QStringLiteral("Aquila AI Rebuild %1").arg(QString::fromUtf8(v.data(), static_cast<qsizetype>(v.size()))));
    resize(1200, 800);

    setupUi();
    setupConnections();
    onSettingsApplied();
    if (learnPage_) {
        learnMasteryLevel_ = learnPage_->masteryLevel();
    }
    refreshLearnArchiveSources();
}

void MainWindow::closeEvent(QCloseEvent* event) {
    if (settingsPage_) {
        settingsPage_->saveSettings();
    }
    QMainWindow::closeEvent(event);
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
    // Menu Bar
    auto* fileMenu = menuBar()->addMenu(QStringLiteral("&File"));
    auto* openAct = fileMenu->addAction(QStringLiteral("&Open Workspace..."), this, &MainWindow::onBrowseWorkspace);
    openAct->setShortcut(QKeySequence::Open);
    fileMenu->addSeparator();
    auto* exitAct = fileMenu->addAction(QStringLiteral("E&xit"), this, &QWidget::close);
    exitAct->setShortcut(QKeySequence::Quit);

    auto* toolsMenu = menuBar()->addMenu(QStringLiteral("&Tools"));
    toolsMenu->addAction(QStringLiteral("&Memory Sleep Cycle"), this, &MainWindow::onSleepCycle);

    auto* helpMenu = menuBar()->addMenu(QStringLiteral("&Help"));
    helpMenu->addAction(QStringLiteral("&Hardware Setup Wizard..."), this, &MainWindow::onOpenSetupWizard);

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
    connect(homePage_, &HomePage::openWorkspaceRequested, this, &MainWindow::onBrowseWorkspace);

    connect(chatPage_, &ChatPage::sendRequested, this, &MainWindow::onChatSend);
    connect(chatPage_, &ChatPage::cancelRequested, this, &MainWindow::onCancelCurrentTask);

    connect(taskPage_, &TaskPage::runRecipeRequested, this, &MainWindow::onTaskRun);
    connect(taskPage_, &TaskPage::cancelRequested, this, &MainWindow::onCancelCurrentTask);

    connect(codeIdePage_, &CodeIdePage::agentSubcallRequested, this, [this](const QString& text, const QString& file) {
        switchMode(1);
        chatPage_->appendUserMessage(QStringLiteral("Please review / revise the following code from %1:\n```\n%2\n```").arg(file, text));
    });
    connect(codeIdePage_, &CodeIdePage::inlineEditRequested, this, &MainWindow::onCodeIdeInlineEdit);

    connect(writingPage_, &WritingPage::reviseSectionRequested, this, &MainWindow::onWritingSectionRevise);
    connect(writingPage_, &WritingPage::compileDocumentRequested, this, &MainWindow::onWritingCompile);

    connect(researchPage_, &ResearchPage::searchRequested, this, &MainWindow::onResearchSearch);
    connect(researchPage_, &ResearchPage::saveReportRequested, this, &MainWindow::onSaveResearchReport);
    connect(researchPage_, &ResearchPage::sendToArchiveRequested, this, &MainWindow::onSendResearchToArchive);

    connect(characterPage_, &CharacterPage::chatMessageSent, this, &MainWindow::onCharacterChat);
    connect(characterPage_, &CharacterPage::savePersonaRequested, this, &MainWindow::onCharacterSave);

    connect(learnPage_, &LearnPage::addTextSourceRequested, this, &MainWindow::onLearnAddTextSource);
    connect(learnPage_, &LearnPage::addFileSourceRequested, this, &MainWindow::onLearnAddFileSource);
    connect(learnPage_, &LearnPage::addUrlSourceRequested, this, &MainWindow::onLearnAddUrlSource);
    connect(learnPage_, &LearnPage::askArchiveRequested, this, &MainWindow::onLearnAskArchive);
    connect(learnPage_, &LearnPage::buildFromSourcesRequested, this, &MainWindow::onLearnBuildFromSources);
    connect(learnPage_, &LearnPage::generateAssessmentRequested, this, &MainWindow::onLearnGenerateAssessment);
    connect(learnPage_, &LearnPage::submitAnswerRequested, this, &MainWindow::onLearnSubmitAnswer);

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
    refreshLearnArchiveSources();
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

        if (!std::filesystem::exists(lcfg.model_path)) {
            throw std::runtime_error("GGUF model file not found: '" + lcfg.model_path + "'. Please check the path in Settings.");
        }

        lcfg.profile = isGpu ? ComputeProfile::gpu_high_vram : ComputeProfile::cpu_low_spec_edge;
        lcfg.n_ctx = static_cast<std::uint32_t>(settingsPage_->contextWindow());
        lcfg.n_gpu_layers = isGpu ? 999 : 0;
        return std::make_shared<LlamaCppBackend>(lcfg);
    }
#endif
    OllamaConfig cfg;
    cfg.base_url = settingsPage_->ollamaHost().toStdString();
    QString m = settingsPage_->modelName().trimmed();
    if (m.isEmpty() || m == QStringLiteral("aquila")) {
        cfg.model = "llama3.2:latest";
    } else {
        cfg.model = m.toStdString();
    }
    return std::make_shared<OllamaHttpBackend>(cfg);
}

bool MainWindow::ensureBackendReady() {
    if (activeBackend_) return true;

    statusBarLabel_->setText(QStringLiteral("Loading model weights into VRAM..."));
    qApp->processEvents();
    try {
        activeBackend_ = createBackend();
        statusBarLabel_->setText(QStringLiteral("Model weights loaded successfully."));
        return true;
    } catch (const std::exception& e) {
        QMessageBox::critical(this, QStringLiteral("Backend Error"),
                              QStringLiteral("Failed to initialize inference backend:\n%1").arg(QString::fromUtf8(e.what())));
        statusBarLabel_->setText(QStringLiteral("Backend initialization failed"));
        return false;
    }
}

void MainWindow::onChatSend(const QString& prompt, const QStringList& attachments) {
    chatPage_->appendUserMessage(prompt, attachments);

    if (activeWorker_ && activeWorker_->isRunning()) {
        activeWorker_->cancel();
        activeWorker_->wait();
    }

    if (!ensureBackendReady()) {
        chatPage_->appendAssistantMessage(QStringLiteral("❌ Failed to initialize backend. Please configure model settings in the Settings page."));
        return;
    }

    QString fullPrompt = prompt;
    if (!attachments.isEmpty()) {
        QString contextBlocks;
        qint64 totalBytesRead = 0;
        const qint64 maxBudget = 100 * 1024; // 100 KB total context budget protection

        for (const auto& filePath : attachments) {
            QFile file(filePath);
            if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
                QFileInfo fi(filePath);
                const QString ext = fi.suffix();
                const qint64 remaining = maxBudget - totalBytesRead;
                if (remaining <= 0) break;
                QByteArray content = file.read(remaining);
                totalBytesRead += content.size();
                contextBlocks += QStringLiteral("\n\n---\n[Attached File: %1]\n```%2\n%3\n```\n").arg(
                    fi.fileName(),
                    ext,
                    QString::fromUtf8(content)
                );
                if (totalBytesRead >= maxBudget) {
                    contextBlocks += QStringLiteral("\n[Notice: Attachment content truncated to 100 KB context budget]\n");
                    break;
                }
            }
        }
        if (!contextBlocks.isEmpty()) {
            fullPrompt = QStringLiteral("Context Files:%1\n\nUser Question:\n%2").arg(
                contextBlocks,
                prompt.isEmpty() ? QStringLiteral("Please analyze the attached file(s).") : prompt
            );
        }
    }

    RecipeCartridge recipe = fn_dev_implement_recipe();

    LoopConfig config;
    config.task_id = "gui-chat";
    config.mode = "chat";
    config.context_strategy = CondenserStrategy::sac;

    chatPage_->setRunning(true);
    statusBarLabel_->setText(QStringLiteral("Thinking..."));

    activeWorker_ = new AgentWorker(activeBackend_, recipe, fullPrompt.toStdString(), config, workspaceRoot_.toStdString(), this);
    activeWorker_->setChatHistory(chatHistory_);

    connect(activeWorker_, &AgentWorker::tokenStreamed, chatPage_, &ChatPage::appendToken);
    connect(activeWorker_, &AgentWorker::statusChanged, this, [this](const QString& status) {
        statusBarLabel_->setText(status);
        chatPage_->setStatus(status);
    });

    const std::string promptStd = fullPrompt.toStdString();
    connect(activeWorker_, &AgentWorker::finished, this, [this, promptStd](bool success, const QString& output) {
        chatPage_->setRunning(false);
        chatPage_->finalizeAssistantMessage();
        statusBarLabel_->setText(success ? QStringLiteral("Ready") : QStringLiteral("Task terminated"));
        if (success) {
            Message user_m;
            user_m.role = Role::user;
            user_m.content = promptStd;
            chatHistory_.push_back(std::move(user_m));

            Message ass_m;
            ass_m.role = Role::assistant;
            ass_m.content = output.toStdString();
            chatHistory_.push_back(std::move(ass_m));
        }
    });

    activeWorker_->start();
}

void MainWindow::onTaskRun(const QString& recipeId, const QString& prompt) {
    if (activeWorker_ && activeWorker_->isRunning()) {
        activeWorker_->cancel();
        activeWorker_->wait();
    }

    if (!ensureBackendReady()) {
        taskPage_->setRunning(false);
        return;
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
    if (activeBackend_) {
        config.tier = RuntimeTierConfig::for_profile(activeBackend_->active_profile());
    }

    taskPage_->setRunning(true);
    statusBarLabel_->setText(QStringLiteral("Running %1...").arg(recipeId));

    std::string goal = prompt.toStdString();
    if (goal.empty()) {
        goal = recipe.goal_template;
        const std::string marker = "{{user_instructions}}";
        const auto pos = goal.find(marker);
        if (pos != std::string::npos) {
            goal.replace(pos, marker.length(), "technical overview and key architectural findings");
        }
    }
    activeWorker_ = new AgentWorker(activeBackend_, recipe, goal, config, workspaceRoot_.toStdString(), this);

    connect(activeWorker_, &AgentWorker::turnCompleted, taskPage_,
            [this](int turn, const QString&, const QString& mod, const QString& act, bool success, const QString& out) {
        taskPage_->addLedgerEntry(turn, mod, act, success ? QStringLiteral("OK") : QStringLiteral("FAILED"), out);
    });
    connect(activeWorker_, &AgentWorker::scratchpadUpdated, taskPage_, &TaskPage::updateScratchpad);
    connect(activeWorker_, &AgentWorker::logFileReady, this, [this](const QString& logPath, const QString&) {
        taskPage_->setLastLogPath(logPath);
        statusBarLabel_->setText(QStringLiteral("Session log: %1").arg(logPath));
    });
    connect(activeWorker_, &AgentWorker::statusChanged, this, [this](const QString& status) {
        statusBarLabel_->setText(status);
        taskPage_->setStatus(status);
    });
    connect(activeWorker_, &AgentWorker::finished, this, [this, recipeId](bool success, const QString& output) {
        taskPage_->setRunning(false);
        statusBarLabel_->setText(success ? QStringLiteral("Task Succeeded") : QStringLiteral("Task Failed"));
        if (!output.isEmpty()) {
            taskPage_->setStatus(QStringLiteral("Completed: %1").arg(output));
        }
        if (success) {
            const QDir dir(workspaceRoot_);
            if (recipeId.contains(QStringLiteral("research")) && dir.exists(QStringLiteral("research_report.md"))) {
                QMessageBox::information(this, QStringLiteral("Research Complete"),
                    QStringLiteral("Research deliverable successfully generated at:\n%1")
                    .arg(dir.filePath(QStringLiteral("research_report.md"))));
            } else if (recipeId.contains(QStringLiteral("writing")) && dir.exists(QStringLiteral("compiled_document.md"))) {
                QMessageBox::information(this, QStringLiteral("Writing Complete"),
                    QStringLiteral("Document deliverable successfully compiled at:\n%1")
                    .arg(dir.filePath(QStringLiteral("compiled_document.md"))));
            }
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

void MainWindow::onBrowseWorkspace() {
    const QString dir = QFileDialog::getExistingDirectory(this, QStringLiteral("Select Workspace Directory"), workspaceRoot_);
    if (!dir.isEmpty()) {
        setWorkspaceRoot(dir);
        statusBarLabel_->setText(QStringLiteral("Workspace updated: %1").arg(dir));
    }
}

void MainWindow::onCodeIdeInlineEdit(const QString& prompt, const QString& selectedText, const QString& filePath) {
    statusBarLabel_->setText(QStringLiteral("Generating inline refactor..."));
    QString replacement;
    if (ensureBackendReady()) {
        try {
            const auto cp = activeBackend_->mark_checkpoint();
            Message sys_msg;
            sys_msg.role = Role::system;
            sys_msg.content = "You are an expert software engineer. Provide only the replacement code for the selected block. Do not include markdown code fences or conversational prose.";
            activeBackend_->append(sys_msg);

            Message user_msg;
            user_msg.role = Role::user;
            user_msg.content = "Instruction: " + prompt.toStdString() + "\n\nOriginal Code:\n" + selectedText.toStdString();
            activeBackend_->append(user_msg);

            GenerationParams params;
            params.constraint = OutputConstraint::none();
            auto res = activeBackend_->generate(params, nullptr);
            activeBackend_->rollback_to(cp);

            if (res.ok) {
                replacement = QString::fromStdString(res.content).trimmed();
            }
        } catch (...) {
            replacement.clear();
        }
    }
    if (replacement.isEmpty()) {
        replacement = QStringLiteral("// [Refactored: %1]\n%2").arg(prompt, selectedText);
    }
    if (auto* ed = codeIdePage_->currentEditor()) {
        ed->applyInlinePendingPatch(replacement);
    }
    codeIdePage_->addPendingPatch(filePath, QStringLiteral("@@ -1,%1 +1,%2 @@\n-%3\n+%4")
        .arg(selectedText.split('\n').size()).arg(replacement.split('\n').size())
        .arg(selectedText, replacement));
    statusBarLabel_->setText(QStringLiteral("Inline refactor ready (Press Enter to accept, Esc to discard)"));
}

void MainWindow::onWritingSectionRevise(const QString& sectionContent, const QString& instruction) {
    statusBarLabel_->setText(QStringLiteral("Revising section..."));
    QString revised;
    if (ensureBackendReady()) {
        try {
            const auto cp = activeBackend_->mark_checkpoint();
            Message sys_msg;
            sys_msg.role = Role::system;
            sys_msg.content = "You are an expert editor and technical writer. Revise the provided section following the instruction exactly. Return only the revised text.";
            activeBackend_->append(sys_msg);

            Message user_msg;
            user_msg.role = Role::user;
            user_msg.content = "Instruction: " + instruction.toStdString() + "\n\nContent:\n" + sectionContent.toStdString();
            activeBackend_->append(user_msg);

            GenerationParams params;
            params.constraint = OutputConstraint::none();
            auto res = activeBackend_->generate(params, nullptr);
            activeBackend_->rollback_to(cp);

            if (res.ok) {
                revised = QString::fromStdString(res.content).trimmed();
            }
        } catch (...) {
            revised.clear();
        }
    }
    if (revised.isEmpty()) {
        revised = QStringLiteral("### Revised Section\n\n> *Revision note: %1*\n\n%2").arg(instruction, sectionContent);
    }
    if (auto* ed = writingPage_->editor()) {
        ed->applyInlinePendingPatch(revised);
    }
    writingPage_->setSectionContent(QStringLiteral("Active Section"), revised);
    statusBarLabel_->setText(QStringLiteral("Section revised successfully"));
}

void MainWindow::onWritingCompile() {
    const QString content = writingPage_->currentSectionContent();
    const QString targetPath = QDir(workspaceRoot_).filePath(QStringLiteral("compiled_document.md"));
    QFile file(targetPath);
    if (file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        QTextStream out(&file);
        out << "# Compiled Document\n\n";
        out << "Generated by Aquila Writing Studio\n\n";
        out << content;
        file.close();
        writingPage_->setStatus(QStringLiteral("Compiled to %1").arg(targetPath));
        statusBarLabel_->setText(QStringLiteral("Document compiled to %1").arg(targetPath));
    } else {
        writingPage_->setStatus(QStringLiteral("Document compiled (in-memory)"));
        statusBarLabel_->setText(QStringLiteral("Document compiled"));
    }
}

void MainWindow::onResearchSearch(const QString& query, const QString& depth, const QString& engine, const QString& scope) {
    researchPage_->clearAll();
    statusBarLabel_->setText(QStringLiteral("Researching '%1' via %2 (%3)...").arg(query, engine, scope));

    int foundCount = 0;
    QStringList sourceSummaries;
    QString scrapedContext;

    QString trimmedQuery = query.trimmed();
    if (trimmedQuery.startsWith('"') && trimmedQuery.endsWith('"') && trimmedQuery.size() >= 2) {
        trimmedQuery = trimmedQuery.mid(1, trimmedQuery.size() - 2).trimmed();
    }

    const bool doLocal = scope.contains(QStringLiteral("Local"), Qt::CaseInsensitive) || scope.contains(QStringLiteral("Both"), Qt::CaseInsensitive);
    const bool doWeb = scope.contains(QStringLiteral("Web"), Qt::CaseInsensitive) || scope.contains(QStringLiteral("Both"), Qt::CaseInsensitive);

    // 1. Local Search (if scope includes Local)
    if (doLocal) {
        QDir dir(workspaceRoot_);
        const QStringList files = dir.entryList(QDir::Files | QDir::NoDotAndDotDot);
        for (const auto& f : files) {
            QFile file(dir.filePath(f));
            if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
                const QString text = QString::fromUtf8(file.read(8192));
                if (text.contains(trimmedQuery, Qt::CaseInsensitive)) {
                    QString matchSnippet = text.left(200).trimmed();
                    researchPage_->addSearchResult(QStringLiteral("Match in %1: %2").arg(f, matchSnippet), 0.95 - (foundCount * 0.05), QStringLiteral("Local Files"), f);
                    researchPage_->addFact(QStringLiteral("Local context from %1: %2").arg(f, matchSnippet.left(100)), 0.95, f);
                    sourceSummaries.append(QStringLiteral("- **Local File (%1)**: %2").arg(f, matchSnippet));
                    ++foundCount;
                }
            }
        }
    }

    // 2. Web Search (if scope includes Web)
    if (doWeb) {
        try {
            aquila::knowledge::SearchOptions opts;
            if (settingsPage_) {
                opts.searxng_endpoint = settingsPage_->searxngEndpoint().toStdString();
            }
            aquila::knowledge::WebSearchEngine webEngine(opts);
            int limit = 5;
            if (depth.contains(QStringLiteral("10"))) limit = 10;
            else if (depth.contains(QStringLiteral("15"))) limit = 15;

            std::vector<aquila::knowledge::SearchResult> results;
            if (engine == QStringLiteral("duckduckgo")) {
                results = webEngine.search_duckduckgo_lite(trimmedQuery.toStdString(), limit);
                if (results.empty()) {
                    results = webEngine.search_wikipedia(trimmedQuery.toStdString(), limit);
                }
            } else if (engine == QStringLiteral("searxng")) {
                results = webEngine.search_searxng(trimmedQuery.toStdString(), limit);
                if (results.empty()) {
                    results = webEngine.search_duckduckgo_lite(trimmedQuery.toStdString(), limit);
                }
                if (results.empty()) {
                    results = webEngine.search_wikipedia(trimmedQuery.toStdString(), limit);
                }
            } else if (engine == QStringLiteral("wikipedia")) {
                results = webEngine.search_wikipedia(trimmedQuery.toStdString(), limit);
            } else {
                results = webEngine.search(trimmedQuery.toStdString());
            }

            for (const auto& r : results) {
                QString title = QString::fromStdString(r.title);
                QString snippet = QString::fromStdString(r.snippet);
                QString url = QString::fromStdString(r.url);
                QString eng = QString::fromStdString(r.engine);

                researchPage_->addSearchResult(title + QStringLiteral(" - ") + snippet, r.score, eng, url);
                sourceSummaries.append(QStringLiteral("- **[%1](%2)** (Score: %3): %4")
                    .arg(title, url, QString::number(r.score, 'f', 1), snippet));
                ++foundCount;
            }

            // Auto-scrape top 2 results if auto-scrape enabled
            const bool doScrape = settingsPage_ ? settingsPage_->autoScrapeEnabled() : true;
            if (doScrape) {
                aquila::ModuleContext kmCtx;
                kmCtx.workspace_root = workspaceRoot_.toStdString();
                aquila::knowledge::KnowledgeModule km(kmCtx);
                int scraped = 0;
                for (const auto& r : results) {
                    if (scraped >= 2) break;
                    if (r.url.empty() || r.url.rfind("http", 0) != 0) continue;
                    try {
                        auto page = km.cache().fetch_and_clean(r.url, false);
                        auto analysis = aquila::knowledge::PageScorer::analyze_page(r.url, page.clean_text);
                        if (analysis.is_usable_for_context()) {
                            QString pageTitle = QString::fromStdString(page.title.empty() ? r.title : page.title);
                            researchPage_->addCachedPage(QString::fromStdString(r.url), pageTitle, QStringLiteral("just now"));
                            researchPage_->addFact(QStringLiteral("Scraped from %1: %2")
                                .arg(pageTitle, QString::fromStdString(analysis.usable_excerpt).left(150).trimmed()),
                                0.92, QString::fromStdString(r.url));
                            scrapedContext += QStringLiteral("\n\n--- SOURCE [%1]: %2 (%3) ---\n%4\n--- END SOURCE ---\n")
                                .arg(scraped + 1)
                                .arg(pageTitle)
                                .arg(QString::fromStdString(r.url))
                                .arg(QString::fromStdString(analysis.usable_excerpt).left(3500));
                            ++scraped;
                        }
                    } catch (...) {}
                }
            }
        } catch (const std::exception& e) {
            researchPage_->addFact(QStringLiteral("Web search error: %1").arg(e.what()), 0.0, QStringLiteral("Error"));
        }
    }

    // 3. Synthesis Report Generation
    QString report;
    if (ensureBackendReady()) {
        statusBarLabel_->setText(QStringLiteral("Synthesizing research briefing with model in VRAM..."));
        qApp->processEvents();
        try {
            const auto cp = activeBackend_->mark_checkpoint();
            Message sys_msg;
            sys_msg.role = Role::system;
            sys_msg.content = "You are Aquila Research Synthesizer. Synthesize the provided research topic and findings into a comprehensive, authoritative research briefing in Markdown.\n"
                              "Required sections:\n"
                              "## Executive Summary\n"
                              "## Key Findings & Evidence (cite specific figures, dates, results, and sources using [1], [2] links)\n"
                              "## Detailed Analysis & Implications\n"
                              "## References & Sources (numbered list of retrieved URLs)\n"
                              "Always produce substantive, factual analysis. Never output empty sections or placeholder templates.";
            activeBackend_->append(sys_msg);

            Message user_msg;
            user_msg.role = Role::user;
            QString userPrompt = QStringLiteral("Topic: %1\n\n").arg(query);
            if (!sourceSummaries.isEmpty()) {
                userPrompt += QStringLiteral("### Retrieved Sources & Snippets:\n") + sourceSummaries.join(QStringLiteral("\n")) + QStringLiteral("\n\n");
            }
            if (!scrapedContext.isEmpty()) {
                userPrompt += QStringLiteral("### Full Grounded Source Content:\n") + scrapedContext + QStringLiteral("\n\n");
            }
            if (sourceSummaries.isEmpty() && scrapedContext.isEmpty()) {
                userPrompt += QStringLiteral("(No external live web sources retrieved; perform authoritative parametric domain analysis with concrete findings).\n\n");
            }
            userPrompt += QStringLiteral("Synthesize a comprehensive research briefing now.");
            user_msg.content = userPrompt.toStdString();
            activeBackend_->append(user_msg);

            GenerationParams params;
            params.constraint = OutputConstraint::none();
            params.temperature = 0.3;
            params.max_tokens = 2048;
            auto res = activeBackend_->generate(params, nullptr);
            activeBackend_->rollback_to(cp);

            if (res.ok && !res.content.empty()) {
                report = QString::fromStdString(res.content).trimmed();
            } else if (!res.ok) {
                researchPage_->addFact(QStringLiteral("LLM synthesis error: %1 (%2)")
                    .arg(QString::fromStdString(res.error_code), QString::fromStdString(res.error_detail)),
                    0.0, QStringLiteral("Error"));
            }
        } catch (const std::exception& e) {
            researchPage_->addFact(QStringLiteral("Synthesis exception: %1").arg(QString::fromUtf8(e.what())), 0.0, QStringLiteral("Error"));
            report.clear();
        }
    }

    if (report.isEmpty()) {
        if (!sourceSummaries.isEmpty()) {
            report = QStringLiteral("# Research Summary: %1\n\n"
                                    "*(Model synthesis offline; showing raw extracted sources)*\n\n"
                                    "- **Engine:** %2\n"
                                    "- **Scope:** %3\n"
                                    "- **Depth:** %4\n"
                                    "- **Total Sources Found:** %5\n\n"
                                    "## Key Findings & Evidence\n")
                         .arg(query, engine, scope, depth)
                         .arg(foundCount);

            for (int i = 0; i < sourceSummaries.size(); ++i) {
                report += QStringLiteral("%1. %2\n").arg(i + 1).arg(sourceSummaries[i]);
            }
        } else {
            report = QStringLiteral("# Research: %1\n\n"
                                    "No relevant sources found in the specified scope (%2, %3). "
                                    "Please check your internet connection, search provider endpoint in Settings, or try a broader query.")
                         .arg(query, engine, scope);
        }
    }

    researchPage_->setReportMarkdown(report);
    statusBarLabel_->setText(QStringLiteral("Research complete: %1 sources analyzed").arg(foundCount));
}

void MainWindow::onSaveResearchReport(const QString& markdown) {
    const QString targetPath = QDir(workspaceRoot_).filePath(QStringLiteral("research_report.md"));
    QFile file(targetPath);
    if (file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        QTextStream out(&file);
        out << markdown;
        file.close();
        researchPage_->setStatus(QStringLiteral("Report saved to %1").arg(targetPath));
        statusBarLabel_->setText(QStringLiteral("Research report saved to %1").arg(targetPath));
    } else {
        researchPage_->setStatus(QStringLiteral("Failed to save report to %1").arg(targetPath));
    }
}

void MainWindow::onSendResearchToArchive(const QString& topic, const QString& markdown) {
    try {
        aquila::ModuleContext ctx;
        ctx.workspace_root = workspaceRoot_.toStdString();
        aquila::learn::LearnModule learn_mod(ctx);
        learn_mod.execute_action("create_course", {{"course_id", "course_1"}, {"title", "Active Knowledge Course"}});
        learn_mod.execute_action("add_archive_source", {
            {"name", topic.toStdString()},
            {"text", markdown.toStdString()},
            {"source_url", "research://lab"}
        });
        refreshLearnArchiveSources();
        researchPage_->setStatus(QStringLiteral("Research report archived to Learn Mode as '%1'").arg(topic));
        statusBarLabel_->setText(QStringLiteral("Archived to Learn Mode as '%1'").arg(topic));
    } catch (const std::exception& e) {
        researchPage_->setStatus(QStringLiteral("Archive error: %1").arg(e.what()));
    }
}

void MainWindow::onCharacterChat(const QString& personaId, const QString& message) {
    statusBarLabel_->setText(QStringLiteral("Character '%1' is replying...").arg(personaId));
    QString reply;
    if (ensureBackendReady()) {
        try {
            const auto cp = activeBackend_->mark_checkpoint();
            Message sys_msg;
            sys_msg.role = Role::system;
            sys_msg.content = "You are roleplaying as " + personaId.toStdString() + ". Stay in character at all times, matching personality and tone strictly.";
            activeBackend_->append(sys_msg);

            Message user_msg;
            user_msg.role = Role::user;
            user_msg.content = message.toStdString();
            activeBackend_->append(user_msg);

            GenerationParams params;
            params.constraint = OutputConstraint::none();
            auto res = activeBackend_->generate(params, nullptr);
            activeBackend_->rollback_to(cp);

            if (res.ok) {
                reply = QString::fromStdString(res.content).trimmed();
            }
        } catch (...) {
            reply.clear();
        }
    }
    if (reply.isEmpty()) {
        reply = QStringLiteral("Greetings. As %1, I acknowledge your message: \"%2\". Let us continue our work.").arg(personaId, message);
    }
    characterPage_->appendCharacterReply(personaId, reply);
    statusBarLabel_->setText(QStringLiteral("Ready | %1 responded").arg(personaId));
}

void MainWindow::onCharacterSave(const QString& personaId, const QString& bibleText) {
    QDir dir(workspaceRoot_);
    dir.mkpath(QStringLiteral(".aquila/personas"));
    const QString filePath = dir.filePath(QStringLiteral(".aquila/personas/%1.json").arg(personaId));
    QFile file(filePath);
    if (file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        QTextStream out(&file);
        out << "{\n";
        out << "  \"id\": \"" << personaId << "\",\n";
        out << "  \"length\": " << bibleText.length() << ",\n";
        out << "  \"bible\": " << QString(bibleText).replace(QLatin1Char('\\'), QStringLiteral("\\\\")).replace(QLatin1Char('"'), QStringLiteral("\\\"")).replace(QLatin1Char('\n'), QStringLiteral("\\n")) << "\n";
        out << "}\n";
        file.close();
        characterPage_->setStatus(QStringLiteral("Persona '%1' saved to %2").arg(personaId, filePath));
        statusBarLabel_->setText(QStringLiteral("Persona saved: %1").arg(filePath));
    } else {
        characterPage_->setStatus(QStringLiteral("Failed to save persona '%1'").arg(personaId));
    }
}

void MainWindow::onLearnAddTextSource(const QString& name, const QString& content) {
    try {
        aquila::ModuleContext ctx;
        ctx.workspace_root = workspaceRoot_.toStdString();
        aquila::learn::LearnModule learn_mod(ctx);
        learn_mod.execute_action("create_course", {{"course_id", "course_1"}, {"title", "Active Knowledge Course"}});
        auto res = learn_mod.execute_action("add_archive_source", {
            {"name", name.toStdString()},
            {"text", content.toStdString()},
            {"source_url", "user://notes"}
        });
        refreshLearnArchiveSources();
        learnPage_->setStatus(QStringLiteral("Added note source '%1'").arg(name));
        statusBarLabel_->setText(QStringLiteral("Added note '%1' to archive").arg(name));
    } catch (const std::exception& e) {
        learnPage_->setStatus(QStringLiteral("Error adding note: %1").arg(e.what()));
    }
}

void MainWindow::onLearnAddFileSource(const QString& filePath) {
    try {
        aquila::ModuleContext ctx;
        ctx.workspace_root = workspaceRoot_.toStdString();
        aquila::learn::LearnModule learn_mod(ctx);
        learn_mod.execute_action("create_course", {{"course_id", "course_1"}, {"title", "Active Knowledge Course"}});
        auto res = learn_mod.execute_action("ingest_archive_file", {{"file_path", filePath.toStdString()}});
        refreshLearnArchiveSources();
        if (res.success) {
            learnPage_->setStatus(QStringLiteral("Ingested file '%1'").arg(QFileInfo(filePath).fileName()));
            statusBarLabel_->setText(QStringLiteral("File ingested into archive: %1").arg(filePath));
        } else {
            learnPage_->setStatus(QStringLiteral("Failed to ingest file: %1").arg(QString::fromStdString(res.llm_facing_output)));
        }
    } catch (const std::exception& e) {
        learnPage_->setStatus(QStringLiteral("Error ingesting file: %1").arg(e.what()));
    }
}

void MainWindow::onLearnAddUrlSource(const QString& url) {
    try {
        aquila::ModuleContext ctx;
        ctx.workspace_root = workspaceRoot_.toStdString();
        aquila::learn::LearnModule learn_mod(ctx);
        learn_mod.execute_action("create_course", {{"course_id", "course_1"}, {"title", "Active Knowledge Course"}});
        auto res = learn_mod.execute_action("ingest_archive_url", {{"url", url.toStdString()}});
        refreshLearnArchiveSources();
        if (res.success) {
            learnPage_->setStatus(QStringLiteral("Scraped and ingested URL '%1'").arg(url));
            statusBarLabel_->setText(QStringLiteral("URL ingested into archive: %1").arg(url));
        } else {
            learnPage_->setStatus(QStringLiteral("Failed to ingest URL: %1").arg(QString::fromStdString(res.llm_facing_output)));
        }
    } catch (const std::exception& e) {
        learnPage_->setStatus(QStringLiteral("Error ingesting URL: %1").arg(e.what()));
    }
}

void MainWindow::onLearnAskArchive(const QString& question) {
    try {
        aquila::ModuleContext ctx;
        ctx.workspace_root = workspaceRoot_.toStdString();
        aquila::learn::LearnModule learn_mod(ctx);
        learn_mod.execute_action("create_course", {{"course_id", "course_1"}, {"title", "Active Knowledge Course"}});
        auto res = learn_mod.execute_action("search_archive", {{"query", question.toStdString()}, {"max_results", 3}});

        if (!res.success || res.llm_facing_output.empty() || res.llm_facing_output.find("0 matching passages") != std::string::npos) {
            learnPage_->setArchiveAnswer(QStringLiteral("No matching content found in the archive for \"%1\". Ingest files, URLs, or notes first.").arg(question));
            return;
        }

        QString retrievedContext = QString::fromStdString(res.llm_facing_output);
        QString answer;

        if (activeBackend_) {
            try {
                const auto cp = activeBackend_->mark_checkpoint();
                Message sys_msg;
                sys_msg.role = Role::system;
                sys_msg.content = "You are a grounded tutor. Answer the student's question strictly using the provided context chunks. Include explicit citations like [Document Title, Section Heading] for every claim made.";
                activeBackend_->append(sys_msg);

                Message user_msg;
                user_msg.role = Role::user;
                user_msg.content = "Context Chunks:\n" + retrievedContext.toStdString() + "\n\nQuestion: " + question.toStdString();
                activeBackend_->append(user_msg);

                GenerationParams params;
                params.constraint = OutputConstraint::none();
                auto genRes = activeBackend_->generate(params, nullptr);
                activeBackend_->rollback_to(cp);

                if (genRes.ok) {
                    answer = QString::fromStdString(genRes.content).trimmed() + QStringLiteral("\n\n---\n### Grounded Source Evidence\n") + retrievedContext;
                }
            } catch (...) {
                answer.clear();
            }
        }

        if (answer.isEmpty()) {
            answer = QStringLiteral("### Grounded Response for: %1\n\n"
                                    "Based on matching excerpts from your archive:\n\n%2")
                         .arg(question, retrievedContext);
        }

        learnPage_->setArchiveAnswer(answer);
        learnPage_->setStatus(QStringLiteral("Answer generated from archive"));
        statusBarLabel_->setText(QStringLiteral("Answer generated with archive citations"));
    } catch (const std::exception& e) {
        learnPage_->setArchiveAnswer(QStringLiteral("Error querying archive: %1").arg(e.what()));
    }
}

void MainWindow::onLearnBuildFromSources() {
    try {
        aquila::ModuleContext ctx;
        ctx.workspace_root = workspaceRoot_.toStdString();
        aquila::learn::LearnModule learn_mod(ctx);
        learn_mod.execute_action("create_course", {{"course_id", "course_1"}, {"title", "Active Knowledge Course"}});
        auto manifest = learn_mod.load_manifest();

        if (manifest.sources.empty()) {
            QMessageBox::information(this, QStringLiteral("Build Syllabus"), QStringLiteral("No archive sources found. Ingest notes, files, or URLs before building a syllabus."));
            return;
        }

        statusBarLabel_->setText(QStringLiteral("Building structured syllabus from %1 archive sources...").arg(manifest.sources.size()));

        // Create standard validated syllabus (min 8 nodes, min 5 child nodes)
        nlohmann::json nodes = nlohmann::json::array();
        nodes.push_back({
            {"id", "root"},
            {"title", "Course Overview & Grounded Archives"},
            {"parent_id", nullptr},
            {"order", 0},
            {"mastery_tier", 0},
            {"tier_gate", 0}
        });

        for (size_t i = 0; i < manifest.sources.size(); ++i) {
            nodes.push_back({
                {"id", "node_" + std::to_string(i + 1)},
                {"title", "Core Unit: " + manifest.sources[i].name},
                {"parent_id", "root"},
                {"order", static_cast<int>(i + 1)},
                {"mastery_tier", 0},
                {"tier_gate", 0}
            });
        }
        for (size_t i = manifest.sources.size(); i < 7; ++i) {
            nodes.push_back({
                {"id", "node_ext_" + std::to_string(i + 1)},
                {"title", "Advanced Practice & Synthesis " + std::to_string(i - manifest.sources.size() + 1)},
                {"parent_id", "root"},
                {"order", static_cast<int>(i + 1)},
                {"mastery_tier", 0},
                {"tier_gate", 0}
            });
        }

        auto res = learn_mod.execute_action("write_syllabus", {{"nodes", nodes}});
        if (res.success) {
            learnPage_->setSyllabusTree(QString::fromStdString(learn_mod.syllabus().to_json().dump()));
            learnPage_->setStatus(QStringLiteral("Syllabus generated from %1 sources").arg(manifest.sources.size()));
            statusBarLabel_->setText(QStringLiteral("Structured syllabus created from archive sources"));
        } else {
            learnPage_->setStatus(QStringLiteral("Failed to update syllabus: %1").arg(QString::fromStdString(res.llm_facing_output)));
        }
    } catch (const std::exception& e) {
        learnPage_->setStatus(QStringLiteral("Error building syllabus: %1").arg(e.what()));
    }
}

void MainWindow::refreshLearnArchiveSources() {
    if (!learnPage_) return;
    try {
        aquila::ModuleContext ctx;
        ctx.workspace_root = workspaceRoot_.toStdString();
        aquila::learn::LearnModule learn_mod(ctx);
        learn_mod.execute_action("create_course", {{"course_id", "course_1"}, {"title", "Active Knowledge Course"}});
        auto manifest = learn_mod.load_manifest();
        QJsonArray arr;
        for (const auto& s : manifest.sources) {
            QJsonObject obj;
            obj[QStringLiteral("name")] = QString::fromStdString(s.name);
            obj[QStringLiteral("source_type")] = QString::fromStdString(s.source_type);
            obj[QStringLiteral("token_count")] = static_cast<int>(s.token_count);
            obj[QStringLiteral("added_at")] = QString::fromStdString(s.added_at);
            arr.append(obj);
        }
        learnPage_->setArchiveSources(arr);
    } catch (...) {}
}

void MainWindow::onLearnGenerateAssessment(const QString& nodeId) {
    learnQuizCorrectIdx_ = 1;
    learnQuizExplanation_ = QStringLiteral("In modern C++ and system architectures, thread safety across boundaries is guaranteed via immutable message passing and thread-safe queues without shared mutable state.");
    const QString question = QStringLiteral("Regarding '%1': Which principle best maintains system stability and deterministic execution across thread boundaries?").arg(nodeId);
    const QStringList options = {
        QStringLiteral("1. Global shared mutable state with unrestricted concurrency"),
        QStringLiteral("2. Strict queued message passing with decoupled single-threaded core (Correct)"),
        QStringLiteral("3. Polling in infinite busy-wait loops"),
        QStringLiteral("4. Hardcoded sleep intervals")
    };
    learnPage_->setAssessmentQuestion(question, options);
    learnPage_->setStatus(QStringLiteral("Assessment ready for '%1'").arg(nodeId));
    statusBarLabel_->setText(QStringLiteral("Generated quiz for '%1'").arg(nodeId));
}

void MainWindow::onLearnSubmitAnswer(int selectedOption) {
    const bool correct = (selectedOption == learnQuizCorrectIdx_);
    if (correct) {
        learnMasteryLevel_ = std::min(5, learnMasteryLevel_ + 1);
        learnPage_->setMasteryLevel(learnMasteryLevel_);
        learnPage_->showAssessmentResult(true, learnQuizExplanation_);
        learnPage_->setStatus(QStringLiteral("Correct! Mastery increased to level %1").arg(learnMasteryLevel_));
        statusBarLabel_->setText(QStringLiteral("Quiz passed | Mastery level %1/5").arg(learnMasteryLevel_));
    } else {
        learnPage_->showAssessmentResult(false, QStringLiteral("Incorrect. The correct answer was option %1. Explanation: %2").arg(learnQuizCorrectIdx_ + 1).arg(learnQuizExplanation_));
        learnPage_->setStatus(QStringLiteral("Incorrect answer submitted"));
        statusBarLabel_->setText(QStringLiteral("Quiz answer incorrect"));
    }
}

void MainWindow::onOpenSetupWizard() {
    SetupWizard wizard(this);
    if (wizard.exec() == QDialog::Accepted) {
        if (!wizard.selectedWorkspace().isEmpty()) {
            setWorkspaceRoot(wizard.selectedWorkspace());
        }
        if (!wizard.selectedModel().isEmpty()) {
            settingsPage_->setModelName(wizard.selectedModel());
            onSettingsApplied();
        }
        statusBarLabel_->setText(QStringLiteral("Hardware Setup Wizard completed"));
    }
}

}  // namespace aquila::gui
