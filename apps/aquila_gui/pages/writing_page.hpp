// apps/aquila_gui/pages/writing_page.hpp
#pragma once

#include "base_page.hpp"

#include <QLabel>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSplitter>
#include <QTextEdit>
#include <QTreeWidget>

namespace aquila::gui {

class WritingPage : public BasePage {
    Q_OBJECT
public:
    explicit WritingPage(QWidget* parent = nullptr);

    void setDocumentOutline(const QStringList& sections);
    void setSectionContent(const QString& sectionName, const QString& content);
    QString currentSectionContent() const;
    void updatePreview(const QString& markdown);

signals:
    void sectionSelected(const QString& sectionName);
    void reviseSectionRequested(const QString& sectionName, const QString& instruction);
    void compileDocumentRequested();

private:
    void onCompileClicked();
    void onReviseClicked();
    void updateWordCount();

    QTreeWidget* outlineTree_ = nullptr;
    QPlainTextEdit* sectionEditor_ = nullptr;
    QTextEdit* markdownPreview_ = nullptr;
    QLabel* wordCountLabel_ = nullptr;
    QPushButton* compileButton_ = nullptr;
    QPushButton* reviseButton_ = nullptr;
};

}  // namespace aquila::gui

