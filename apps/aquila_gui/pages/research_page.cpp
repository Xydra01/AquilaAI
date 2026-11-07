// apps/aquila_gui/pages/research_page.cpp
#include "research_page.hpp"

#include <QClipboard>
#include <QFileDialog>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QMessageBox>
#include <QVBoxLayout>
#include <QGuiApplication>

namespace aquila::gui {

ResearchPage::ResearchPage(QWidget* parent)
    : BasePage(QStringLiteral("Research Lab"),
               QStringLiteral("Multi-Engine Web Search, Grounded Synthesis, and Fact Graph"),
               QStringLiteral("🔍"), parent) {
    auto* layout = contentLayout();

    // Top Search Row
    auto* searchRow = new QHBoxLayout();
    searchRow->setSpacing(8);

    queryInput_ = new QLineEdit(this);
    queryInput_->setPlaceholderText(QStringLiteral("Enter research topic or technical query (e.g. 'What are the latest features in C++26?')..."));
    searchRow->addWidget(queryInput_, 2);

    engineCombo_ = new QComboBox(this);
    engineCombo_->addItems({
        QStringLiteral("DuckDuckGo (Free)"),
        QStringLiteral("SearXNG (127.0.0.1:8888)"),
        QStringLiteral("Wikipedia"),
        QStringLiteral("Local Docs Only")
    });
    searchRow->addWidget(engineCombo_);

    scopeCombo_ = new QComboBox(this);
    scopeCombo_->addItems({
        QStringLiteral("Web + Local Knowledge"),
        QStringLiteral("Web Only"),
        QStringLiteral("Local Corpus Only")
    });
    searchRow->addWidget(scopeCombo_);

    depthCombo_ = new QComboBox(this);
    depthCombo_->addItems({QStringLiteral("Light"), QStringLiteral("Full Deep Research")});
    searchRow->addWidget(depthCombo_);

    searchButton_ = new QPushButton(QStringLiteral("🔍 Run Research"), this);
    searchButton_->setProperty("accent", true);
    connect(searchButton_, &QPushButton::clicked, this, &ResearchPage::onSearchClicked);
    connect(queryInput_, &QLineEdit::returnPressed, this, &ResearchPage::onSearchClicked);
    searchRow->addWidget(searchButton_);

    layout->addLayout(searchRow);

    // Main Splitter: Left Pane (Sources & Findings), Right Pane (Synthesis & Deliverable)
    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Left Pane
    auto* leftWidget = new QWidget(splitter);
    auto* leftLayout = new QVBoxLayout(leftWidget);
    leftLayout->setContentsMargins(0, 0, 0, 0);

    auto* resGroup = new QGroupBox(QStringLiteral("Ranked Search Results (Relevance & Authority)"), leftWidget);
    auto* resLayout = new QVBoxLayout(resGroup);
    resLayout->setContentsMargins(4, 8, 4, 4);

    resultsTree_ = new QTreeWidget(resGroup);
    resultsTree_->setColumnCount(4);
    resultsTree_->setHeaderLabels({
        QStringLiteral("Title / Snippet"),
        QStringLiteral("Score"),
        QStringLiteral("Source"),
        QStringLiteral("URL")
    });
    resultsTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    resultsTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    resultsTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    resultsTree_->header()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    resLayout->addWidget(resultsTree_);
    leftLayout->addWidget(resGroup, 3);

    // Findings Tabs (Fact Graph & Page Cache)
    findingsTabs_ = new QTabWidget(leftWidget);

    // Tab 1: Fact Graph
    factTree_ = new QTreeWidget(findingsTabs_);
    factTree_->setColumnCount(3);
    factTree_->setHeaderLabels({QStringLiteral("Established Fact"), QStringLiteral("Confidence"), QStringLiteral("Entity")});
    factTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    factTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    factTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    findingsTabs_->addTab(factTree_, QStringLiteral("Verified Facts"));

    // Tab 2: Page Cache
    cacheTree_ = new QTreeWidget(findingsTabs_);
    cacheTree_->setColumnCount(3);
    cacheTree_->setHeaderLabels({QStringLiteral("Title"), QStringLiteral("URL"), QStringLiteral("Cached At")});
    cacheTree_->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    cacheTree_->header()->setSectionResizeMode(1, QHeaderView::Stretch);
    cacheTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    findingsTabs_->addTab(cacheTree_, QStringLiteral("Scraped Web Cache"));

    leftLayout->addWidget(findingsTabs_, 2);
    splitter->addWidget(leftWidget);

    // Right Pane: Synthesis & Report Viewer
    auto* rightWidget = new QWidget(splitter);
    auto* rightLayout = new QVBoxLayout(rightWidget);
    rightLayout->setContentsMargins(0, 0, 0, 0);

    auto* reportGroup = new QGroupBox(QStringLiteral("Research Synthesis Report (Live Markdown)"), rightWidget);
    auto* reportGroupLayout = new QVBoxLayout(reportGroup);
    reportGroupLayout->setContentsMargins(4, 8, 4, 4);

    reportViewer_ = new QTextEdit(reportGroup);
    reportViewer_->setReadOnly(true);
    reportViewer_->setPlaceholderText(QStringLiteral("Synthesized research findings, verified facts, and references will appear here..."));
    reportGroupLayout->addWidget(reportViewer_, 1);

    auto* btnRow = new QHBoxLayout();
    btnRow->setSpacing(8);

    saveReportBtn_ = new QPushButton(QStringLiteral("💾 Save Report"), reportGroup);
    connect(saveReportBtn_, &QPushButton::clicked, this, &ResearchPage::onSaveReportClicked);
    btnRow->addWidget(saveReportBtn_);

    sendToArchiveBtn_ = new QPushButton(QStringLiteral("🎓 Add to Course Archive"), reportGroup);
    connect(sendToArchiveBtn_, &QPushButton::clicked, this, &ResearchPage::onSendToArchiveClicked);
    btnRow->addWidget(sendToArchiveBtn_);

    copyMarkdownBtn_ = new QPushButton(QStringLiteral("📋 Copy Markdown"), reportGroup);
    connect(copyMarkdownBtn_, &QPushButton::clicked, this, &ResearchPage::onCopyMarkdownClicked);
    btnRow->addWidget(copyMarkdownBtn_);

    btnRow->addStretch();
    reportGroupLayout->addLayout(btnRow);

    rightLayout->addWidget(reportGroup);
    splitter->addWidget(rightWidget);

    splitter->setSizes({550, 650});
    layout->addWidget(splitter, 1);
}

QString ResearchPage::selectedEngine() const {
    const QString txt = engineCombo_->currentText();
    if (txt.contains(QStringLiteral("DuckDuckGo"))) return QStringLiteral("duckduckgo");
    if (txt.contains(QStringLiteral("SearXNG"))) return QStringLiteral("searxng");
    if (txt.contains(QStringLiteral("Wikipedia"))) return QStringLiteral("wikipedia");
    return QStringLiteral("local");
}

QString ResearchPage::selectedScope() const {
    return scopeCombo_->currentText();
}

void ResearchPage::onSearchClicked() {
    const QString q = queryInput_->text().trimmed();
    if (q.isEmpty()) return;

    setStatus(QStringLiteral("Researching '%1' via %2...").arg(q, engineCombo_->currentText()));
    emit searchRequested(q, depthCombo_->currentText(), selectedEngine(), selectedScope());
}

void ResearchPage::onSaveReportClicked() {
    const QString md = reportMarkdown();
    if (md.isEmpty()) {
        QMessageBox::information(this, QStringLiteral("Save Report"), QStringLiteral("No research report to save yet. Run a search first."));
        return;
    }
    emit saveReportRequested(md);
}

void ResearchPage::onSendToArchiveClicked() {
    const QString md = reportMarkdown();
    const QString q = queryInput_->text().trimmed();
    if (md.isEmpty()) {
        QMessageBox::information(this, QStringLiteral("Add to Archive"), QStringLiteral("No research report to archive. Run a search first."));
        return;
    }
    emit sendToArchiveRequested(q.isEmpty() ? QStringLiteral("Research Findings") : q, md);
}

void ResearchPage::onCopyMarkdownClicked() {
    const QString md = reportMarkdown();
    if (!md.isEmpty()) {
        QGuiApplication::clipboard()->setText(md);
        setStatus(QStringLiteral("Research report copied to clipboard."));
    }
}

void ResearchPage::addSearchResult(const QString& text, double score, const QString& source, const QString& url) {
    auto* item = new QTreeWidgetItem(resultsTree_);
    item->setText(0, text);
    item->setText(1, QString::number(score, 'f', 1));
    item->setText(2, source);
    item->setText(3, url);
}

void ResearchPage::addFact(const QString& fact, double confidence, const QString& entity) {
    auto* item = new QTreeWidgetItem(factTree_);
    item->setText(0, fact);
    item->setText(1, QString::number(confidence, 'f', 2));
    item->setText(2, entity);
}

void ResearchPage::addCachedPage(const QString& url, const QString& title, const QString& timestamp) {
    auto* item = new QTreeWidgetItem(cacheTree_);
    item->setText(0, title);
    item->setText(1, url);
    item->setText(2, timestamp);
}

void ResearchPage::setReportMarkdown(const QString& md) {
    reportViewer_->setMarkdown(md);
}

QString ResearchPage::reportMarkdown() const {
    return reportViewer_->toMarkdown();
}

void ResearchPage::clearAll() {
    resultsTree_->clear();
    factTree_->clear();
    cacheTree_->clear();
    reportViewer_->clear();
}

int ResearchPage::searchResultCount() const {
    return resultsTree_->topLevelItemCount();
}

int ResearchPage::factCount() const {
    return factTree_->topLevelItemCount();
}

}  // namespace aquila::gui
