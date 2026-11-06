// apps/aquila_gui/pages/task_page.cpp
#include "task_page.hpp"

#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>

namespace aquila::gui {

TaskPage::TaskPage(QWidget* parent)
    : BasePage(QStringLiteral("Tasks Mode"),
               QStringLiteral("Autonomous Recipe Workflows with Deterministic Exit Gates"),
               QStringLiteral("⚡"), parent) {
    auto* layout = contentLayout();

    // Controls Row
    auto* controls = new QHBoxLayout();
    controls->setSpacing(8);

    auto* lblRecipe = new QLabel(QStringLiteral("Recipe:"), this);
    lblRecipe->setStyleSheet(QStringLiteral("font-weight:bold;"));
    controls->addWidget(lblRecipe);

    recipeCombo_ = new QComboBox(this);
    recipeCombo_->setMinimumWidth(220);
    controls->addWidget(recipeCombo_);

    promptInput_ = new QLineEdit(this);
    promptInput_->setPlaceholderText(QStringLiteral("Goal prompt or task instructions (optional)..."));
    controls->addWidget(promptInput_, 1);

    runButton_ = new QPushButton(QStringLiteral("▶ Run Recipe"), this);
    runButton_->setProperty("accent", true);
    connect(runButton_, &QPushButton::clicked, this, &TaskPage::onRunClicked);
    controls->addWidget(runButton_);

    cancelButton_ = new QPushButton(QStringLiteral("⏹ Cancel"), this);
    cancelButton_->setStyleSheet(QStringLiteral("background-color: #a80000; color: #ffffff;"));
    cancelButton_->setEnabled(false);
    connect(cancelButton_, &QPushButton::clicked, this, &TaskPage::cancelRequested);
    controls->addWidget(cancelButton_);

    openBuilderButton_ = new QPushButton(QStringLiteral("🧩 Open in Builder"), this);
    connect(openBuilderButton_, &QPushButton::clicked, this, [this]() {
        emit openBuilderRequested(recipeCombo_->currentText());
    });
    controls->addWidget(openBuilderButton_);

    layout->addLayout(controls);

    // Splitter: Left = Execution Ledger, Right = Scratchpad Monitor
    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Left: Execution Ledger
    auto* ledgerGroup = new QGroupBox(QStringLiteral("Live Execution Ledger"), splitter);
    auto* ledgerLayout = new QVBoxLayout(ledgerGroup);
    ledgerLayout->setContentsMargins(6, 10, 6, 6);

    ledgerTree_ = new QTreeWidget(ledgerGroup);
    ledgerTree_->setColumnCount(4);
    ledgerTree_->setHeaderLabels({QStringLiteral("Turn"), QStringLiteral("Module"), QStringLiteral("Action"), QStringLiteral("Status")});
    ledgerTree_->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    ledgerTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    ledgerTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    ledgerTree_->header()->setSectionResizeMode(3, QHeaderView::Stretch);
    ledgerTree_->setRootIsDecorated(true);
    ledgerLayout->addWidget(ledgerTree_);
    splitter->addWidget(ledgerGroup);

    // Right: Scratchpad Monitor
    auto* padGroup = new QGroupBox(QStringLiteral("Agent Scratchpad Monitor"), splitter);
    auto* padLayout = new QVBoxLayout(padGroup);
    padLayout->setContentsMargins(8, 10, 8, 6);
    padLayout->setSpacing(6);

    auto* lblObjTitle = new QLabel(QStringLiteral("Active Objective:"), padGroup);
    lblObjTitle->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff; font-size: 11px;"));
    padLayout->addWidget(lblObjTitle);

    objectiveLabel_ = new QLabel(QStringLiteral("(none)"), padGroup);
    objectiveLabel_->setWordWrap(true);
    objectiveLabel_->setStyleSheet(QStringLiteral("background-color: #1e1e1e; padding: 6px; border-radius: 4px;"));
    padLayout->addWidget(objectiveLabel_);

    auto* lblHypTitle = new QLabel(QStringLiteral("Current Hypothesis:"), padGroup);
    lblHypTitle->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff; font-size: 11px;"));
    padLayout->addWidget(lblHypTitle);

    hypothesisLabel_ = new QLabel(QStringLiteral("(none)"), padGroup);
    hypothesisLabel_->setWordWrap(true);
    hypothesisLabel_->setStyleSheet(QStringLiteral("background-color: #1e1e1e; padding: 6px; border-radius: 4px;"));
    padLayout->addWidget(hypothesisLabel_);

    auto* lblFactsTitle = new QLabel(QStringLiteral("Verified Facts:"), padGroup);
    lblFactsTitle->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff; font-size: 11px;"));
    padLayout->addWidget(lblFactsTitle);

    factsList_ = new QListWidget(padGroup);
    factsList_->setMaximumHeight(100);
    padLayout->addWidget(factsList_);

    auto* lblCheckTitle = new QLabel(QStringLiteral("Checklist Milestones:"), padGroup);
    lblCheckTitle->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff; font-size: 11px;"));
    padLayout->addWidget(lblCheckTitle);

    checklistTree_ = new QTreeWidget(padGroup);
    checklistTree_->setColumnCount(2);
    checklistTree_->setHeaderLabels({QStringLiteral("Milestone"), QStringLiteral("State")});
    checklistTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    checklistTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    padLayout->addWidget(checklistTree_, 1);

    splitter->addWidget(padGroup);
    splitter->setSizes({550, 450});

    layout->addWidget(splitter, 1);

    // Populate built-in recipes
    setRecipeList({
        QStringLiteral("fn_dev_implement"),
        QStringLiteral("fn_dev_documentation"),
        QStringLiteral("fn_dev_tdd"),
        QStringLiteral("fn_dev_dynamic"),
        QStringLiteral("fn_research_full"),
        QStringLiteral("fn_research_dynamic"),
        QStringLiteral("fn_research_offline"),
        QStringLiteral("fn_research_chat_light"),
        QStringLiteral("fn_writing_full"),
        QStringLiteral("fn_writing_dynamic"),
        QStringLiteral("fn_writing_sources"),
        QStringLiteral("fn_learn_syllabus"),
        QStringLiteral("fn_learn_syllabus_web"),
        QStringLiteral("fn_persona_build"),
        QStringLiteral("fn_persona_lore"),
        QStringLiteral("code_smoke_file"),
        QStringLiteral("knowledge_smoke")
    });
}

void TaskPage::setRecipeList(const QStringList& recipeIds) {
    recipeCombo_->clear();
    for (const auto& r : recipeIds) {
        recipeCombo_->addItem(r);
    }
}

void TaskPage::onRunClicked() {
    const QString recipe = recipeCombo_->currentText();
    const QString prompt = promptInput_->text().trimmed();
    if (recipe.isEmpty()) return;

    clearLedger();
    setRunning(true);
    setStatus(QStringLiteral("Running recipe %1...").arg(recipe));
    emit runRecipeRequested(recipe, prompt);
}

void TaskPage::setRunning(bool running) {
    runButton_->setEnabled(!running);
    recipeCombo_->setEnabled(!running);
    promptInput_->setEnabled(!running);
    cancelButton_->setEnabled(running);
}

void TaskPage::addLedgerEntry(int turn, const QString& module, const QString& action, const QString& status, const QString& output) {
    auto* item = new QTreeWidgetItem(ledgerTree_);
    item->setText(0, QString::number(turn + 1));
    item->setText(1, module);
    item->setText(2, action);
    item->setText(3, status);

    if (status == QStringLiteral("OK") || status == QStringLiteral("success")) {
        item->setForeground(3, QColor(QStringLiteral("#7ee787")));
    } else {
        item->setForeground(3, QColor(QStringLiteral("#ffa198")));
    }

    if (!output.isEmpty()) {
        auto* child = new QTreeWidgetItem(item);
        child->setText(0, QStringLiteral("Output"));
        child->setText(3, output.left(300) + (output.length() > 300 ? QStringLiteral("...") : QStringLiteral("")));
        child->setForeground(3, QColor(QStringLiteral("#8b949e")));
    }

    ledgerTree_->scrollToItem(item);
}

void TaskPage::updateScratchpad(const QString& objective, const QString& hypothesis,
                                const QStringList& facts, const QStringList& checklist) {
    objectiveLabel_->setText(objective.isEmpty() ? QStringLiteral("(none)") : objective);
    hypothesisLabel_->setText(hypothesis.isEmpty() ? QStringLiteral("(none)") : hypothesis);

    factsList_->clear();
    for (const auto& f : facts) {
        factsList_->addItem(QStringLiteral("• %1").arg(f));
    }

    checklistTree_->clear();
    for (const auto& c : checklist) {
        auto* item = new QTreeWidgetItem(checklistTree_);
        item->setText(0, c);
        item->setText(1, QStringLiteral("Pending"));
        item->setForeground(1, QColor(QStringLiteral("#d29922")));
    }
}

void TaskPage::clearLedger() {
    ledgerTree_->clear();
    objectiveLabel_->setText(QStringLiteral("(none)"));
    hypothesisLabel_->setText(QStringLiteral("(none)"));
    factsList_->clear();
    checklistTree_->clear();
}

QString TaskPage::objective() const {
    return objectiveLabel_->text();
}

QString TaskPage::hypothesis() const {
    return hypothesisLabel_->text();
}

int TaskPage::factsCount() const {
    return factsList_->count();
}

int TaskPage::checklistCount() const {
    return checklistTree_->topLevelItemCount();
}

}  // namespace aquila::gui

