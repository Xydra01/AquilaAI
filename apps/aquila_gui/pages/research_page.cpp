// apps/aquila_gui/pages/research_page.cpp
#include "research_page.hpp"

#include <QClipboard>
#include <QDateTime>
#include <QDesktopServices>
#include <QDialog>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QGroupBox>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QMessageBox>
#include <QResizeEvent>
#include <QScrollArea>
#include <QUrl>
#include <QVBoxLayout>

namespace aquila::gui {

namespace {
constexpr int kRoleFilePath = Qt::UserRole + 1;
constexpr int kRoleTitle = Qt::UserRole + 2;
constexpr int kRoleUrl = Qt::UserRole + 3;
constexpr int kRoleCanonical = Qt::UserRole + 4;
}  // namespace

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
        QStringLiteral("SearXNG (Local Multi-Source Default)"),
        QStringLiteral("Headless Browser (aquila_browser)"),
        QStringLiteral("DuckDuckGo (Free)"),
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

    deepAgentButton_ = new QPushButton(QStringLiteral("🤖 Run Deep Agent"), this);
    deepAgentButton_->setToolTip(QStringLiteral("Launch the autonomous multi-turn fn_research_full agent in Task Center"));
    connect(deepAgentButton_, &QPushButton::clicked, this, &ResearchPage::onDeepAgentClicked);
    searchRow->addWidget(deepAgentButton_);

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
    connect(cacheTree_, &QTreeWidget::itemDoubleClicked, this, &ResearchPage::onCacheItemDoubleClicked);
    findingsTabs_->addTab(cacheTree_, QStringLiteral("Scraped Web Cache"));

    // Tab 3: Browser Screenshots
    screenshotsTab_ = new QWidget(findingsTabs_);
    auto* shotsMainLayout = new QVBoxLayout(screenshotsTab_);
    shotsMainLayout->setContentsMargins(6, 6, 6, 6);
    shotsMainLayout->setSpacing(6);

    auto* shotsToolbar = new QHBoxLayout();
    shotsToolbar->setSpacing(6);

    refreshShotsBtn_ = new QPushButton(QStringLiteral("🔄 Refresh"), screenshotsTab_);
    refreshShotsBtn_->setToolTip(QStringLiteral("Rescan .aquila/browser_screenshots/ for newly saved captures"));
    connect(refreshShotsBtn_, &QPushButton::clicked, this, &ResearchPage::onRefreshScreenshots);
    shotsToolbar->addWidget(refreshShotsBtn_);

    openShotsDirBtn_ = new QPushButton(QStringLiteral("📂 Open Folder"), screenshotsTab_);
    openShotsDirBtn_->setToolTip(QStringLiteral("Open the browser screenshots directory in Explorer"));
    connect(openShotsDirBtn_, &QPushButton::clicked, this, &ResearchPage::onOpenScreenshotsFolder);
    shotsToolbar->addWidget(openShotsDirBtn_);

    fullSizeShotBtn_ = new QPushButton(QStringLiteral("🔍 Full Size"), screenshotsTab_);
    fullSizeShotBtn_->setEnabled(false);
    connect(fullSizeShotBtn_, &QPushButton::clicked, this, &ResearchPage::onOpenFullSizeScreenshot);
    shotsToolbar->addWidget(fullSizeShotBtn_);

    shotsToolbar->addStretch();

    clearShotsBtn_ = new QPushButton(QStringLiteral("🗑️ Clear"), screenshotsTab_);
    clearShotsBtn_->setToolTip(QStringLiteral("Delete saved screenshots from .aquila/browser_screenshots/"));
    connect(clearShotsBtn_, &QPushButton::clicked, this, &ResearchPage::onClearScreenshotsClicked);
    shotsToolbar->addWidget(clearShotsBtn_);

    shotsMainLayout->addLayout(shotsToolbar);

    auto* shotsSplitter = new QSplitter(Qt::Horizontal, screenshotsTab_);

    screenshotList_ = new QListWidget(shotsSplitter);
    screenshotList_->setIconSize(QSize(88, 55));
    screenshotList_->setSpacing(4);
    screenshotList_->setUniformItemSizes(false);
    screenshotList_->setWordWrap(false);
    screenshotList_->setTextElideMode(Qt::ElideRight);
    screenshotList_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    screenshotList_->setMinimumWidth(200);
    connect(screenshotList_, &QListWidget::itemSelectionChanged, this, &ResearchPage::onScreenshotSelectionChanged);
    connect(screenshotList_, &QListWidget::itemDoubleClicked, this, &ResearchPage::onScreenshotDoubleClicked);
    shotsSplitter->addWidget(screenshotList_);

