// apps/aquila_gui/main_window.hpp
#pragma once

#include "builder/recipe_builder_page.hpp"
#include "pages/character_page.hpp"
#include "pages/chat_page.hpp"
#include "pages/code_ide_page.hpp"
#include "pages/home_page.hpp"
#include "pages/learn_page.hpp"
#include "pages/research_page.hpp"
#include "pages/settings_page.hpp"
#include "pages/task_page.hpp"
#include "pages/writing_page.hpp"
#include "widgets/nav_rail.hpp"
#include "worker/agent_worker.hpp"

#include <QLabel>
#include <QMainWindow>
#include <QStackedWidget>

namespace aquila::gui {

class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit MainWindow(QWidget* parent = nullptr);
    ~MainWindow() override;

    void setWorkspaceRoot(const QString& path);
    QString workspaceRoot() const { return workspaceRoot_; }

    void switchMode(int index);
    int activeMode() const;

    HomePage* homePage() const { return homePage_; }
    ChatPage* chatPage() const { return chatPage_; }
    TaskPage* taskPage() const { return taskPage_; }
    CodeIdePage* codeIdePage() const { return codeIdePage_; }
    WritingPage* writingPage() const { return writingPage_; }
    ResearchPage* researchPage() const { return researchPage_; }
    CharacterPage* characterPage() const { return characterPage_; }
    LearnPage* learnPage() const { return learnPage_; }
    RecipeBuilderPage* builderPage() const { return builderPage_; }
    SettingsPage* settingsPage() const { return settingsPage_; }

public slots:
    void onThemeToggle();
    void onSleepCycle();
    void onChatSend(const QString& prompt, const QStringList& attachments);
    void onTaskRun(const QString& recipeId, const QString& prompt);
    void onCancelCurrentTask();
    void openCartridgeInBuilder(const QString& recipeId);
    void onSettingsApplied();
    void onBrowseWorkspace();
    void onCodeIdeInlineEdit(const QString& prompt, const QString& selectedText, const QString& filePath);
    void onWritingSectionRevise(const QString& sectionContent, const QString& instruction);
    void onWritingCompile();
    void onResearchSearch(const QString& query, const QString& depth);
    void onCharacterChat(const QString& personaId, const QString& message);
    void onCharacterSave(const QString& personaId, const QString& bibleText);
    void onLearnGenerateAssessment(const QString& nodeId);
    void onLearnSubmitAnswer(int selectedOption);
    void onOpenSetupWizard();

private:
    void setupUi();
    void setupConnections();
    std::shared_ptr<aquila::IInferenceBackend> createBackend();

    NavRailWidget* navRail_ = nullptr;
    QStackedWidget* pageStack_ = nullptr;

    HomePage* homePage_ = nullptr;
    ChatPage* chatPage_ = nullptr;
    TaskPage* taskPage_ = nullptr;
    CodeIdePage* codeIdePage_ = nullptr;
    WritingPage* writingPage_ = nullptr;
    ResearchPage* researchPage_ = nullptr;
    CharacterPage* characterPage_ = nullptr;
    LearnPage* learnPage_ = nullptr;
    RecipeBuilderPage* builderPage_ = nullptr;
    SettingsPage* settingsPage_ = nullptr;

    QLabel* topWorkspaceBadge_ = nullptr;
    QLabel* topModelBadge_ = nullptr;
    QLabel* topTierBadge_ = nullptr;
    QLabel* statusBarLabel_ = nullptr;

    QString workspaceRoot_ = ".";
    AgentWorker* activeWorker_ = nullptr;
    std::shared_ptr<aquila::IInferenceBackend> activeBackend_;

    int learnQuizCorrectIdx_ = 1;
    QString learnQuizExplanation_;
    int learnMasteryLevel_ = 1;
};

}  // namespace aquila::gui
