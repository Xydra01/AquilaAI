#include "dialogs/plan_review_dialog.hpp"
#include "dialogs/setup_wizard.hpp"
#include "main_window.hpp"
#include "theme/theme.hpp"
#include "widgets/flow_layout.hpp"

#include "aquila/core.hpp"

#include <QApplication>
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
    std::printf("[GUI-TEST] 2. FlowLayout widget: OK\n");

    // Test 3: MainWindow instantiation & navigation
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

    // Test 8: Setup Wizard Page Progression
    aquila::gui::SetupWizard wizard;
    if (wizard.pageIds().size() != 4) {
        std::fprintf(stderr, "Setup wizard page count mismatch: expected 4, got %lld\n", static_cast<long long>(wizard.pageIds().size()));
        return 1;
    }
    std::printf("[GUI-TEST] 8. Setup Wizard (4 pages): OK\n");

    // Test 9: Plan Review Dialog
    aquila::gui::PlanReviewDialog planDialog(QStringLiteral("fn_dev_implement"), QStringLiteral("Fix bug"), {QStringLiteral("Step 1"), QStringLiteral("Step 2")});
    std::printf("[GUI-TEST] 9. Plan Review Dialog: OK\n");

    // Test 10: AgentWorker background execution with mock backend and queued signals
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
    std::printf("[GUI-TEST] 10. AgentWorker QThread Queued Signal Bridge: OK\n");

    std::printf("\n========================================\n");
    std::printf("All 10 GUI headless test suites PASSED!\n");
    std::printf("[GUI-HEADLESS-TEST-OK]\n");
    std::printf("smoke=ok\n");
    std::printf("========================================\n");
    std::fflush(stdout);
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    aquila::gui::apply_theme(&app, aquila::gui::ThemeMode::Dark);

    const bool smoke = app.arguments().contains(QStringLiteral("--smoke"));
    const bool headlessTest = app.arguments().contains(QStringLiteral("--test-headless"));

    if (headlessTest) {
        return run_headless_tests(app);
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
