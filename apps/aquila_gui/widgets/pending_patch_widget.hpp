// apps/aquila_gui/widgets/pending_patch_widget.hpp
#pragma once

#include <QFrame>
#include <QLabel>
#include <QPushButton>
#include <QTextEdit>
#include <QVBoxLayout>

namespace aquila::gui {

class PendingPatchWidget : public QFrame {
    Q_OBJECT
public:
    explicit PendingPatchWidget(const QString& filePath, const QString& diffText, QWidget* parent = nullptr);

    QString filePath() const { return filePath_; }

signals:
    void patchAccepted(const QString& filePath);
    void patchRejected(const QString& filePath);

private:
    QString filePath_;
    QLabel* titleLabel_ = nullptr;
    QTextEdit* diffViewer_ = nullptr;
    QPushButton* acceptButton_ = nullptr;
    QPushButton* rejectButton_ = nullptr;
};

}  // namespace aquila::gui

