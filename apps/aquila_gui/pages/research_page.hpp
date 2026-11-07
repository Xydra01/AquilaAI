// apps/aquila_gui/pages/research_page.hpp
#pragma once

#include "base_page.hpp"

#include <QComboBox>
#include <QLineEdit>
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
    void addCachedPage(const QString& url, const QString& title, const QString& timestamp);
    void setReportMarkdown(const QString& md);
    QString reportMarkdown() const;
    void clearAll();
    int searchResultCount() const;
    int factCount() const;

    QString selectedEngine() const;
    QString selectedScope() const;

signals:
    void searchRequested(const QString& query, const QString& depth, const QString& engine, const QString& scope);
    void saveReportRequested(const QString& markdown);
    void sendToArchiveRequested(const QString& topic, const QString& markdown);

private slots:
    void onSearchClicked();
    void onSaveReportClicked();
    void onSendToArchiveClicked();
    void onCopyMarkdownClicked();

private:
    QLineEdit* queryInput_ = nullptr;
    QComboBox* engineCombo_ = nullptr;
    QComboBox* scopeCombo_ = nullptr;
    QComboBox* depthCombo_ = nullptr;
    QPushButton* searchButton_ = nullptr;

    QTreeWidget* resultsTree_ = nullptr;
    QTreeWidget* factTree_ = nullptr;
    QTreeWidget* cacheTree_ = nullptr;
    QTabWidget* findingsTabs_ = nullptr;

    QTextEdit* reportViewer_ = nullptr;
    QPushButton* saveReportBtn_ = nullptr;
    QPushButton* sendToArchiveBtn_ = nullptr;
    QPushButton* copyMarkdownBtn_ = nullptr;
};

}  // namespace aquila::gui
