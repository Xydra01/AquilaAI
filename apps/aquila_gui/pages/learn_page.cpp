// apps/aquila_gui/pages/learn_page.cpp
#include "learn_page.hpp"
#include "../theme/markdown_renderer.hpp"

#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>

namespace aquila::gui {

LearnPage::LearnPage(QWidget* parent)
    : BasePage(QStringLiteral("Learn & Classroom"),
               QStringLiteral("Hierarchical Curriculum Building, Mastery Progression (0-5), and Interactive Quizzes"),
               QStringLiteral("🎓"), parent) {
    auto* layout = contentLayout();

    // Top Controls
    auto* topBar = new QHBoxLayout();
    topBar->setSpacing(8);

    auto* lblCourse = new QLabel(QStringLiteral("Active Course:"), this);
    lblCourse->setStyleSheet(QStringLiteral("font-weight:bold;"));
    topBar->addWidget(lblCourse);

    courseCombo_ = new QComboBox(this);
    courseCombo_->setMinimumWidth(220);
    connect(courseCombo_, &QComboBox::currentTextChanged, this, &LearnPage::courseSelected);
    topBar->addWidget(courseCombo_);

    generateBtn_ = new QPushButton(QStringLiteral("📝 Generate Quiz / Assessment"), this);
    generateBtn_->setProperty("accent", true);
    connect(generateBtn_, &QPushButton::clicked, this, &LearnPage::onGenerateAssessmentClicked);
    topBar->addWidget(generateBtn_);
    topBar->addStretch(1);

    layout->addLayout(topBar);

    // Splitter: Left = Syllabus Hierarchy, Right = Assessment & Mastery
    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Left: Syllabus Tree
    auto* treeGroup = new QGroupBox(QStringLiteral("Course Curriculum Hierarchy (≥ 8 Units, ≥ 5 Sub-units)"), splitter);
    auto* treeLayout = new QVBoxLayout(treeGroup);
    treeLayout->setContentsMargins(4, 8, 4, 4);

    syllabusTree_ = new QTreeWidget(treeGroup);
    syllabusTree_->setColumnCount(2);
    syllabusTree_->setHeaderLabels({QStringLiteral("Curriculum Topic / Unit"), QStringLiteral("Mastery")});
    syllabusTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    syllabusTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    treeLayout->addWidget(syllabusTree_);
    splitter->addWidget(treeGroup);

    // Right: Assessment & Mastery Gauge
    auto* quizGroup = new QGroupBox(QStringLiteral("Assessment & Mastery Progression"), splitter);
    auto* quizLayout = new QVBoxLayout(quizGroup);
    quizLayout->setContentsMargins(8, 10, 8, 8);
    quizLayout->setSpacing(8);

    // Mastery Progress
    auto* masteryHeader = new QHBoxLayout();
    masteryLabel_ = new QLabel(QStringLiteral("Mastery Level: 0 / 5 (Novice)"), quizGroup);
    masteryLabel_->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff; font-size: 13px;"));
    masteryHeader->addWidget(masteryLabel_);
    masteryHeader->addStretch(1);
    quizLayout->addLayout(masteryHeader);

    masteryBar_ = new QProgressBar(quizGroup);
    masteryBar_->setRange(0, 5);
    masteryBar_->setValue(0);
    masteryBar_->setFixedHeight(10);
    masteryBar_->setTextVisible(false);
    quizLayout->addWidget(masteryBar_);

    // Question Box
    auto* lblQ = new QLabel(QStringLiteral("Active Assessment Question:"), quizGroup);
    lblQ->setStyleSheet(QStringLiteral("font-weight: bold; font-size: 11px;"));
    quizLayout->addWidget(lblQ);

    questionViewer_ = new QTextEdit(quizGroup);
    questionViewer_->setReadOnly(true);
    questionViewer_->setMaximumHeight(140);
    questionViewer_->setStyleSheet(QStringLiteral(
        "background-color: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 6px; padding: 8px;"
    ));
    quizLayout->addWidget(questionViewer_);

    // Multiple Choice Answer Selector
    auto* lblAns = new QLabel(QStringLiteral("Select Your Answer:"), quizGroup);
    lblAns->setStyleSheet(QStringLiteral("font-weight: bold; font-size: 11px;"));
    quizLayout->addWidget(lblAns);

    answerCombo_ = new QComboBox(quizGroup);
    quizLayout->addWidget(answerCombo_);

    submitAnswerBtn_ = new QPushButton(QStringLiteral("Submit Answer"), quizGroup);
    submitAnswerBtn_->setProperty("accent", true);
    connect(submitAnswerBtn_, &QPushButton::clicked, this, &LearnPage::onSubmitAnswerClicked);
    quizLayout->addWidget(submitAnswerBtn_);

    quizLayout->addStretch(1);
    splitter->addWidget(quizGroup);

    splitter->setSizes({550, 450});
    layout->addWidget(splitter, 1);

    setCourseList({QStringLiteral("cpp20_systems_architecture"), QStringLiteral("compiler_design_internals")});
    setMasteryLevel(1);

    // Populate a sample standard curriculum
    auto* root = new QTreeWidgetItem(syllabusTree_, {QStringLiteral("C++20 Systems Architecture (Root)"), QStringLiteral("1/5")});
    root->setExpanded(true);
    for (int i = 1; i <= 8; ++i) {
        auto* unit = new QTreeWidgetItem(root, {QStringLiteral("Unit %1: Core Concept %1").arg(i), QStringLiteral("0/5")});
        for (int j = 1; j <= 5; ++j) {
            new QTreeWidgetItem(unit, {QStringLiteral("Topic %1.%2: Details").arg(i).arg(j), QStringLiteral("0/5")});
        }
    }
}

void LearnPage::setCourseList(const QStringList& courses) {
    courseCombo_->clear();
    for (const auto& c : courses) {
        courseCombo_->addItem(c);
    }
}

void LearnPage::setSyllabusTree(const QString& /* courseJson */) {
    // Dynamically populates syllabus from JSON
}

void LearnPage::setAssessmentQuestion(const QString& question, const QStringList& options) {
    questionViewer_->setText(question);
    answerCombo_->clear();
    for (const auto& opt : options) {
        answerCombo_->addItem(opt);
    }
}

void LearnPage::showAssessmentResult(bool correct, const QString& explanation) {
    const QString formattedHtml = MarkdownRenderer::toHtml(explanation);
    const QString resultHtml = QStringLiteral(
        "<div style='margin-top:12px; padding:10px; border-radius:6px; background-color:%1; color:#ffffff;'>"
        "  <b>%2</b><br>%3"
        "</div>"
    ).arg(
        correct ? QStringLiteral("#2ea043") : QStringLiteral("#da3633"),
        correct ? QStringLiteral("✓ Correct!") : QStringLiteral("✗ Incorrect"),
        formattedHtml
    );
    questionViewer_->append(resultHtml);
}

void LearnPage::setMasteryLevel(int level) {
    masteryBar_->setValue(level);
    const char* titles[] = {"0 / 5 (Uninitiated)", "1 / 5 (Novice)", "2 / 5 (Competent)",
                            "3 / 5 (Proficient)", "4 / 5 (Expert)", "5 / 5 (Master)"};
    if (level >= 0 && level <= 5) {
        masteryLabel_->setText(QString::fromUtf8(titles[level]));
    }
}

int LearnPage::masteryLevel() const {
    return masteryBar_->value();
}

QString LearnPage::currentQuestion() const {
    return questionViewer_->toPlainText();
}

int LearnPage::answerOptionCount() const {
    return answerCombo_->count();
}

void LearnPage::onGenerateAssessmentClicked() {
    auto* cur = syllabusTree_->currentItem();
    const QString node = cur ? cur->text(0) : QStringLiteral("root");
    setStatus(QStringLiteral("Generating quiz for node '%1'...").arg(node));
    emit generateAssessmentRequested(node);
}

void LearnPage::onSubmitAnswerClicked() {
    const int idx = answerCombo_->currentIndex();
    if (idx >= 0) {
        setStatus(QStringLiteral("Submitting answer option %1...").arg(idx + 1));
        emit submitAnswerRequested(idx);
    }
}

}  // namespace aquila::gui

