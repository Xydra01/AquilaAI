// apps/aquila_gui/pages/code_ide_page.hpp
#pragma once

#include "base_page.hpp"
#include "../widgets/code_editor.hpp"
#include "../widgets/pending_patch_widget.hpp"

#include <QFileSystemModel>
#include <QScrollArea>
#include <QSplitter>
#include <QTabWidget>
#include <QTreeView>
#include <QVBoxLayout>

namespace aquila::gui {

class CodeIdePage : public BasePage {
    Q_OBJECT
public:
    explicit CodeIdePage(QWidget* parent = nullptr);

    void setWorkspaceRoot(const QString& path);
    void openFile(const QString& filePath);
    CodeEditor* currentEditor() const;
    void addPendingPatch(const QString& filePath, const QString& diffText);
    void clearPendingPatches();

signals:
    void agentSubcallRequested(const QString& selectedText, const QString& filePath);
    void inlineEditRequested(const QString& prompt, const QString& selectedText, const QString& filePath);
    void patchAccepted(const QString& filePath);
    void patchRejected(const QString& filePath);

private slots:
    void onFileDoubleClicked(const QModelIndex& index);
    void onTabCloseRequested(int index);

private:
    QTreeView* fileTree_ = nullptr;
    QFileSystemModel* fileModel_ = nullptr;
    QTabWidget* editorTabs_ = nullptr;

    QWidget* patchesContainer_ = nullptr;
    QVBoxLayout* patchesLayout_ = nullptr;
    QScrollArea* patchesScroll_ = nullptr;
    QString workspaceRoot_ = ".";
};

}  // namespace aquila::gui

