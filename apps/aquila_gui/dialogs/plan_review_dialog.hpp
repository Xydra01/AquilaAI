// apps/aquila_gui/dialogs/plan_review_dialog.hpp
#pragma once

#include <QDialog>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QTabWidget>
#include <QTextEdit>

namespace aquila::gui {

class PlanReviewDialog : public QDialog {
    Q_OBJECT
public:
    explicit PlanReviewDialog(const QString& recipeId, const QString& taskPrompt,
                              const QStringList& checklist, QWidget* parent = nullptr);

    explicit PlanReviewDialog(const QString& recipeId, const QString& taskPrompt,
                              const QString& specMarkdown, const QStringList& milestones,
                              QWidget* parent = nullptr);

    bool isApproved() const { return approved_; }

private:
    void setupUi(const QString& recipeId, const QString& taskPrompt,
                 const QString& specMarkdown, const QStringList& checklist);

    bool approved_ = false;
    QLabel* recipeLabel_ = nullptr;
    QLabel* promptLabel_ = nullptr;
    QTabWidget* tabWidget_ = nullptr;
    QTextEdit* specView_ = nullptr;
    QListWidget* checklistView_ = nullptr;
    QPushButton* approveButton_ = nullptr;
    QPushButton* cancelButton_ = nullptr;
};

}  // namespace aquila::gui
