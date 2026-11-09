// apps/aquila_gui/pages/task_page.hpp
#pragma once

#include "base_page.hpp"

#include <QComboBox>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QSplitter>
#include <QTreeWidget>

namespace aquila::gui {

class TaskPage : public BasePage {
    Q_OBJECT
public:
    explicit TaskPage(QWidget* parent = nullptr);

    void setRecipeList(const QStringList& recipeIds);
    void setRunning(bool running);

    void addLedgerEntry(int turn, const QString& module, const QString& action, const QString& status, const QString& output);
    void updateScratchpad(const QString& objective, const QString& hypothesis,
                          const QStringList& facts, const QStringList& checklist);
    void clearLedger();
    void setLastLogPath(const QString& path);

    QString objective() const;
    QString hypothesis() const;
    int factsCount() const;
    int checklistCount() const;

signals:
    void runRecipeRequested(const QString& recipeId, const QString& prompt);
    void cancelRequested();
    void openBuilderRequested(const QString& recipeId);

private:
    void onRunClicked();

    QComboBox* recipeCombo_ = nullptr;
    QLineEdit* promptInput_ = nullptr;
    QPushButton* runButton_ = nullptr;
    QPushButton* cancelButton_ = nullptr;
    QPushButton* openBuilderButton_ = nullptr;
    QPushButton* openLogsButton_ = nullptr;
    QString lastLogPath_;

    QTreeWidget* ledgerTree_ = nullptr;
    QLabel* objectiveLabel_ = nullptr;
    QLabel* hypothesisLabel_ = nullptr;
    QListWidget* factsList_ = nullptr;
    QTreeWidget* checklistTree_ = nullptr;
};

}  // namespace aquila::gui

