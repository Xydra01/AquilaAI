// apps/aquila_gui/pages/research_page.hpp
#pragma once

#include "base_page.hpp"

#include <QComboBox>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPixmap>
#include <QPushButton>
#include <QSplitter>
#include <QTabWidget>
#include <QTextEdit>
#include <QTreeWidget>

namespace aquila::gui {

class ResearchPage : public BasePage {
    Q_OBJECT
public:
    explicit ResearchPage(QWidget* parent = nullptr);

    void addSearchResult(const QString& text, double score, const QString& source, const QString& url = QString());
    void addFact(const QString& fact, double confidence, const QString& entity);
    void addCachedPage(const QString& url, const QString& title, const QString& timestamp,
                       const QString& screenshotPath = QString());
    void addScreenshot(const QString& filePath, const QString& title = QString(), const QString& url = QString());
    void loadScreenshotsFromDir(const QString& workspaceRoot);
    void showScreenshotsTab();
    void clearScreenshots(bool deleteFiles = false);
    void setReportMarkdown(const QString& md);
    QString reportMarkdown() const;
    void clearAll();
    int searchResultCount() const;
    int factCount() const;
    int screenshotCount() const;
    bool hasScreenshotPreview() const;

    QString selectedEngine() const;
    QString selectedScope() const;

signals:
    void searchRequested(const QString& query, const QString& depth, const QString& engine, const QString& scope);
    void deepAgentRequested(const QString& query);
    void saveReportRequested(const QString& markdown);
    void sendToArchiveRequested(const QString& topic, const QString& markdown);

protected:
    void resizeEvent(QResizeEvent* event) override;

private slots:
    void onSearchClicked();
    void onDeepAgentClicked();
    void onSaveReportClicked();
    void onSendToArchiveClicked();
    void onCopyMarkdownClicked();
    void onScreenshotSelectionChanged();
    void onScreenshotDoubleClicked(QListWidgetItem* item);
    void onOpenFullSizeScreenshot();
    void onRefreshScreenshots();
    void onOpenScreenshotsFolder();
    void onClearScreenshotsClicked();
    void onCacheItemDoubleClicked(QTreeWidgetItem* item, int column);

private:
    void updateScreenshotsTabTitle();
    void updatePreviewScaling();
    int findScreenshotRowByPath(const QString& canonicalPath) const;

    QLineEdit* queryInput_ = nullptr;
    QComboBox* engineCombo_ = nullptr;
    QComboBox* scopeCombo_ = nullptr;
    QComboBox* depthCombo_ = nullptr;
    QPushButton* searchButton_ = nullptr;
    QPushButton* deepAgentButton_ = nullptr;

    QTreeWidget* resultsTree_ = nullptr;
    QTreeWidget* factTree_ = nullptr;
    QTreeWidget* cacheTree_ = nullptr;
    QTabWidget* findingsTabs_ = nullptr;

    // Screenshot Browser Tab widgets
    QWidget* screenshotsTab_ = nullptr;
    QListWidget* screenshotList_ = nullptr;
    QLabel* screenshotPreviewLabel_ = nullptr;
    QLabel* screenshotMetaLabel_ = nullptr;
    QPushButton* fullSizeShotBtn_ = nullptr;
    QPushButton* refreshShotsBtn_ = nullptr;
    QPushButton* openShotsDirBtn_ = nullptr;
    QPushButton* clearShotsBtn_ = nullptr;
    QPixmap activePreviewPixmap_;
    QString activePreviewPath_;
    QString currentScreenshotsDir_;

    QTextEdit* reportViewer_ = nullptr;
    QPushButton* saveReportBtn_ = nullptr;
    QPushButton* sendToArchiveBtn_ = nullptr;
    QPushButton* copyMarkdownBtn_ = nullptr;
};

}  // namespace aquila::gui
