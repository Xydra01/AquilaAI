// apps/aquila_gui/pages/code_ide_page.cpp
#include "code_ide_page.hpp"

#include <QFile>
#include <QFileInfo>
#include <QGroupBox>
#include <QHeaderView>
#include <QMessageBox>

namespace aquila::gui {

CodeIdePage::CodeIdePage(QWidget* parent)
    : BasePage(QStringLiteral("Code IDE"),
               QStringLiteral("Living Code Canvas, File Tree Navigation, and Pending Patches"),
               QStringLiteral("💻"), parent) {
    auto* layout = contentLayout();

    auto* splitter = new QSplitter(Qt::Horizontal, this);

    // Pane 1: File Explorer Tree
    auto* leftGroup = new QGroupBox(QStringLiteral("Workspace Explorer"), splitter);
    auto* leftLayout = new QVBoxLayout(leftGroup);
    leftLayout->setContentsMargins(4, 8, 4, 4);

    fileTree_ = new QTreeView(leftGroup);
    fileModel_ = new QFileSystemModel(this);
    fileModel_->setRootPath(QStringLiteral("."));
    fileTree_->setModel(fileModel_);
    fileTree_->setRootIndex(fileModel_->index(QStringLiteral(".")));
    fileTree_->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    fileTree_->hideColumn(1);
    fileTree_->hideColumn(2);
    fileTree_->hideColumn(3);
    connect(fileTree_, &QTreeView::doubleClicked, this, &CodeIdePage::onFileDoubleClicked);
    leftLayout->addWidget(fileTree_);
    splitter->addWidget(leftGroup);

    // Pane 2: Tabbed Code Editor
    auto* centerGroup = new QGroupBox(QStringLiteral("Editor Canvas"), splitter);
    auto* centerLayout = new QVBoxLayout(centerGroup);
    centerLayout->setContentsMargins(4, 8, 4, 4);

    editorTabs_ = new QTabWidget(centerGroup);
    editorTabs_->setTabsClosable(true);
    editorTabs_->setMovable(true);
    connect(editorTabs_, &QTabWidget::tabCloseRequested, this, &CodeIdePage::onTabCloseRequested);
    centerLayout->addWidget(editorTabs_);
    splitter->addWidget(centerGroup);

    // Pane 3: Pending Patch Cards
    auto* rightGroup = new QGroupBox(QStringLiteral("Pending Patches"), splitter);
    auto* rightLayout = new QVBoxLayout(rightGroup);
    rightLayout->setContentsMargins(4, 8, 4, 4);

    patchesScroll_ = new QScrollArea(rightGroup);
    patchesScroll_->setWidgetResizable(true);
    patchesScroll_->setFrameShape(QFrame::NoFrame);

    patchesContainer_ = new QWidget(patchesScroll_);
    patchesLayout_ = new QVBoxLayout(patchesContainer_);
    patchesLayout_->setContentsMargins(4, 4, 4, 4);
    patchesLayout_->setSpacing(8);
    patchesLayout_->addStretch(1);

    patchesScroll_->setWidget(patchesContainer_);
    rightLayout->addWidget(patchesScroll_);
    splitter->addWidget(rightGroup);

    splitter->setSizes({220, 560, 320});
    layout->addWidget(splitter, 1);
}

void CodeIdePage::setWorkspaceRoot(const QString& path) {
    workspaceRoot_ = path;
    fileModel_->setRootPath(path);
    fileTree_->setRootIndex(fileModel_->index(path));
}

void CodeIdePage::openFile(const QString& filePath) {
    for (int i = 0; i < editorTabs_->count(); ++i) {
        auto* ed = qobject_cast<CodeEditor*>(editorTabs_->widget(i));
        if (ed && ed->filePath() == filePath) {
            editorTabs_->setCurrentIndex(i);
            return;
        }
    }

    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        setStatus(QStringLiteral("Could not open file: %1").arg(filePath));
        return;
    }

    const QString content = QString::fromUtf8(file.readAll());
    file.close();

    auto* editor = new CodeEditor(editorTabs_);
    editor->setPlainText(content);
    editor->setFilePath(filePath);

    connect(editor, &CodeEditor::subcallRequested, this, [this, filePath](const QString& sel) {
        emit agentSubcallRequested(sel, filePath);
    });

    const QString tabTitle = QFileInfo(filePath).fileName();
    const int tabIdx = editorTabs_->addTab(editor, tabTitle);
    editorTabs_->setCurrentIndex(tabIdx);
    setStatus(QStringLiteral("Opened %1 (%2 lines)").arg(tabTitle).arg(editor->blockCount()));
}

void CodeIdePage::onFileDoubleClicked(const QModelIndex& index) {
    if (!fileModel_->isDir(index)) {
        openFile(fileModel_->filePath(index));
    }
}

void CodeIdePage::onTabCloseRequested(int index) {
    QWidget* widget = editorTabs_->widget(index);
    editorTabs_->removeTab(index);
    delete widget;
}

void CodeIdePage::addPendingPatch(const QString& filePath, const QString& diffText) {
    auto* patchCard = new PendingPatchWidget(filePath, diffText, patchesContainer_);

    connect(patchCard, &PendingPatchWidget::patchAccepted, this, [this, patchCard, filePath]() {
        emit patchAccepted(filePath);
        patchesLayout_->removeWidget(patchCard);
        delete patchCard;
        setStatus(QStringLiteral("Patch accepted for %1").arg(filePath));
    });

    connect(patchCard, &PendingPatchWidget::patchRejected, this, [this, patchCard, filePath]() {
        emit patchRejected(filePath);
        patchesLayout_->removeWidget(patchCard);
        delete patchCard;
        setStatus(QStringLiteral("Patch discarded for %1").arg(filePath));
    });

    // Insert before the trailing stretch
    patchesLayout_->insertWidget(patchesLayout_->count() - 1, patchCard);
    setStatus(QStringLiteral("New patch pending for %1").arg(filePath));
}

void CodeIdePage::clearPendingPatches() {
    QLayoutItem* item = nullptr;
    while ((item = patchesLayout_->takeAt(0)) != nullptr) {
        if (item->widget()) {
            delete item->widget();
        }
        delete item;
    }
    patchesLayout_->addStretch(1);
}

}  // namespace aquila::gui

