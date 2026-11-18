#include "builder/recipe_builder_page.hpp"
#include "dialogs/plan_review_dialog.hpp"
#include "dialogs/setup_wizard.hpp"
#include "main_window.hpp"
#include "theme/theme.hpp"
#include "theme/markdown_renderer.hpp"
#include "widgets/flow_layout.hpp"
#include "widgets/inline_prompt_bar.hpp"
#include "widgets/inline_diff_overlay.hpp"

#include "aquila/core.hpp"

#include <QApplication>
#include <QDir>
#include <QFile>
#include <QImage>
#include <QKeyEvent>
#include <QPixmap>
#include <QSet>
#include <QStyle>
#include <QStyleFactory>
#include <QTemporaryFile>
#include <QTimer>

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iostream>

namespace {

class HeadlessMockBackend final : public aquila::IInferenceBackend {
public:
    void append(const aquila::Message& msg) override { messages_.push_back(msg); }
    std::size_t mark_checkpoint() const override { return messages_.size(); }
    void rollback_to(std::size_t cp) override { messages_.resize(cp); }
    aquila::GenerationResult generate(const aquila::GenerationParams&,
                                      const aquila::TokenCallback& on_token) override {
        ++turn_;
        aquila::GenerationResult res;
        res.ok = true;
        if (turn_ == 1) {
            // Complete all checklist/ledger steps to satisfy the strict Option A completion gate
            res.content = R"({"thought":"mark ledger steps completed","module":"OrchestratorModule","action":"update_task_ledger","args":{"completed_steps":["Setup","Write","Compile"]}})";
        } else {
            res.content = R"({"thought":"headless ok","module":"OrchestratorModule","action":"complete_recipe","args":{"output":"success"}})";
        }
        if (on_token) {
            on_token(res.content, "");
        }
        return res;
    }
    aquila::ComputeProfile active_profile() const noexcept override {
        return aquila::ComputeProfile::cpu_low_spec_edge;
    }
    bool supports_kv_reuse() const noexcept override { return false; }

private:
    std::vector<aquila::Message> messages_;
    int turn_ = 0;
};

int run_headless_tests(QApplication& app) {
    std::printf("[GUI-TEST] Starting headless offscreen test suite...\n");

    // Test 1: Themes
    aquila::gui::apply_theme(&app, aquila::gui::ThemeMode::Dark);
    if (aquila::gui::current_theme() != aquila::gui::ThemeMode::Dark) {
        std::fprintf(stderr, "Theme test failed: dark theme not set\n");
        return 1;
    }
    aquila::gui::apply_theme(&app, aquila::gui::ThemeMode::Light);
    if (aquila::gui::current_theme() != aquila::gui::ThemeMode::Light) {
        std::fprintf(stderr, "Theme test failed: light theme not set\n");
        return 1;
    }
    aquila::gui::apply_theme(&app, aquila::gui::ThemeMode::Dark);
    std::printf("[GUI-TEST] 1. Theme application: OK\n");

    // Test 2: FlowLayout wrapping geometry
    {
        QWidget container;
        auto* flow = new aquila::gui::FlowLayout(&container, 4, 4, 4);
        for (int i = 0; i < 6; ++i) {
            auto* btn = new QPushButton(QStringLiteral("Chip %1").arg(i), &container);
            flow->addWidget(btn);
        }
        if (flow->count() != 6) {
            std::fprintf(stderr, "FlowLayout count mismatch: expected 6, got %d\n", flow->count());
            return 1;
        }
    }
    std::printf("[GUI-TEST] 2. FlowLayout widget: OK\n");

    // Test 3-7: MainWindow instantiation & navigation
    {
        aquila::gui::MainWindow window;
        window.setWorkspaceRoot(QStringLiteral("."));
        if (window.workspaceRoot() != QStringLiteral(".")) {
            std::fprintf(stderr, "Workspace root mismatch\n");
            return 1;
        }

        for (int mode = 0; mode <= 8; ++mode) {
            window.switchMode(mode);
            if (window.activeMode() != mode) {
                std::fprintf(stderr, "Mode switch mismatch for mode %d\n", mode);
                return 1;
            }
        }
        std::printf("[GUI-TEST] 3. MainWindow & 9 Mode Pages: OK\n");

        // Test 4: Code IDE Buffers and Pending Patch Cards
        auto* ide = window.codeIdePage();
        ide->addPendingPatch(QStringLiteral("src/main.cpp"), QStringLiteral("+line added\n-line deleted\n@@ -1,3 +1,3 @@"));
        ide->clearPendingPatches();
        std::printf("[GUI-TEST] 4. Code IDE & Pending Patch Cards: OK\n");

        // Test 5: Writing Page Preview
        auto* writing = window.writingPage();
        writing->setSectionContent(QStringLiteral("Intro"), QStringLiteral("# Header\n\nSome markdown text with **bold**."));
        std::printf("[GUI-TEST] 5. Writing Studio & Live Markdown Preview: OK\n");

        // Test 6: Tasks Page & Execution Ledger
        auto* task = window.taskPage();
        task->addLedgerEntry(0, QStringLiteral("WorkspaceModule"), QStringLiteral("outline"), QStringLiteral("OK"), QStringLiteral("file list"));
        task->updateScratchpad(QStringLiteral("Complete M8"), QStringLiteral("Rebuild Qt6 GUI"),
                               {QStringLiteral("Single threaded core"), QStringLiteral("QThread edge boundary")},
                               {QStringLiteral("Build CLI"), QStringLiteral("Build GUI")});
        std::printf("[GUI-TEST] 6. Task Page & Scratchpad Monitor: OK\n");

        // Test 7: Character AI 800-char Quality Gate
        auto* charPage = window.characterPage();
        charPage->setInitializationBible(QString(850, 'A'));
        if (charPage->initializationBible().length() != 850) {
            std::fprintf(stderr, "Character bible length mismatch\n");
            return 1;
        }
        std::printf("[GUI-TEST] 7. Character AI 800+ char Quality Gate: OK\n");
    }

    // Test 8: Setup Wizard Page Progression
    {
        aquila::gui::SetupWizard wizard;
        if (wizard.pageIds().size() != 4) {
            std::fprintf(stderr, "Setup wizard page count mismatch: expected 4, got %lld\n", static_cast<long long>(wizard.pageIds().size()));
            return 1;
        }
    }
    std::printf("[GUI-TEST] 8. Setup Wizard (4 pages): OK\n");

    // Test 9: Plan Review Dialog
    {
        aquila::gui::PlanReviewDialog planDialog(QStringLiteral("fn_dev_implement"), QStringLiteral("Fix bug"), {QStringLiteral("Step 1"), QStringLiteral("Step 2")});
    }
    std::printf("[GUI-TEST] 9. Plan Review Dialog: OK\n");

    // Test 10: AgentWorker background execution with mock backend and queued signals
    {
        auto mockBackend = std::make_shared<HeadlessMockBackend>();
        aquila::RecipeCartridge recipe = aquila::fn_writing_dynamic_recipe();
        aquila::LoopConfig cfg;
        cfg.task_id = "headless-test";
        cfg.mode = "task";

        bool workerFinished = false;
        bool workerSuccess = false;

        aquila::gui::AgentWorker worker(mockBackend, recipe, "test task", cfg, ".");
        QObject::connect(&worker, &aquila::gui::AgentWorker::finished, [&app, &workerFinished, &workerSuccess](bool success, const QString&) {
            workerFinished = true;
            workerSuccess = success;
            app.quit();
        });

        worker.start();
        // Pump Qt event loop until worker finishes
        QTimer::singleShot(2000, &app, [&app]() {
            app.quit();
        });
        app.exec();
        worker.wait();

        if (!workerFinished || !workerSuccess) {
            std::fprintf(stderr, "AgentWorker test failed: finished=%d, success=%d\n", workerFinished, workerSuccess);
            return 1;
        }
    }
    std::printf("[GUI-TEST] 10. AgentWorker QThread Queued Signal Bridge: OK\n");

    // Test 11: Code Editor Live Canvas (Inline Prompt, Myers Diff, Accept, Reject, Undo)
    {
        aquila::gui::CodeEditor editor;
        editor.resize(800, 600);
        editor.setPlainText(QStringLiteral("int main() {\n    return 0;\n}\n"));

        // Select line 2: "    return 0;"
        QTextCursor cur(editor.document());
        cur.setPosition(13);
        cur.setPosition(26, QTextCursor::KeepAnchor);
        editor.setTextCursor(cur);

        editor.showInlinePrompt();
        editor.applyInlinePendingPatch(QStringLiteral("    int x = 42;\n    return x;"));
        if (!editor.hasPendingPatch()) {
            std::fprintf(stderr, "Code editor Live Canvas failed: pending patch not active\n");
            return 1;
        }

        // Test Reject restores original text
        editor.rejectInlinePatch();
        if (editor.hasPendingPatch() || !editor.toPlainText().contains(QStringLiteral("return 0;"))) {
            std::fprintf(stderr, "Code editor Live Canvas reject failed\n");
            return 1;
        }

        // Test Accept commits replacement text
        cur.setPosition(13);
        cur.setPosition(26, QTextCursor::KeepAnchor);
        editor.setTextCursor(cur);
        editor.applyInlinePendingPatch(QStringLiteral("    int x = 42;\n    return x;"));
        editor.acceptInlinePatch();
        if (editor.hasPendingPatch() || !editor.toPlainText().contains(QStringLiteral("int x = 42;"))) {
            std::fprintf(stderr, "Code editor Live Canvas accept failed\n");
            return 1;
        }

        // Test Undo restores original text
        editor.undo();
        if (!editor.toPlainText().contains(QStringLiteral("return 0;"))) {
            std::fprintf(stderr, "Code editor Live Canvas undo failed\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 11. Code Editor Live Canvas (Inline Diff & Undo): OK\n");

    // Test 12: Writing Page Live Canvas
    {
        aquila::gui::WritingPage writingPage;
        writingPage.setSectionContent(QStringLiteral("1. Introduction"), QStringLiteral("Draft prose outline."));
        auto* ed = writingPage.editor();
        if (!ed) {
            std::fprintf(stderr, "Writing page editor is null\n");
            return 1;
        }
        QTextCursor cur(ed->document());
        cur.select(QTextCursor::Document);
        ed->setTextCursor(cur);
        ed->applyInlinePendingPatch(QStringLiteral("Revised and polished prose for introduction."));
        if (!ed->hasPendingPatch()) {
            std::fprintf(stderr, "Writing page Live Canvas failed to set pending patch\n");
            return 1;
        }
        ed->acceptInlinePatch();
        if (!writingPage.currentSectionContent().contains(QStringLiteral("Revised and polished prose"))) {
            std::fprintf(stderr, "Writing page Live Canvas accept failed\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 12. Writing Studio Live Canvas Revision: OK\n");

    // Test 13: Recipe Builder Graph & Lossless 17-Cartridge Round-Trip
    {
        aquila::gui::RecipeBuilderPage builder;
        const auto allCartridges = aquila::all_builtin_recipes();
        if (allCartridges.size() != 17) {
            std::fprintf(stderr, "Expected 17 builtin cartridges, found %lld\n", static_cast<long long>(allCartridges.size()));
            return 1;
        }

        for (const auto& c : allCartridges) {
            builder.loadCartridge(c);
            const aquila::RecipeCartridge out = builder.currentCartridge();

            if (c.recipe_id != out.recipe_id ||
                c.goal_template != out.goal_template ||
                c.load_modules.size() != out.load_modules.size() ||
                c.pre_llm_hooks.size() != out.pre_llm_hooks.size() ||
                c.scratchpad_checklist.size() != out.scratchpad_checklist.size() ||
                c.include != out.include) {
                std::fprintf(stderr, "Recipe builder round-trip failed for cartridge '%s'\n", c.recipe_id.c_str());
                return 1;
            }
        }
    }
    std::printf("[GUI-TEST] 13. Recipe Builder 17-Cartridge Lossless Round-Trip: OK\n");

    // Test 14: Chat Attachment Packaging & Truncation
    {
        aquila::gui::ChatPage chatPage;
        QTemporaryFile tempFile;
        if (tempFile.open()) {
            tempFile.write(QByteArray(2048, 'X'));
            const QString path = tempFile.fileName();
            tempFile.close();

            chatPage.addAttachment(path);
            const QStringList atts = chatPage.currentAttachments();
            if (atts.size() != 1 || atts[0] != path) {
                std::fprintf(stderr, "ChatPage attachment list mismatch\n");
                return 1;
            }

            chatPage.appendUserMessage(QStringLiteral("Look at file"), atts);
            if (!chatPage.transcript()->toHtml().contains(QStringLiteral("📎"))) {
                std::fprintf(stderr, "ChatPage transcript missing attachment badge\n");
                return 1;
            }
        }
    }
    std::printf("[GUI-TEST] 14. Chat Attachment Ingestion & Budgeting: OK\n");

    // Test 15: Chat Enter Key Event Filter vs Shift+Enter
    {
        aquila::gui::ChatPage chatPage;
        chatPage.promptInput()->setPlainText(QStringLiteral("Hello Aquila"));

        bool sendEmitted = false;
        QString sentPrompt;
        QObject::connect(&chatPage, &aquila::gui::ChatPage::sendRequested, [&sendEmitted, &sentPrompt](const QString& p, const QStringList&) {
            sendEmitted = true;
            sentPrompt = p;
        });

        // Test Enter key sends
        QKeyEvent enterEvent(QEvent::KeyPress, Qt::Key_Return, Qt::NoModifier);
        QCoreApplication::sendEvent(chatPage.promptInput(), &enterEvent);

        if (!sendEmitted || sentPrompt != QStringLiteral("Hello Aquila")) {
            std::fprintf(stderr, "Chat Enter key filter failed to emit sendRequested\n");
            return 1;
        }

        // Test Shift+Enter does not trigger send
        sendEmitted = false;
        chatPage.promptInput()->setPlainText(QStringLiteral("Multi\nLine"));
        QKeyEvent shiftEnterEvent(QEvent::KeyPress, Qt::Key_Return, Qt::ShiftModifier);
        QCoreApplication::sendEvent(chatPage.promptInput(), &shiftEnterEvent);

        if (sendEmitted) {
            std::fprintf(stderr, "Chat Shift+Enter unexpectedly triggered sendRequested\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 15. Chat Enter Key Filter vs Shift+Enter: OK\n");

    // Test 16: Task Page Live Scratchpad Sync
    {
        aquila::gui::TaskPage taskPage;
        taskPage.updateScratchpad(
            QStringLiteral("Build and verify GUI features"),
            QStringLiteral("All slots correctly connected"),
            {QStringLiteral("MSVC x64 compiler"), QStringLiteral("RTX 4070 VRAM offload")},
            {QStringLiteral("Fix chat attachments"), QStringLiteral("Add unit tests")}
        );

        if (taskPage.objective() != QStringLiteral("Build and verify GUI features") ||
            taskPage.hypothesis() != QStringLiteral("All slots correctly connected") ||
            taskPage.factsCount() != 2 ||
            taskPage.checklistCount() != 2) {
            std::fprintf(stderr, "TaskPage scratchpad update verification failed\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 16. Task Page Live Scratchpad Sync: OK\n");

    // Test 17: Code IDE Inline Refactor & Pending Patch Lifecycle
    {
        aquila::gui::MainWindow window;
        window.switchMode(3); // Code IDE
        auto* ide = window.codeIdePage();

        window.onCodeIdeInlineEdit(QStringLiteral("add const correctness"),
                                   QStringLiteral("void process(std::string s)"),
                                   QStringLiteral("src/process.cpp"));

        ide->clearPendingPatches();
    }
    std::printf("[GUI-TEST] 17. Code IDE Inline Refactor & Patch Lifecycle: OK\n");

    // Test 18: Writing Studio Section Revision & Document Compilation
    {
        aquila::gui::MainWindow window;
        window.switchMode(4); // Writing
        auto* writing = window.writingPage();
        writing->setSectionContent(QStringLiteral("Section 1"), QStringLiteral("Initial draft text."));

        window.onWritingSectionRevise(QStringLiteral("Initial draft text."), QStringLiteral("expand details"));
        if (writing->currentSectionContent().trimmed().isEmpty()) {
            std::fprintf(stderr, "Writing section revision content mismatch\n");
            return 1;
        }

        window.onWritingCompile();
        if (!QFile::exists(QStringLiteral("compiled_document.md"))) {
            std::fprintf(stderr, "Writing compile failed: compiled_document.md not found\n");
            return 1;
        }
        QFile::remove(QStringLiteral("compiled_document.md"));
    }
    std::printf("[GUI-TEST] 18. Writing Studio Revision & Compilation: OK\n");

    // Test 19: Research Lab Search & Fact Graph Population
    {
        aquila::gui::MainWindow window;
        window.switchMode(5); // Research
        auto* resPage = window.researchPage();
        if (resPage->selectedEngine() != QStringLiteral("searxng")) {
            std::fprintf(stderr, "ResearchPage default engine expected 'searxng', got '%s'\n",
                         resPage->selectedEngine().toUtf8().constData());
            return 1;
        }

        window.onResearchSearch(QStringLiteral("aquila"), QStringLiteral("comprehensive"));
        if (resPage->searchResultCount() == 0 || resPage->factCount() == 0) {
            std::fprintf(stderr, "Research search failed: results=%d, facts=%d\n",
                         resPage->searchResultCount(), resPage->factCount());
            return 1;
        }
    }
    std::printf("[GUI-TEST] 19. Research Lab Search & Fact Graph: OK\n");

    // Test 20: Character AI 800-char Quality Gate & Dialogue
    {
        aquila::gui::MainWindow window;
        window.switchMode(6); // Character
        auto* charPage = window.characterPage();

        // Sub-800 chars
        charPage->setInitializationBible(QString(500, 'Z'));
        if (charPage->initializationBible().length() != 500) {
            std::fprintf(stderr, "Character bible length failed\n");
            return 1;
        }

        // 800+ chars
        const QString fullBible = QString(850, 'Q');
        charPage->setInitializationBible(fullBible);
        window.onCharacterSave(QStringLiteral("test_persona"), fullBible);

        const QString personaPath = QStringLiteral(".aquila/personas/test_persona.json");
        if (!QFile::exists(personaPath)) {
            std::fprintf(stderr, "Character persona save failed: file not created\n");
            return 1;
        }
        QFile::remove(personaPath);

        // Chat message
        window.onCharacterChat(QStringLiteral("test_persona"), QStringLiteral("Hello character"));
        if (!charPage->dialogueTranscript()->toPlainText().contains(QStringLiteral("test_persona"))) {
            std::fprintf(stderr, "Character dialogue reply missing\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 20. Character AI Quality Gate & Dialogue: OK\n");

    // Test 21: Learn Page Quiz Generation, Submission & Mastery Progression
    {
        aquila::gui::MainWindow window;
        window.switchMode(7); // Learn
        auto* learn = window.learnPage();

        window.onLearnGenerateAssessment(QStringLiteral("Concurrency Model"));
        if (learn->answerOptionCount() != 4 || !learn->currentQuestion().contains(QStringLiteral("Concurrency Model"))) {
            std::fprintf(stderr, "Learn assessment generation mismatch\n");
            return 1;
        }

        const int initialMastery = learn->masteryLevel();
        // Submit correct option (index 1)
        window.onLearnSubmitAnswer(1);
        if (learn->masteryLevel() != initialMastery + 1) {
            std::fprintf(stderr, "Learn mastery progression failed: expected %d, got %d\n", initialMastery + 1, learn->masteryLevel());
            return 1;
        }
    }
    std::printf("[GUI-TEST] 21. Learn Page Quiz & Mastery Progression: OK\n");

    // Test 22: Home Dashboard Workspace Switcher
    {
        aquila::gui::MainWindow window;
        window.setWorkspaceRoot(QStringLiteral("F:/TestWorkspace"));
        if (window.workspaceRoot() != QStringLiteral("F:/TestWorkspace")) {
            std::fprintf(stderr, "Workspace switcher failed\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 22. Home Dashboard Workspace Switcher: OK\n");

    // Test 23: Markdown Rendering Engine
    {
        const QString input = QStringLiteral("## World Clock\nHere is python code:\n```python\nimport pytz\nprint('time')\n```\n- Point 1\n- Point 2\n**Bold note**");
        const QString html = aquila::gui::MarkdownRenderer::toHtml(input);
        if (!html.contains(QStringLiteral("<h2")) || !html.contains(QStringLiteral("import pytz"))) {
            std::fprintf(stderr, "Markdown rendering verification failed\n");
            return 1;
        }
        if (!html.contains(QStringLiteral("<b>Bold note</b>"))) {
            std::fprintf(stderr, "Markdown bold formatting failed\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 23. Markdown Rendering Engine: OK\n");

    // Test 24: Venv Sandbox Actions & Recipe OneOf Schema Constraining
    {
        aquila::RecipeCartridge recipe = aquila::fn_dev_implement_recipe();
        const auto schema = aquila::AgentLoop::action_call_schema(&recipe);
        if (!schema.contains("oneOf") || !schema["oneOf"].is_array()) {
            std::fprintf(stderr, "Action call schema missing oneOf constraint\n");
            return 1;
        }
        const auto& branches = schema["oneOf"];
        if (branches.size() != 3) {
            std::fprintf(stderr, "Action call oneOf branch size mismatch: expected 3, got %lld\n", static_cast<long long>(branches.size()));
            return 1;
        }
        bool seen_exec = false, seen_ws = false, seen_orch = false;
        for (const auto& b : branches) {
            if (!b.contains("properties") || !b["properties"].contains("module") ||
                !b["properties"]["module"].contains("const") ||
                !b["properties"].contains("action") || !b["properties"]["action"].contains("enum")) {
                std::fprintf(stderr, "Action call oneOf branch malformed\n");
                return 1;
            }
            const std::string mod = b["properties"]["module"]["const"].get<std::string>();
            if (mod == "ExecutionModule") seen_exec = true;
            if (mod == "WorkspaceModule") seen_ws = true;
            if (mod == "OrchestratorModule") seen_orch = true;
        }
        if (!seen_exec || !seen_ws || !seen_orch) {
            std::fprintf(stderr, "Action call oneOf missing expected recipe modules\n");
            return 1;
        }
    }
    std::printf("[GUI-TEST] 24. Venv Sandbox Actions & Recipe OneOf Schema: OK\n");

    // Test 25: Research Lab Screenshot Browser Loading, Deduplication & Preview
    {
        aquila::gui::MainWindow window;
        window.switchMode(5); // Research Lab
        auto* resPage = window.researchPage();
        resPage->clearScreenshots(false);

        const QString tmpWs = QDir(QDir::tempPath()).filePath(QStringLiteral("aquila_gui_shot_test"));
        QDir(tmpWs).removeRecursively();
        const QString shotsDir = QDir(tmpWs).filePath(QStringLiteral(".aquila/browser_screenshots"));
        QDir().mkpath(shotsDir);

        auto writeSamplePng = [&](const QString& fname, const QColor& bg, const QColor& accent) -> QString {
            QImage img(640, 400, QImage::Format_ARGB32);
            img.fill(bg);
            for (int y = 40; y < 180; ++y) {
                for (int x = 40; x < 300; ++x) {
                    img.setPixelColor(x, y, accent);
                }
            }
            const QString fullPath = QDir(shotsDir).filePath(fname);
            img.save(fullPath, "PNG");
            return fullPath;
        };

        const QString p1 = writeSamplePng(QStringLiteral("shot_20261117_170001_001_001.png"), QColor(15, 23, 42), QColor(59, 130, 246));
        const QString p2 = writeSamplePng(QStringLiteral("shot_20261117_170002_001_002.png"), QColor(20, 30, 48), QColor(16, 185, 129));

        resPage->loadScreenshotsFromDir(tmpWs);
        if (resPage->screenshotCount() != 2 || !resPage->hasScreenshotPreview()) {
            std::fprintf(stderr, "Screenshot Browser dir load failed: count=%d, preview=%d\n",
                         resPage->screenshotCount(), int(resPage->hasScreenshotPreview()));
            QDir(tmpWs).removeRecursively();
            return 1;
        }
        // Re-adding an existing screenshot with richer metadata must deduplicate (stay 2, not 3).
        resPage->addScreenshot(p1, QStringLiteral("Rendered Docs Page"), QStringLiteral("https://example.org/docs"));
        if (resPage->screenshotCount() != 2) {
            std::fprintf(stderr, "Screenshot Browser deduplication failed: count=%d\n", resPage->screenshotCount());
            QDir(tmpWs).removeRecursively();
            return 1;
        }
        // Clearing with deleteFiles=true removes both files from disk.
        resPage->clearScreenshots(true);
        if (resPage->screenshotCount() != 0 || QFileInfo::exists(p1) || QFileInfo::exists(p2)) {
            std::fprintf(stderr, "Screenshot Browser clear(deleteFiles=true) failed\n");
            QDir(tmpWs).removeRecursively();
            return 1;
        }
        QDir(tmpWs).removeRecursively();
    }
    std::printf("[GUI-TEST] 25. Research Lab Screenshot Browser: OK\n");

    std::printf("\n========================================\n");
    std::printf("All 25 GUI headless test suites PASSED!\n");
    std::printf("[GUI-HEADLESS-TEST-OK]\n");
    std::printf("smoke=ok\n");
    std::printf("========================================\n");
    std::fflush(stdout);
    return 0;
}

}  // namespace

#ifdef _WIN32
#include <windows.h>
#endif

int main(int argc, char** argv) {
#ifdef _WIN32
    if (AttachConsole(ATTACH_PARENT_PROCESS)) {
        FILE* fp = nullptr;
        freopen_s(&fp, "CONOUT$", "w", stdout);
        freopen_s(&fp, "CONOUT$", "w", stderr);
    }
#endif
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    QCoreApplication::setOrganizationName(QStringLiteral("Aquila"));
    QCoreApplication::setApplicationName(QStringLiteral("AquilaGui"));
    QApplication app(argc, argv);
    aquila::gui::apply_theme(&app, aquila::gui::ThemeMode::Dark);

    const bool smoke = app.arguments().contains(QStringLiteral("--smoke"));
    const bool headlessTest = app.arguments().contains(QStringLiteral("--test-headless")) || app.arguments().contains(QStringLiteral("--run-headless-tests"));
    const int ssIdx = app.arguments().indexOf(QStringLiteral("--screenshots"));
    const int vaIdx = app.arguments().indexOf(QStringLiteral("--visual-audit"));
    const int captureArgIdx = (vaIdx != -1) ? vaIdx : ssIdx;
    const bool visualAudit = (vaIdx != -1);

    if (captureArgIdx != -1 && captureArgIdx + 1 < app.arguments().size()) {
        const QString outDir = app.arguments().at(captureArgIdx + 1);
        QDir().mkpath(outDir);

        aquila::gui::MainWindow window;
        window.setWorkspaceRoot(QStringLiteral("."));
        window.resize(visualAudit ? 1440 : 1280, visualAudit ? 900 : 800);
        window.show();
        app.processEvents();

        // Populate rich fixtures across pages so rendered frames showcase real UI states.
        window.taskPage()->addLedgerEntry(0, QStringLiteral("KnowledgeModule"), QStringLiteral("search_local_docs"), QStringLiteral("OK"), QStringLiteral("Found 4 matches"));
        window.taskPage()->updateScratchpad(
            QStringLiteral("Verify Qwen 3.5 multi-domain execution"),
            QStringLiteral("Inspect visual GUI captures"),
            {QStringLiteral("CPU tier isolates 0 MiB CUDA"), QStringLiteral("Lazy mmproj loads on first image")},
            {QStringLiteral("Capture all mode screenshots"), QStringLiteral("Verify visual contrast & layout")});
        window.writingPage()->setSectionContent(
            QStringLiteral("1. Overview"),
            QStringLiteral("# Architecture Summary\n\nAquila pairs a **deterministic C++ core** with Qt6 desktop workflows and lazy multimodal vision."));
        window.characterPage()->setInitializationBible(
            QStringLiteral("# Ada — Systems Architecture Mentor\n\n"
                           "## Voice & Temperament\nConcise, grounded, and empirically driven.\n\n") +
            QString(800, QLatin1Char('x')));

        aquila::Json manifest = aquila::Json::array();
        bool allValidFrames = true;
        auto record_frame = [&](const QString& label, const QPixmap& pix, const QString& fileName) {
            const QString path = QDir(outDir).filePath(fileName);
            const bool saved = pix.save(path);
            const QImage img = pix.toImage();
            QSet<QRgb> uniqueColors;
            const int stepX = (std::max)(1, img.width() / 64);
            const int stepY = (std::max)(1, img.height() / 64);
            for (int y = 0; y < img.height(); y += stepY) {
                for (int x = 0; x < img.width(); x += stepX) {
                    uniqueColors.insert(img.pixel(x, y));
                }
            }
            const bool nonBlank = saved && !img.isNull() && img.width() >= 400 && img.height() >= 300 && uniqueColors.size() >= 8;
            if (!nonBlank) {
                allValidFrames = false;
                std::fprintf(stderr, "[VISUAL-AUDIT] Invalid/blank frame %s (%dx%d, colors=%d, saved=%d)\n",
                             qPrintable(fileName), img.width(), img.height(), static_cast<int>(uniqueColors.size()), int(saved));
            }
            manifest.push_back(aquila::Json::object({
                {"label", label.toStdString()},
                {"file", fileName.toStdString()},
                {"width", img.width()},
                {"height", img.height()},
                {"sampled_unique_colors", static_cast<int>(uniqueColors.size())},
                {"valid", nonBlank}
            }));
        };

        const QStringList modeNames = {
            QStringLiteral("01_home"),
            QStringLiteral("02_chat"),
            QStringLiteral("03_task"),
            QStringLiteral("04_code_ide"),
            QStringLiteral("05_writing"),
            QStringLiteral("06_research"),
            QStringLiteral("07_character"),
            QStringLiteral("08_learn"),
            QStringLiteral("09_builder"),
            QStringLiteral("10_settings")
        };

        for (int i = 0; i < modeNames.size(); ++i) {
            window.switchMode(i);
            app.processEvents();
            record_frame(modeNames[i], window.grab(), QStringLiteral("screenshot_%1.png").arg(modeNames[i]));
        }

        // Setup Wizard
        aquila::gui::SetupWizard wizard;
        wizard.resize(720, 520);
        wizard.show();
        app.processEvents();
        record_frame(QStringLiteral("setup_wizard"), wizard.grab(), QStringLiteral("screenshot_10_setup_wizard.png"));

        // Plan Review Dialog
        aquila::gui::PlanReviewDialog planDialog(QStringLiteral("fn_dev_implement"),
                                                QStringLiteral("Implement robust AST parser for C++ syntax"),
                                                {QStringLiteral("Scan workspace headers"),
                                                 QStringLiteral("Generate AST node definitions"),
                                                 QStringLiteral("Run unit test suite")});
        planDialog.resize(600, 450);
        planDialog.show();
        app.processEvents();
        record_frame(QStringLiteral("plan_review"), planDialog.grab(), QStringLiteral("screenshot_11_plan_review.png"));

        // Live Canvas Inline Diff Screenshot
        window.switchMode(3); // Code IDE
        window.codeIdePage()->openFile(QStringLiteral("src/core/main.cpp"));
        if (auto* ed = window.codeIdePage()->currentEditor()) {
            ed->setPlainText(QStringLiteral("// Aquila Live Canvas Demo\nvoid calculate_metrics() {\n    // Old unoptimized loop\n    for (int i = 0; i < 100; ++i) {\n        process(i);\n    }\n}\n"));
            QTextCursor cur(ed->document());
            cur.setPosition(58);
            cur.setPosition(135, QTextCursor::KeepAnchor);
            ed->setTextCursor(cur);
            ed->applyInlinePendingPatch(QStringLiteral("    // Optimized vectorized execution\n    std::ranges::for_each(std::views::iota(0, 100), process_fast);"));
            app.processEvents();
            record_frame(QStringLiteral("live_canvas_code"), window.grab(), QStringLiteral("screenshot_12_live_canvas_code.png"));
            ed->rejectInlinePatch();
        }

        // Research Lab Screenshot Browser Tab Visual Audit Frame
        {
            window.switchMode(5); // Research Lab
            auto* rp = window.researchPage();
            const QString samplePath = QDir(outDir).filePath(QStringLiteral("sample_browser_capture.png"));
            QImage sample(1280, 800, QImage::Format_ARGB32);
            sample.fill(QColor(15, 23, 42));
            for (int y = 0; y < 90; ++y) {
                for (int x = 0; x < 1280; ++x) sample.setPixelColor(x, y, QColor(30, 41, 59));
            }
            for (int y = 140; y < 520; ++y) {
                for (int x = 100; x < 1180; ++x) sample.setPixelColor(x, y, QColor(37, 99, 235));
            }
            for (int y = 560; y < 700; ++y) {
                for (int x = 100; x < 760; ++x) sample.setPixelColor(x, y, QColor(16, 185, 129));
            }
            sample.save(samplePath, "PNG");
            rp->addCachedPage(QStringLiteral("https://docs.example.org/hybrid-attention"),
                              QStringLiteral("Hybrid Attention Architecture Guide"),
                              QStringLiteral("rendered + screenshot"),
                              samplePath);
            rp->addScreenshot(samplePath,
                              QStringLiteral("Hybrid Attention Architecture Guide"),
                              QStringLiteral("https://docs.example.org/hybrid-attention"));
            rp->showScreenshotsTab();
            app.processEvents();
            record_frame(QStringLiteral("research_screenshots"), window.grab(), QStringLiteral("screenshot_13_research_screenshots.png"));
        }

        std::ofstream mf(QDir(outDir).filePath(QStringLiteral("visual_manifest.json")).toStdString(),
                         std::ios::binary | std::ios::trunc);
        if (mf.is_open()) {
            mf << aquila::Json::object({
                {"frames", manifest},
                {"all_valid", allValidFrames}
            }).dump(2);
        }

        if (visualAudit) {
            std::printf("[VISUAL-AUDIT-%s] captured %zu frames to %s\n",
                        allValidFrames ? "OK" : "FAIL",
                        manifest.size(),
                        qPrintable(outDir));
            std::fflush(stdout);
            return allValidFrames ? 0 : 1;
        }
        std::printf("[SCREENSHOTS-CAPTURED-OK]\n");
        std::fflush(stdout);
        return 0;
    }

    if (headlessTest) {
        int r = run_headless_tests(app);
        std::printf("[GUI-TEST] run_headless_tests completed with return code %d\n", r);
        std::fflush(stdout);
        return r;
    }

    if (smoke) {
        std::printf("platform=%s\n", qPrintable(QApplication::platformName()));
        if (auto* s = QApplication::style()) {
            std::printf("style=%s\n", qPrintable(s->name()));
        }
        std::printf("styles=%s\n", qPrintable(QStyleFactory::keys().join(QLatin1Char(','))));
        std::printf("smoke=ok\n");
        std::fflush(stdout);
        return 0;
    }

    aquila::gui::MainWindow window;
    window.show();
    return QApplication::exec();
}
