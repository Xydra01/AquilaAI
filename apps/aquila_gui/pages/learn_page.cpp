// apps/aquila_gui/pages/learn_page.cpp
#include "learn_page.hpp"

#include <QCoreApplication>
#include <QFileDialog>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QInputDialog>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMessageBox>
#include <QVBoxLayout>

namespace aquila::gui {

LearnPage::LearnPage(QWidget* parent)
    : BasePage(QStringLiteral("Learn & Classroom"),
               QStringLiteral("NotebookLM Course Archive, Hierarchical Syllabus, and Adaptive Assessment"),
               QStringLiteral("🎓"), parent) {
    auto* layout = contentLayout();

    // Top Row: Course Selector & Generate
    auto* topRow = new QHBoxLayout();
    topRow->setSpacing(8);

    auto* courseLabel = new QLabel(QStringLiteral("Active Course:"), this);
    topRow->addWidget(courseLabel);

    courseCombo_ = new QComboBox(this);
    courseCombo_->setMinimumWidth(240);
    connect(courseCombo_, &QComboBox::currentTextChanged, this, &LearnPage::courseSelected);
    topRow->addWidget(courseCombo_, 1);

    generateBtn_ = new QPushButton(QStringLiteral("⚡ Generate Assessment"), this);
    generateBtn_->setProperty("accent", true);
    connect(generateBtn_, &QPushButton::clicked, this, &LearnPage::onGenerateAssessmentClicked);
    topRow->addWidget(generateBtn_);

    layout->addLayout(topRow);

    // Main Splitter: Left (Syllabus & Archive Sources), Right (Archive Q&A & Assessments)
    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Left Container
    auto* leftWidget = new QWidget(splitter);
    auto* leftLayout = new QVBoxLayout(leftWidget);
    leftLayout->setContentsMargins(0, 0, 0, 0);

    // Syllabus Hierarchy Group
    auto* sylGroup = new QGroupBox(QStringLiteral("Course Syllabus Hierarchy & Progress"), leftWidget);
    auto* sylLayout = new QVBoxLayout(sylGroup);
    sylLayout->setContentsMargins(4, 8, 4, 4);

    syllabusTree_ = new QTreeWidget(sylGroup);
    syllabusTree_->setColumnCount(3);
    syllabusTree_->setHeaderLabels({QStringLiteral("Unit / Lesson"), QStringLiteral("ID"), QStringLiteral("Mastery")});
    syllabusTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    syllabusTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    syllabusTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    sylLayout->addWidget(syllabusTree_);

    auto* masteryRow = new QHBoxLayout();
    masteryLabel_ = new QLabel(QStringLiteral("Mastery Progress: 0%"), sylGroup);
    masteryRow->addWidget(masteryLabel_);

    masteryBar_ = new QProgressBar(sylGroup);
    masteryBar_->setRange(0, 100);
    masteryBar_->setValue(0);
    masteryRow->addWidget(masteryBar_, 1);
    sylLayout->addLayout(masteryRow);

    leftLayout->addWidget(sylGroup, 3);

    // NotebookLM Course Archive Dock
    auto* archGroup = new QGroupBox(QStringLiteral("Course Archive & Reference Sources (NotebookLM)"), leftWidget);
    auto* archLayout = new QVBoxLayout(archGroup);
    archLayout->setContentsMargins(4, 8, 4, 4);

    archiveTree_ = new QTreeWidget(archGroup);
    archiveTree_->setColumnCount(4);
    archiveTree_->setHeaderLabels({QStringLiteral("Source Name"), QStringLiteral("Type"), QStringLiteral("Tokens"), QStringLiteral("Added")});
    archiveTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    archiveTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    archiveTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    archiveTree_->header()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    archLayout->addWidget(archiveTree_);

    auto* archBtnRow = new QHBoxLayout();
    archBtnRow->setSpacing(6);

    addTextBtn_ = new QPushButton(QStringLiteral("➕ Add Note"), archGroup);
    connect(addTextBtn_, &QPushButton::clicked, this, &LearnPage::onAddTextSourceClicked);
    archBtnRow->addWidget(addTextBtn_);

    addFileBtn_ = new QPushButton(QStringLiteral("📁 Add File"), archGroup);
    connect(addFileBtn_, &QPushButton::clicked, this, &LearnPage::onAddFileSourceClicked);
    archBtnRow->addWidget(addFileBtn_);

    addUrlBtn_ = new QPushButton(QStringLiteral("🌐 Ingest URL"), archGroup);
    connect(addUrlBtn_, &QPushButton::clicked, this, &LearnPage::onAddUrlSourceClicked);
    archBtnRow->addWidget(addUrlBtn_);

    buildFromSourcesBtn_ = new QPushButton(QStringLiteral("⚡ Build Syllabus"), archGroup);
    connect(buildFromSourcesBtn_, &QPushButton::clicked, this, &LearnPage::buildFromSourcesRequested);
    archBtnRow->addWidget(buildFromSourcesBtn_);

    archLayout->addLayout(archBtnRow);
    leftLayout->addWidget(archGroup, 2);
    splitter->addWidget(leftWidget);

    // Right Container: Archive Q&A + Assessment Practice
    auto* rightWidget = new QWidget(splitter);
    auto* rightLayout = new QVBoxLayout(rightWidget);
    rightLayout->setContentsMargins(0, 0, 0, 0);

    // Grounded Archive Q&A Group
    auto* qaGroup = new QGroupBox(QStringLiteral("Grounded Archive Q&A (NotebookLM Citations)"), rightWidget);
    auto* qaLayout = new QVBoxLayout(qaGroup);
    qaLayout->setContentsMargins(4, 8, 4, 4);

    auto* qaInputRow = new QHBoxLayout();
    askInput_ = new QLineEdit(qaGroup);
    askInput_->setPlaceholderText(QStringLiteral("Ask a question grounded in course sources..."));
    connect(askInput_, &QLineEdit::returnPressed, this, &LearnPage::onAskArchiveClicked);
    qaInputRow->addWidget(askInput_, 1);

    askBtn_ = new QPushButton(QStringLiteral("Ask Archive"), qaGroup);
    connect(askBtn_, &QPushButton::clicked, this, &LearnPage::onAskArchiveClicked);
    qaInputRow->addWidget(askBtn_);
    qaLayout->addLayout(qaInputRow);

    askAnswerViewer_ = new QTextEdit(qaGroup);
    askAnswerViewer_->setReadOnly(true);
    askAnswerViewer_->setPlaceholderText(QStringLiteral("Answers citing archived documents and section headings will appear here..."));
    qaLayout->addWidget(askAnswerViewer_, 1);

    rightLayout->addWidget(qaGroup, 2);

    // Assessment Question Group
    auto* quizGroup = new QGroupBox(QStringLiteral("Interactive Knowledge Assessment"), rightWidget);
    auto* quizLayout = new QVBoxLayout(quizGroup);
    quizLayout->setContentsMargins(4, 8, 4, 4);

    questionViewer_ = new QTextEdit(quizGroup);
    questionViewer_->setReadOnly(true);
    questionViewer_->setPlaceholderText(QStringLiteral("Select a lesson node and click 'Generate Assessment'..."));
    quizLayout->addWidget(questionViewer_, 2);

    auto* ansRow = new QHBoxLayout();
    ansRow->setSpacing(8);

    answerCombo_ = new QComboBox(quizGroup);
    ansRow->addWidget(answerCombo_, 1);

    submitAnswerBtn_ = new QPushButton(QStringLiteral("Submit Answer"), quizGroup);
    submitAnswerBtn_->setProperty("accent", true);
    connect(submitAnswerBtn_, &QPushButton::clicked, this, &LearnPage::onSubmitAnswerClicked);
    ansRow->addWidget(submitAnswerBtn_);

    quizLayout->addLayout(ansRow);
    rightLayout->addWidget(quizGroup, 2);

    splitter->addWidget(rightWidget);
    splitter->setSizes({550, 650});
    layout->addWidget(splitter, 1);
}

void LearnPage::setCourseList(const QStringList& courses) {
    courseCombo_->clear();
    courseCombo_->addItems(courses);
}

void LearnPage::setSyllabusTree(const QString& courseJson) {
    syllabusTree_->clear();
    QJsonDocument doc = QJsonDocument::fromJson(courseJson.toUtf8());
    if (!doc.isObject()) return;

    QJsonObject obj = doc.object();
    QJsonArray nodes = obj.value(QStringLiteral("nodes")).toArray();

    int totalMastery = 0;
    for (const auto& val : nodes) {
        QJsonObject n = val.toObject();
        auto* item = new QTreeWidgetItem(syllabusTree_);
        item->setText(0, n.value(QStringLiteral("title")).toString());
        item->setText(1, n.value(QStringLiteral("id")).toString());
        int mastery = n.value(QStringLiteral("mastery_tier")).toInt(0);
        item->setText(2, QStringLiteral("Tier %1/5").arg(mastery));
        totalMastery += mastery;
    }

    if (!nodes.isEmpty()) {
        int maxPossible = nodes.size() * 5;
        int pct = (totalMastery * 100) / maxPossible;
        setMasteryLevel(pct);
    }
}

void LearnPage::setArchiveSources(const QJsonArray& sources) {
    archiveTree_->clear();
    for (const auto& s : sources) {
        QJsonObject obj = s.toObject();
        addArchiveSourceItem(
            obj.value(QStringLiteral("name")).toString(),
            obj.value(QStringLiteral("source_type")).toString(),
            obj.value(QStringLiteral("token_count")).toInt(),
            obj.value(QStringLiteral("added_at")).toString().left(10)
        );
    }
}

void LearnPage::addArchiveSourceItem(const QString& name, const QString& type, int tokens, const QString& date) {
    auto* item = new QTreeWidgetItem(archiveTree_);
    item->setText(0, name);
    item->setText(1, type);
    item->setText(2, QStringLiteral("%1 tok").arg(tokens));
    item->setText(3, date);
}

void LearnPage::setArchiveAnswer(const QString& answer) {
    askAnswerViewer_->setMarkdown(answer);
}

void LearnPage::onAddTextSourceClicked() {
    bool ok = false;
    QString name = QInputDialog::getText(this, QStringLiteral("Add Note Source"), QStringLiteral("Source title:"), QLineEdit::Normal, QStringLiteral("Lecture Notes"), &ok);
    if (!ok || name.trimmed().isEmpty()) return;

    QString content = QInputDialog::getMultiLineText(this, QStringLiteral("Source Content"), QStringLiteral("Enter markdown notes:"), QString(), &ok);
    if (!ok || content.trimmed().isEmpty()) return;

    emit addTextSourceRequested(name.trimmed(), content);
}

void LearnPage::onAddFileSourceClicked() {
    QString file = QFileDialog::getOpenFileName(this, QStringLiteral("Ingest File into Archive"), QString(), QStringLiteral("Documents (*.md *.txt *.pdf *.py *.cpp *.h *.json);;All Files (*.*)"));
    if (!file.isEmpty()) {
        emit addFileSourceRequested(file);
    }
}

void LearnPage::onAddUrlSourceClicked() {
    bool ok = false;
    QString url = QInputDialog::getText(this, QStringLiteral("Ingest Web URL"), QStringLiteral("Enter URL to scrape into archive:"), QLineEdit::Normal, QStringLiteral("https://"), &ok);
    if (ok && !url.trimmed().isEmpty()) {
        emit addUrlSourceRequested(url.trimmed());
    }
}

void LearnPage::onAskArchiveClicked() {
    const QString q = askInput_->text().trimmed();
    if (q.isEmpty()) return;
    setStatus(QStringLiteral("Searching course archive for '%1'...").arg(q));
    emit askArchiveRequested(q);
}

void LearnPage::setAssessmentQuestion(const QString& question, const QStringList& options) {
    questionViewer_->setText(question);
    answerCombo_->clear();
    answerCombo_->addItems(options);
}

void LearnPage::showAssessmentResult(bool correct, const QString& explanation) {
    if (!isVisible() || qgetenv("QT_QPA_PLATFORM") == "offscreen" || QCoreApplication::arguments().contains(QStringLiteral("--test-headless"))) {
        return;
    }
    QMessageBox::information(this,
        correct ? QStringLiteral("Correct!") : QStringLiteral("Needs Review"),
        QStringLiteral("%1\n\n%2").arg(correct ? QStringLiteral("✅ Well done!") : QStringLiteral("❌ Not quite."), explanation));
}

void LearnPage::setMasteryLevel(int level) {
    masteryBar_->setValue(level);
    masteryLabel_->setText(QStringLiteral("Mastery Progress: %1%").arg(level));
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
    auto* item = syllabusTree_->currentItem();
    const QString nodeId = item ? item->text(1) : QStringLiteral("root");
    emit generateAssessmentRequested(nodeId);
}

void LearnPage::onSubmitAnswerClicked() {
    emit submitAnswerRequested(answerCombo_->currentIndex());
}

}  // namespace aquila::gui
