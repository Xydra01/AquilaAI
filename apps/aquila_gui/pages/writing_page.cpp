// apps/aquila_gui/pages/writing_page.cpp
#include "writing_page.hpp"

#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QInputDialog>

namespace aquila::gui {

WritingPage::WritingPage(QWidget* parent)
    : BasePage(QStringLiteral("Writing Studio"),
               QStringLiteral("Structured Document Authoring, Section Canvas, and Live Markdown Preview"),
               QStringLiteral("📝"), parent) {
    auto* layout = contentLayout();

    // Top Action Bar
    auto* topBar = new QHBoxLayout();
    wordCountLabel_ = new QLabel(QStringLiteral("Words: 0 | Sections: 0"), this);
    wordCountLabel_->setStyleSheet(QStringLiteral("font-weight: bold; color: #79c0ff;"));
    topBar->addWidget(wordCountLabel_);
    topBar->addStretch(1);

    reviseButton_ = new QPushButton(QStringLiteral("⚡ Revise Section"), this);
    connect(reviseButton_, &QPushButton::clicked, this, &WritingPage::onReviseClicked);
    topBar->addWidget(reviseButton_);

    compileButton_ = new QPushButton(QStringLiteral("📑 Compile Document"), this);
    compileButton_->setProperty("accent", true);
    connect(compileButton_, &QPushButton::clicked, this, &WritingPage::onCompileClicked);
    topBar->addWidget(compileButton_);

    layout->addLayout(topBar);

    // 3-Pane Splitter: Outline, Editor, Preview
    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Left: Outline Tree
    auto* outlineGroup = new QGroupBox(QStringLiteral("Document Outline"), splitter);
    auto* outlineLayout = new QVBoxLayout(outlineGroup);
    outlineLayout->setContentsMargins(4, 8, 4, 4);

    outlineTree_ = new QTreeWidget(outlineGroup);
    outlineTree_->setColumnCount(2);
    outlineTree_->setHeaderLabels({QStringLiteral("Section"), QStringLiteral("Words")});
    outlineTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    outlineTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    connect(outlineTree_, &QTreeWidget::itemClicked, this, [this](QTreeWidgetItem* item, int) {
        if (item) {
            emit sectionSelected(item->text(0));
        }
    });
    outlineLayout->addWidget(outlineTree_);
    splitter->addWidget(outlineGroup);

    // Center: Section Editor
    auto* editorGroup = new QGroupBox(QStringLiteral("Section Editor"), splitter);
    auto* editorLayout = new QVBoxLayout(editorGroup);
    editorLayout->setContentsMargins(4, 8, 4, 4);

    sectionEditor_ = new CodeEditor(editorGroup);
    sectionEditor_->setFont(QFont(QStringLiteral("Consolas"), 11));
    sectionEditor_->setPlaceholderText(QStringLiteral("Write or edit section draft content here..."));
    connect(sectionEditor_, &CodeEditor::textChanged, this, [this]() {
        updateWordCount();
        updatePreview(sectionEditor_->toPlainText());
    });
    connect(sectionEditor_, &CodeEditor::inlinePromptSubmitted, this, [this](const QString& prompt, const QString& selected, const QString&) {
        emit reviseSectionRequested(selected, prompt);
    });
    editorLayout->addWidget(sectionEditor_);
    splitter->addWidget(editorGroup);

    // Right: Live Markdown Preview
    auto* previewGroup = new QGroupBox(QStringLiteral("Live Markdown Preview"), splitter);
    auto* previewLayout = new QVBoxLayout(previewGroup);
    previewLayout->setContentsMargins(4, 8, 4, 4);

    markdownPreview_ = new QTextEdit(previewGroup);
    markdownPreview_->setReadOnly(true);
    previewLayout->addWidget(markdownPreview_);
    splitter->addWidget(previewGroup);

    splitter->setSizes({220, 500, 480});
    layout->addWidget(splitter, 1);

    // Default sample outline
    setDocumentOutline({
        QStringLiteral("1. Introduction"),
        QStringLiteral("2. Architecture and Invariants"),
        QStringLiteral("3. Benchmark Results"),
        QStringLiteral("4. Conclusion")
    });
}

void WritingPage::setDocumentOutline(const QStringList& sections) {
    outlineTree_->clear();
    for (const auto& s : sections) {
        auto* item = new QTreeWidgetItem(outlineTree_);
        item->setText(0, s);
        item->setText(1, QStringLiteral("0"));
    }
    wordCountLabel_->setText(QStringLiteral("Words: %1 | Sections: %2").arg(0).arg(sections.size()));
}

void WritingPage::setSectionContent(const QString& /* sectionName */, const QString& content) {
    sectionEditor_->setPlainText(content);
    updateWordCount();
    updatePreview(content);
}

QString WritingPage::currentSectionContent() const {
    return sectionEditor_->toPlainText();
}

void WritingPage::updatePreview(const QString& markdown) {
    markdownPreview_->setMarkdown(markdown);
}

void WritingPage::updateWordCount() {
    const QString text = sectionEditor_->toPlainText().trimmed();
    int count = 0;
    if (!text.isEmpty()) {
        const auto parts = text.split(QRegularExpression(QStringLiteral("\\s+")), Qt::SkipEmptyParts);
        count = static_cast<int>(parts.size());
    }
    wordCountLabel_->setText(QStringLiteral("Words: %1 | Sections: %2").arg(count).arg(outlineTree_->topLevelItemCount()));
}

void WritingPage::onCompileClicked() {
    setStatus(QStringLiteral("Compiling document sections..."));
    emit compileDocumentRequested();
}

void WritingPage::onReviseClicked() {
    auto* currentItem = outlineTree_->currentItem();
    const QString secName = currentItem ? currentItem->text(0) : QStringLiteral("Current Section");
    bool ok = false;
    const QString instruction = QInputDialog::getText(this, QStringLiteral("Revise Section with AI"),
                                                      QStringLiteral("Instructions for '%1':").arg(secName),
                                                      QLineEdit::Normal, QStringLiteral("Make it more concise and technical"), &ok);
    if (ok && !instruction.isEmpty()) {
        setStatus(QStringLiteral("Requesting AI revision for '%1'...").arg(secName));
        emit reviseSectionRequested(secName, instruction);
    }
}

}  // namespace aquila::gui

