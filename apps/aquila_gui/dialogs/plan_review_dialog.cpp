// apps/aquila_gui/dialogs/plan_review_dialog.cpp
#include "plan_review_dialog.hpp"

#include <QHBoxLayout>
#include <QVBoxLayout>

namespace aquila::gui {

PlanReviewDialog::PlanReviewDialog(const QString& recipeId, const QString& taskPrompt,
                                   const QStringList& checklist, QWidget* parent)
    : QDialog(parent) {
    setWindowTitle(QStringLiteral("Plan & Exit Gate Review"));
    resize(520, 360);

    auto* layout = new QVBoxLayout(this);
    layout->setSpacing(10);

    recipeLabel_ = new QLabel(QStringLiteral("<b>Recipe:</b> %1").arg(recipeId), this);
    layout->addWidget(recipeLabel_);

    promptLabel_ = new QLabel(QStringLiteral("<b>Task:</b> %1").arg(taskPrompt), this);
    promptLabel_->setWordWrap(true);
    layout->addWidget(promptLabel_);

    auto* lblCheck = new QLabel(QStringLiteral("Planned Exit Gate Verification Checklist:"), this);
    lblCheck->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff;"));
    layout->addWidget(lblCheck);

    checklistView_ = new QListWidget(this);
    for (const auto& item : checklist) {
        checklistView_->addItem(QStringLiteral("• %1").arg(item));
    }
    layout->addWidget(checklistView_, 1);

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
