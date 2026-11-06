// apps/aquila_gui/pages/learn_page.hpp
#pragma once

#include "base_page.hpp"

#include <QComboBox>
#include <QLabel>
#include <QProgressBar>
#include <QPushButton>
#include <QSplitter>
#include <QTextEdit>
#include <QTreeWidget>

namespace aquila::gui {

class LearnPage : public BasePage {
    Q_OBJECT
public:
    explicit LearnPage(QWidget* parent = nullptr);

    void setCourseList(const QStringList& courses);
    void setSyllabusTree(const QString& courseJson);
    void setAssessmentQuestion(const QString& question, const QStringList& options);
    void setMasteryLevel(int level);

signals:
    void courseSelected(const QString& courseId);
    void generateAssessmentRequested(const QString& nodeId);
    void submitAnswerRequested(int selectedOption);

private slots:
    void onGenerateAssessmentClicked();
    void onSubmitAnswerClicked();

private:
    QComboBox* courseCombo_ = nullptr;
    QPushButton* generateBtn_ = nullptr;

    QTreeWidget* syllabusTree_ = nullptr;
    QTextEdit* questionViewer_ = nullptr;
    QComboBox* answerCombo_ = nullptr;
    QPushButton* submitAnswerBtn_ = nullptr;
    QProgressBar* masteryBar_ = nullptr;
    QLabel* masteryLabel_ = nullptr;
};

}  // namespace aquila::gui

