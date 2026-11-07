// apps/aquila_gui/pages/learn_page.hpp
#pragma once

#include "base_page.hpp"

#include <QComboBox>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
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
    void showAssessmentResult(bool correct, const QString& explanation);
    void setMasteryLevel(int level);
    int masteryLevel() const;
    QString currentQuestion() const;
    int answerOptionCount() const;

    void setArchiveSources(const QJsonArray& sources);
    void addArchiveSourceItem(const QString& name, const QString& type, int tokens, const QString& date);
    void setArchiveAnswer(const QString& answer);

signals:
    void courseSelected(const QString& courseId);
    void generateAssessmentRequested(const QString& nodeId);
    void submitAnswerRequested(int selectedOption);

    void addTextSourceRequested(const QString& name, const QString& content);
    void addFileSourceRequested(const QString& filePath);
    void addUrlSourceRequested(const QString& url);
    void askArchiveRequested(const QString& question);
    void buildFromSourcesRequested();

private slots:
    void onGenerateAssessmentClicked();
    void onSubmitAnswerClicked();
    void onAddTextSourceClicked();
    void onAddFileSourceClicked();
    void onAddUrlSourceClicked();
    void onAskArchiveClicked();

private:
    QComboBox* courseCombo_ = nullptr;
    QPushButton* generateBtn_ = nullptr;

    QTreeWidget* syllabusTree_ = nullptr;
    QProgressBar* masteryBar_ = nullptr;
    QLabel* masteryLabel_ = nullptr;

    // NotebookLM Archive Dock
    QTreeWidget* archiveTree_ = nullptr;
    QPushButton* addTextBtn_ = nullptr;
    QPushButton* addFileBtn_ = nullptr;
    QPushButton* addUrlBtn_ = nullptr;
    QPushButton* buildFromSourcesBtn_ = nullptr;

    QLineEdit* askInput_ = nullptr;
    QPushButton* askBtn_ = nullptr;
    QTextEdit* askAnswerViewer_ = nullptr;

    QTextEdit* questionViewer_ = nullptr;
    QComboBox* answerCombo_ = nullptr;
    QPushButton* submitAnswerBtn_ = nullptr;
};

}  // namespace aquila::gui