    auto* previewPane = new QWidget(shotsSplitter);
    auto* previewLayout = new QVBoxLayout(previewPane);
    previewLayout->setContentsMargins(4, 0, 0, 0);
    previewLayout->setSpacing(4);

    screenshotPreviewLabel_ = new QLabel(QStringLiteral("No screenshot selected.\nRun a web search or autonomous research task to capture rendered pages."), previewPane);
    screenshotPreviewLabel_->setAlignment(Qt::AlignCenter);
    screenshotPreviewLabel_->setWordWrap(true);
    screenshotPreviewLabel_->setMinimumSize(220, 140);
    screenshotPreviewLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    screenshotPreviewLabel_->setStyleSheet(QStringLiteral("QLabel { background-color: #0f172a; color: #94a3b8; border: 1px solid #334155; border-radius: 6px; padding: 8px; }"));
    previewLayout->addWidget(screenshotPreviewLabel_, 1);

    screenshotMetaLabel_ = new QLabel(QString(), previewPane);
    screenshotMetaLabel_->setWordWrap(true);
    screenshotMetaLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    screenshotMetaLabel_->setStyleSheet(QStringLiteral("QLabel { color: #94a3b8; font-size: 11px; }"));
    previewLayout->addWidget(screenshotMetaLabel_);

    shotsSplitter->addWidget(previewPane);
    shotsSplitter->setSizes({230, 340});
    shotsMainLayout->addWidget(shotsSplitter, 1);

    findingsTabs_->addTab(screenshotsTab_, QStringLiteral("📸 Screenshots (0)"));

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
    if (txt.contains(QStringLiteral("SearXNG"), Qt::CaseInsensitive)) return QStringLiteral("searxng");
    if (txt.contains(QStringLiteral("Browser"), Qt::CaseInsensitive)) return QStringLiteral("browser");
    if (txt.contains(QStringLiteral("DuckDuckGo"), Qt::CaseInsensitive)) return QStringLiteral("duckduckgo");
    if (txt.contains(QStringLiteral("Wikipedia"), Qt::CaseInsensitive)) return QStringLiteral("wikipedia");
    return QStringLiteral("local");
}

QString ResearchPage::selectedScope() const {
    const QString txt = scopeCombo_->currentText();
    if (txt.contains(QStringLiteral("Web"), Qt::CaseInsensitive) && txt.contains(QStringLiteral("Local"), Qt::CaseInsensitive)) {
        return QStringLiteral("Both");
    }
    if (txt.contains(QStringLiteral("Web"), Qt::CaseInsensitive)) {
        return QStringLiteral("Web");
    }
    return QStringLiteral("Local");
}

void ResearchPage::onSearchClicked() {
    const QString q = queryInput_->text().trimmed();
    if (q.isEmpty()) return;

    setStatus(QStringLiteral("Researching '%1' via %2...").arg(q, engineCombo_->currentText()));
    emit searchRequested(q, depthCombo_->currentText(), selectedEngine(), selectedScope());
}

