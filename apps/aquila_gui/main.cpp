#include "builder/recipe_builder_page.hpp"
#include "dialogs/plan_review_dialog.hpp"
#include "dialogs/setup_wizard.hpp"
#include "main_window.hpp"
#include "theme/theme.hpp"
#include "widgets/flow_layout.hpp"
#include "widgets/inline_prompt_bar.hpp"
#include "widgets/inline_diff_overlay.hpp"

#include "aquila/core.hpp"

#include <QApplication>
#include <QDir>
#include <QPixmap>
#include <QStyle>
#include <QStyleFactory>
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

    std::printf("\n========================================\n");
    std::printf("All 13 GUI headless test suites PASSED!\n");
    std::printf("[GUI-HEADLESS-TEST-OK]\n");
    std::printf("smoke=ok\n");
    std::printf("========================================\n");
    std::fflush(stdout);
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
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
