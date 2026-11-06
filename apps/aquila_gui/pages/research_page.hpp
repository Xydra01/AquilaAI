// apps/aquila_gui/pages/research_page.hpp
#pragma once

#include "base_page.hpp"

#include <QComboBox>
#include <QLineEdit>
#include <QPushButton>
#include <QSplitter>
#include <QTreeWidget>

namespace aquila::gui {

class ResearchPage : public BasePage {
    Q_OBJECT
public:
    explicit ResearchPage(QWidget* parent = nullptr);

    void addSearchResult(const QString& text, double score, const QString& source);
    void addFact(const QString& fact, double confidence, const QString& entity);
    void addCachedPage(const QString& url, const QString& title, const QString& timestamp);
    void clearAll();
    int searchResultCount() const;
    int factCount() const;

signals:
    void searchRequested(const QString& query, const QString& depth);

private:
    void onSearchClicked();

    QLineEdit* queryInput_ = nullptr;
    QComboBox* depthCombo_ = nullptr;
    QPushButton* searchButton_ = nullptr;

    QTreeWidget* resultsTree_ = nullptr;
    QTreeWidget* factTree_ = nullptr;
    QTreeWidget* cacheTree_ = nullptr;
};

}  // namespace aquila::gui

