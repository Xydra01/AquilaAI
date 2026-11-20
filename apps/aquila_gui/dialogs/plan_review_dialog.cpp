// apps/aquila_gui/dialogs/plan_review_dialog.cpp
#include "plan_review_dialog.hpp"

#include <QHBoxLayout>
#include <QVBoxLayout>

namespace aquila::gui {

PlanReviewDialog::PlanReviewDialog(const QString& recipeId, const QString& taskPrompt,
                                   const QStringList& checklist, QWidget* parent)
    : QDialog(parent) {
    setupUi(recipeId, taskPrompt, QString(), checklist);
}

PlanReviewDialog::PlanReviewDialog(const QString& recipeId, const QString& taskPrompt,
                                   const QString& specMarkdown, const QStringList& milestones,
                                   QWidget* parent)
    : QDialog(parent) {
    setupUi(recipeId, taskPrompt, specMarkdown, milestones);
}

void PlanReviewDialog::setupUi(const QString& recipeId, const QString& taskPrompt,
                               const QString& specMarkdown, const QStringList& checklist) {
    setWindowTitle(QStringLiteral("Task Plan & Specification Review"));
    resize(specMarkdown.isEmpty() ? 520 : 720, specMarkdown.isEmpty() ? 380 : 540);

    auto* layout = new QVBoxLayout(this);
    layout->setSpacing(10);

    recipeLabel_ = new QLabel(QStringLiteral("<b>Recipe:</b> %1").arg(recipeId), this);
    layout->addWidget(recipeLabel_);

    promptLabel_ = new QLabel(QStringLiteral("<b>Task:</b> %1").arg(taskPrompt), this);
    promptLabel_->setWordWrap(true);
    layout->addWidget(promptLabel_);

    if (specMarkdown.isEmpty()) {
        auto* lblCheck = new QLabel(QStringLiteral("Planned Exit Gate Verification Checklist:"), this);
        lblCheck->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff;"));
        layout->addWidget(lblCheck);

        checklistView_ = new QListWidget(this);
        for (const auto& item : checklist) {
            checklistView_->addItem(QStringLiteral("• %1").arg(item));
        }
        layout->addWidget(checklistView_, 1);
    } else {
        tabWidget_ = new QTabWidget(this);

        // Tab 1: Full Specification
        specView_ = new QTextEdit(tabWidget_);
        specView_->setReadOnly(true);
        specView_->setMarkdown(specMarkdown);
        tabWidget_->addTab(specView_, QStringLiteral("📄 Specification Document"));

        // Tab 2: Execution Milestones
        checklistView_ = new QListWidget(tabWidget_);
        for (const auto& item : checklist) {
            checklistView_->addItem(QStringLiteral("• %1").arg(item));
        }
        tabWidget_->addTab(checklistView_, QStringLiteral("📋 Execution Milestones (%1)").arg(checklist.size()));

        layout->addWidget(tabWidget_, 1);
    }

    auto* btnRow = new QHBoxLayout();
    btnRow->addStretch(1);

    cancelButton_ = new QPushButton(QStringLiteral("Cancel"), this);
    connect(cancelButton_, &QPushButton::clicked, this, &QDialog::reject);
    btnRow->addWidget(cancelButton_);

    approveButton_ = new QPushButton(QStringLiteral("✓ Approve & Run"), this);
    approveButton_->setProperty("accent", true);
    connect(approveButton_, &QPushButton::clicked, this, [this]() {
        approved_ = true;
        accept();
    });
    btnRow->addWidget(approveButton_);

    layout->addLayout(btnRow);
}

}  // namespace aquila::gui