void ResearchPage::onDeepAgentClicked() {
    const QString q = queryInput_->text().trimmed();
    if (q.isEmpty()) {
        QMessageBox::information(this, QStringLiteral("Run Deep Agent"),
                                 QStringLiteral("Enter a research topic first to launch the autonomous deep research agent."));
        return;
    }
    setStatus(QStringLiteral("Launching autonomous fn_research_full agent for '%1'...").arg(q));
    emit deepAgentRequested(q);
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

void ResearchPage::addCachedPage(const QString& url, const QString& title, const QString& timestamp,
                                 const QString& screenshotPath) {
    auto* item = new QTreeWidgetItem(cacheTree_);
    item->setText(0, title);
    item->setText(1, url);
    item->setText(2, timestamp);
    if (!screenshotPath.isEmpty()) {
        item->setData(0, kRoleFilePath, screenshotPath);
        item->setToolTip(0, QStringLiteral("Double-click to view captured screenshot:\n%1").arg(screenshotPath));
        item->setToolTip(2, QStringLiteral("Double-click to view captured screenshot"));
    }
}

int ResearchPage::findScreenshotRowByPath(const QString& canonicalPath) const {
    if (!screenshotList_ || canonicalPath.isEmpty()) return -1;
    for (int i = 0; i < screenshotList_->count(); ++i) {
        const auto* item = screenshotList_->item(i);
        if (item && item->data(kRoleCanonical).toString().compare(canonicalPath, Qt::CaseInsensitive) == 0) {
            return i;
        }
    }
    return -1;
}

void ResearchPage::addScreenshot(const QString& filePath, const QString& title, const QString& url) {
    if (!screenshotList_ || filePath.isEmpty()) return;
    const QFileInfo fi(filePath);
    if (!fi.exists() || !fi.isFile()) return;

    const QString canonical = fi.canonicalFilePath().isEmpty() ? fi.absoluteFilePath() : fi.canonicalFilePath();
    const QPixmap pix(fi.absoluteFilePath());
    if (pix.isNull()) return;

    const QString displayTitle = title.trimmed().isEmpty() ? fi.fileName() : title.trimmed();
    const QString stamp = fi.lastModified().toString(QStringLiteral("MM-dd HH:mm"));
    const QString labelText = QStringLiteral("%1\n%2 · %3x%4")
                                  .arg(displayTitle.left(32), stamp)
                                  .arg(pix.width())
                                  .arg(pix.height());

    const QPixmap thumb = pix.scaled(QSize(88, 55), Qt::KeepAspectRatio, Qt::SmoothTransformation);
    const int existingRow = findScreenshotRowByPath(canonical);
    QListWidgetItem* item = nullptr;
    if (existingRow >= 0) {
        item = screenshotList_->item(existingRow);
        item->setIcon(QIcon(thumb));
        item->setText(labelText);
    } else {
        item = new QListWidgetItem(QIcon(thumb), labelText);
        screenshotList_->insertItem(0, item);
    }

    item->setData(kRoleFilePath, QDir::toNativeSeparators(fi.absoluteFilePath()));
    item->setData(kRoleCanonical, canonical);
    if (!title.trimmed().isEmpty() || item->data(kRoleTitle).toString().isEmpty()) {
        item->setData(kRoleTitle, displayTitle);
    }
    if (!url.trimmed().isEmpty()) {
        item->setData(kRoleUrl, url.trimmed());
    }
    QString tip = QStringLiteral("%1\nFile: %2\nResolution: %3x%4")
                      .arg(displayTitle, QDir::toNativeSeparators(fi.absoluteFilePath()))
                      .arg(pix.width())
                      .arg(pix.height());
    if (!url.trimmed().isEmpty()) {
        tip += QStringLiteral("\nURL: %1").arg(url.trimmed());
    }
    item->setToolTip(tip);

    if (currentScreenshotsDir_.isEmpty()) {
        currentScreenshotsDir_ = fi.absolutePath();
    }

    updateScreenshotsTabTitle();
    screenshotList_->setCurrentItem(item);
}

void ResearchPage::loadScreenshotsFromDir(const QString& workspaceRoot) {
    if (!screenshotList_) return;
    const QString base = workspaceRoot.trimmed().isEmpty() ? QDir::currentPath() : workspaceRoot.trimmed();
    const QDir dir(QDir(base).filePath(QStringLiteral(".aquila/browser_screenshots")));
    currentScreenshotsDir_ = QDir::toNativeSeparators(dir.absolutePath());

    if (!dir.exists()) {
        updateScreenshotsTabTitle();
        return;
    }

    // Remove stale items whose files were deleted externally.
    for (int i = screenshotList_->count() - 1; i >= 0; --i) {
        const auto* item = screenshotList_->item(i);
        if (!item || !QFileInfo::exists(item->data(kRoleFilePath).toString())) {
            delete screenshotList_->takeItem(i);
        }
    }

    const QFileInfoList files = dir.entryInfoList(
        {QStringLiteral("*.png")}, QDir::Files | QDir::Readable, QDir::Time);
    // entryInfoList(QDir::Time) returns newest first; iterate oldest-to-newest so newest ends up at row 0.
    for (int i = static_cast<int>(files.size()) - 1; i >= 0; --i) {
        const QFileInfo& fi = files.at(i);
        const QString canonical = fi.canonicalFilePath().isEmpty() ? fi.absoluteFilePath() : fi.canonicalFilePath();
        if (findScreenshotRowByPath(canonical) >= 0) {
            continue;
        }
        const QPixmap pix(fi.absoluteFilePath());
        if (pix.isNull()) continue;

        const QString stamp = fi.lastModified().toString(QStringLiteral("MM-dd HH:mm"));
        const QString labelText = QStringLiteral("%1\n%2 · %3x%4")
                                      .arg(fi.fileName().left(32), stamp)
                                      .arg(pix.width())
                                      .arg(pix.height());
        const QPixmap thumb = pix.scaled(QSize(88, 55), Qt::KeepAspectRatio, Qt::SmoothTransformation);
        auto* item = new QListWidgetItem(QIcon(thumb), labelText);
        item->setData(kRoleFilePath, QDir::toNativeSeparators(fi.absoluteFilePath()));
        item->setData(kRoleCanonical, canonical);
        item->setData(kRoleTitle, fi.fileName());
        item->setToolTip(QStringLiteral("File: %1\nResolution: %2x%3")
                             .arg(QDir::toNativeSeparators(fi.absoluteFilePath()))
                             .arg(pix.width())
                             .arg(pix.height()));
        screenshotList_->insertItem(0, item);
    }

    updateScreenshotsTabTitle();
    if (screenshotList_->count() > 0 && !screenshotList_->currentItem()) {
        screenshotList_->setCurrentRow(0);
    }
}

void ResearchPage::showScreenshotsTab() {
    if (findingsTabs_ && screenshotsTab_) {
        findingsTabs_->setCurrentWidget(screenshotsTab_);
    }
}

void ResearchPage::clearScreenshots(bool deleteFiles) {
    if (!screenshotList_) return;
    if (deleteFiles) {
        for (int i = 0; i < screenshotList_->count(); ++i) {
            const auto* item = screenshotList_->item(i);
            if (item) {
                QFile::remove(item->data(kRoleFilePath).toString());
            }
        }
    }
    screenshotList_->clear();
    activePreviewPixmap_ = QPixmap();
    activePreviewPath_.clear();
    if (screenshotPreviewLabel_) {
        screenshotPreviewLabel_->setPixmap(QPixmap());
        screenshotPreviewLabel_->setText(
            QStringLiteral("No screenshot selected.\nRun a web search or autonomous research task to capture rendered pages."));
    }
    if (screenshotMetaLabel_) {
        screenshotMetaLabel_->clear();
    }
    if (fullSizeShotBtn_) {
        fullSizeShotBtn_->setEnabled(false);
    }
    updateScreenshotsTabTitle();
}

void ResearchPage::updateScreenshotsTabTitle() {
    if (!findingsTabs_ || !screenshotsTab_) return;
    const int idx = findingsTabs_->indexOf(screenshotsTab_);
    if (idx >= 0) {
        findingsTabs_->setTabText(idx, QStringLiteral("📸 Screenshots (%1)").arg(screenshotCount()));
    }
}

void ResearchPage::updatePreviewScaling() {
    if (!screenshotPreviewLabel_ || activePreviewPixmap_.isNull()) return;
    const QSize target = screenshotPreviewLabel_->contentsRect().size();
    if (target.width() < 16 || target.height() < 16) return;
    screenshotPreviewLabel_->setPixmap(
        activePreviewPixmap_.scaled(target, Qt::KeepAspectRatio, Qt::SmoothTransformation));
}

void ResearchPage::resizeEvent(QResizeEvent* event) {
    BasePage::resizeEvent(event);
    updatePreviewScaling();
}

void ResearchPage::onScreenshotSelectionChanged() {
    if (!screenshotList_) return;
    const auto* item = screenshotList_->currentItem();
    if (!item) {
        activePreviewPixmap_ = QPixmap();
        activePreviewPath_.clear();
        screenshotPreviewLabel_->setPixmap(QPixmap());
        screenshotPreviewLabel_->setText(QStringLiteral("Select a screenshot to preview."));
        screenshotMetaLabel_->clear();
        fullSizeShotBtn_->setEnabled(false);
        return;
    }

    const QString path = item->data(kRoleFilePath).toString();
    const QString title = item->data(kRoleTitle).toString();
    const QString url = item->data(kRoleUrl).toString();

    QPixmap pix(path);
    if (pix.isNull()) {
        activePreviewPixmap_ = QPixmap();
        activePreviewPath_.clear();
        screenshotPreviewLabel_->setPixmap(QPixmap());
        screenshotPreviewLabel_->setText(QStringLiteral("Unable to load screenshot:\n%1").arg(path));
        screenshotMetaLabel_->clear();
        fullSizeShotBtn_->setEnabled(false);
        return;
    }

    activePreviewPixmap_ = pix;
    activePreviewPath_ = path;
    screenshotPreviewLabel_->setText(QString());
    updatePreviewScaling();

    QString meta = QStringLiteral("<b>%1</b> — %2x%3").arg(title.toHtmlEscaped()).arg(pix.width()).arg(pix.height());
    if (!url.isEmpty()) {
        meta += QStringLiteral("<br/>URL: %1").arg(url.toHtmlEscaped());
    }
    meta += QStringLiteral("<br/>Path: %1").arg(path.toHtmlEscaped());
    screenshotMetaLabel_->setText(meta);
    fullSizeShotBtn_->setEnabled(true);
}

void ResearchPage::onScreenshotDoubleClicked(QListWidgetItem* item) {
    if (!item) return;
    screenshotList_->setCurrentItem(item);
    onOpenFullSizeScreenshot();
}

void ResearchPage::onOpenFullSizeScreenshot() {
    if (activePreviewPixmap_.isNull()) return;
    auto* dlg = new QDialog(this);
    dlg->setAttribute(Qt::WA_DeleteOnClose);
    dlg->setWindowTitle(QStringLiteral("Screenshot Preview — %1").arg(QFileInfo(activePreviewPath_).fileName()));
    dlg->resize(1024, 680);

    auto* vbox = new QVBoxLayout(dlg);
    auto* scroll = new QScrollArea(dlg);
    scroll->setWidgetResizable(false);
    scroll->setAlignment(Qt::AlignCenter);
    auto* imgLabel = new QLabel(scroll);
    imgLabel->setPixmap(activePreviewPixmap_);
    imgLabel->adjustSize();
    scroll->setWidget(imgLabel);
    vbox->addWidget(scroll, 1);

    auto* pathLbl = new QLabel(activePreviewPath_, dlg);
    pathLbl->setTextInteractionFlags(Qt::TextSelectableByMouse);
    pathLbl->setStyleSheet(QStringLiteral("QLabel { color: #94a3b8; font-size: 11px; }"));
    vbox->addWidget(pathLbl);

    dlg->exec();
}

void ResearchPage::onRefreshScreenshots() {
    if (currentScreenshotsDir_.isEmpty()) return;
    QDir d(currentScreenshotsDir_);
    // currentScreenshotsDir_ is <workspaceRoot>/.aquila/browser_screenshots
    d.cdUp();
    d.cdUp();
    loadScreenshotsFromDir(d.absolutePath());
    setStatus(QStringLiteral("Refreshed screenshots (%1 total).").arg(screenshotCount()));
}

void ResearchPage::onOpenScreenshotsFolder() {
    if (currentScreenshotsDir_.isEmpty()) return;
    QDir().mkpath(currentScreenshotsDir_);
    QDesktopServices::openUrl(QUrl::fromLocalFile(currentScreenshotsDir_));
}

void ResearchPage::onClearScreenshotsClicked() {
    if (screenshotCount() == 0) return;
    const auto reply = QMessageBox::question(
        this,
        QStringLiteral("Clear Browser Screenshots"),
        QStringLiteral("Delete %1 saved screenshot(s) from:\n%2?")
            .arg(screenshotCount())
            .arg(currentScreenshotsDir_),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);
    if (reply == QMessageBox::Yes) {
        clearScreenshots(true);
        setStatus(QStringLiteral("Cleared saved browser screenshots."));
    }
}

void ResearchPage::onCacheItemDoubleClicked(QTreeWidgetItem* item, int) {
    if (!item) return;
    const QString shotPath = item->data(0, kRoleFilePath).toString();
    if (shotPath.isEmpty()) return;
    const QFileInfo fi(shotPath);
    const QString canonical = fi.canonicalFilePath().isEmpty() ? fi.absoluteFilePath() : fi.canonicalFilePath();
    int row = findScreenshotRowByPath(canonical);
    if (row < 0 && fi.exists()) {
        addScreenshot(shotPath, item->text(0), item->text(1));
        row = findScreenshotRowByPath(canonical);
    }
    if (row >= 0) {
        showScreenshotsTab();
        screenshotList_->setCurrentRow(row);
    }
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
    // Option A: keep screenshotsTab_ folder-backed across searches; only refresh/prepend new captures.
}

int ResearchPage::searchResultCount() const {
    return resultsTree_->topLevelItemCount();
}

int ResearchPage::factCount() const {
    return factTree_->topLevelItemCount();
}

int ResearchPage::screenshotCount() const {
    return screenshotList_ ? screenshotList_->count() : 0;
}

bool ResearchPage::hasScreenshotPreview() const {
    return !activePreviewPixmap_.isNull();
}

}  // namespace aquila::gui
