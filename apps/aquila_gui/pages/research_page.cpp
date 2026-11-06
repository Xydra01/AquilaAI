// apps/aquila_gui/pages/research_page.cpp
#include "research_page.hpp"

#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>

namespace aquila::gui {

ResearchPage::ResearchPage(QWidget* parent)
    : BasePage(QStringLiteral("Research Lab"),
               QStringLiteral("Hybrid Semantic Fact Retrieval, Knowledge Graph, and Web Page Cache"),
               QStringLiteral("🔍"), parent) {
    auto* layout = contentLayout();

    // Search Bar
    auto* searchRow = new QHBoxLayout();
    searchRow->setSpacing(8);

    queryInput_ = new QLineEdit(this);
    queryInput_->setPlaceholderText(QStringLiteral("Enter research topic or semantic query (e.g. 'How does KV rollback work?')..."));
    searchRow->addWidget(queryInput_, 1);

    depthCombo_ = new QComboBox(this);
    depthCombo_->addItems({QStringLiteral("Light (Fast)"), QStringLiteral("Full Research"), QStringLiteral("Offline Knowledge")});
    searchRow->addWidget(depthCombo_);

    searchButton_ = new QPushButton(QStringLiteral("🔍 Search"), this);
    searchButton_->setProperty("accent", true);
    connect(searchButton_, &QPushButton::clicked, this, &ResearchPage::onSearchClicked);
    searchRow->addWidget(searchButton_);

    layout->addLayout(searchRow);

    // 3 Panels: Search Results, Fact Graph, Page Cache
    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Panel 1: Document Search Results
    auto* resGroup = new QGroupBox(QStringLiteral("Hybrid Retrieval Results (Dense + BM25)"), splitter);
    auto* resLayout = new QVBoxLayout(resGroup);
    resLayout->setContentsMargins(4, 8, 4, 4);

    resultsTree_ = new QTreeWidget(resGroup);
    resultsTree_->setColumnCount(3);
    resultsTree_->setHeaderLabels({QStringLiteral("Snippet / Document Chunk"), QStringLiteral("Score"), QStringLiteral("Source")});
    resultsTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    resultsTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    resultsTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    resLayout->addWidget(resultsTree_);
    splitter->addWidget(resGroup);

    // Panel 2: Fact Graph
    auto* factGroup = new QGroupBox(QStringLiteral("Structured Fact Graph (SQLite)"), splitter);
    auto* factLayout = new QVBoxLayout(factGroup);
    factLayout->setContentsMargins(4, 8, 4, 4);

    factTree_ = new QTreeWidget(factGroup);
    factTree_->setColumnCount(3);
    factTree_->setHeaderLabels({QStringLiteral("Established Fact"), QStringLiteral("Confidence"), QStringLiteral("Entity")});
    factTree_->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    factTree_->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    factTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    factLayout->addWidget(factTree_);
    splitter->addWidget(factGroup);

    // Panel 3: Web Page Cache
    auto* cacheGroup = new QGroupBox(QStringLiteral("Page Cache (Zero-I/O Hits)"), splitter);
    auto* cacheLayout = new QVBoxLayout(cacheGroup);
    cacheLayout->setContentsMargins(4, 8, 4, 4);

    cacheTree_ = new QTreeWidget(cacheGroup);
    cacheTree_->setColumnCount(3);
    cacheTree_->setHeaderLabels({QStringLiteral("Title"), QStringLiteral("URL"), QStringLiteral("Cached At")});
    cacheTree_->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    cacheTree_->header()->setSectionResizeMode(1, QHeaderView::Stretch);
    cacheTree_->header()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    cacheLayout->addWidget(cacheTree_);
    splitter->addWidget(cacheGroup);

    splitter->setSizes({420, 420, 360});
    layout->addWidget(splitter, 1);
}

void ResearchPage::onSearchClicked() {
    const QString q = queryInput_->text().trimmed();
    if (q.isEmpty()) return;

    setStatus(QStringLiteral("Searching knowledge base for '%1'...").arg(q));
    emit searchRequested(q, depthCombo_->currentText());
}

void ResearchPage::addSearchResult(const QString& text, double score, const QString& source) {
    auto* item = new QTreeWidgetItem(resultsTree_);
    item->setText(0, text);
    item->setText(1, QString::number(score, 'f', 4));
    item->setText(2, source);
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

void ResearchPage::clearAll() {
    resultsTree_->clear();
    factTree_->clear();
    cacheTree_->clear();
}

}  // namespace aquila::gui

