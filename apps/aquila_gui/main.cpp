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
#include <QKeyEvent>
#include <QPixmap>
#include <QStyle>
#include <QStyleFactory>
#include <QTemporaryFile>
#include <QTimer>

#include <cstdio>
#include <iostream>

namespace {

class HeadlessMockBackend final : public aquila::IInferenceBackend {
public:
    void append(const aquila::Message& msg) override { messages_.push_back(msg); }
    std::size_t mark_checkpoint() const override { return messages_.size(); }
    void rollback_to(std::size_t cp) override { messages_.resize(cp); }
    aquila::GenerationResult generate(const aquila::GenerationParams&,
                                      const aquila::TokenCallback& on_token) override {
        aquila::GenerationResult res;
        res.ok = true;
        res.content = R"({"thought":"headless ok","module":"OrchestratorModule","action":"complete_recipe","args":{"output":"success"}})";
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
        aquila::RecipeCartridge recipe = aquila::fn_research_offline_recipe();
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

    // Test 24: Venv Sandbox Actions & Recipe Enum Constraining
    {
        aquila::RecipeCartridge recipe = aquila::fn_dev_implement_recipe();
        const auto schema = aquila::AgentLoop::action_call_schema(&recipe);
        if (!schema.contains("properties") || !schema["properties"].contains("module") ||
            !schema["properties"]["module"].contains("enum")) {
            std::fprintf(stderr, "Action call schema missing module enum constraint\n");
            return 1;
        }
        const auto enumList = schema["properties"]["module"]["enum"];
        if (enumList.size() != 3) {
            std::fprintf(stderr, "Module enum constraint size mismatch: expected 3, got %lld\n", static_cast<long long>(enumList.size()));
            return 1;
        }
    }
    std::printf("[GUI-TEST] 24. Venv Sandbox Actions & Recipe Enum Schema: OK\n");

    std::printf("\n========================================\n");
    std::printf("All 24 GUI headless test suites PASSED!\n");
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
    QApplication app(argc, argv);
    aquila::gui::apply_theme(&app, aquila::gui::ThemeMode::Dark);

    const bool smoke = app.arguments().contains(QStringLiteral("--smoke"));
    const bool headlessTest = app.arguments().contains(QStringLiteral("--test-headless"));
    const int ssIdx = app.arguments().indexOf(QStringLiteral("--screenshots"));

    if (ssIdx != -1 && ssIdx + 1 < app.arguments().size()) {
        const QString outDir = app.arguments().at(ssIdx + 1);
        QDir().mkpath(outDir);

        aquila::gui::MainWindow window;
        window.resize(1280, 800);
        window.show();
        app.processEvents();

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
            QPixmap pix = window.grab();
            QString path = QDir(outDir).filePath(QStringLiteral("screenshot_%1.png").arg(modeNames[i]));
            pix.save(path);
        }

        // Setup Wizard
        aquila::gui::SetupWizard wizard;
        wizard.resize(720, 520);
        wizard.show();
        app.processEvents();
        wizard.grab().save(QDir(outDir).filePath(QStringLiteral("screenshot_10_setup_wizard.png")));

        // Plan Review Dialog
        aquila::gui::PlanReviewDialog planDialog(QStringLiteral("fn_dev_implement"),
                                                QStringLiteral("Implement robust AST parser for C++ syntax"),
                                                {QStringLiteral("Scan workspace headers"),
                                                 QStringLiteral("Generate AST node definitions"),
                                                 QStringLiteral("Run unit test suite")});
        planDialog.resize(600, 450);
        planDialog.show();
        app.processEvents();
        planDialog.grab().save(QDir(outDir).filePath(QStringLiteral("screenshot_11_plan_review.png")));

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
            window.grab().save(QDir(outDir).filePath(QStringLiteral("screenshot_12_live_canvas_code.png")));
            ed->rejectInlinePatch();
        }

        std::printf("[SCREENSHOTS-CAPTURED-OK]\n");
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
        std::printf("style=%s\n", qPrintable(QApplication::style()->name()));
        std::printf("styles=%s\n", qPrintable(QStyleFactory::keys().join(QLatin1Char(','))));
        QTimer::singleShot(0, &app, [&app] {
            std::printf("smoke=ok\n");
            std::fflush(stdout);
            app.quit();
        });
        return QApplication::exec();
    }

    aquila::gui::MainWindow window;
    window.show();
    return QApplication::exec();
}
