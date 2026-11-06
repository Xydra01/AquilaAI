// apps/aquila_gui/widgets/inline_diff_overlay.hpp
#pragma once

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QString>
#include <QTextEdit>
#include <vector>

namespace aquila::gui {

class InlinePatchPill : public QFrame {
    Q_OBJECT
public:
    explicit InlinePatchPill(QWidget* parent = nullptr);

    void setDiffSummary(int additions, int deletions);

signals:
    void acceptRequested();
    void rejectRequested();

private:
    QLabel* statsLabel_ = nullptr;
    QPushButton* acceptBtn_ = nullptr;
    QPushButton* rejectBtn_ = nullptr;
};

class InlineDiffOverlay : public QObject {
    Q_OBJECT
public:
    explicit InlineDiffOverlay(QPlainTextEdit* editor, QObject* parent = nullptr);
    ~InlineDiffOverlay() override;

    bool hasPendingPatch() const { return active_; }

    void startPendingPatch(int selectionStart, int selectionLength,
                           const QString& originalText, const QString& replacementText);
    void acceptPatch();
    void rejectPatch();
    void clear();

    QString originalText() const { return originalText_; }
    QString replacementText() const { return replacementText_; }

signals:
    void patchAccepted(const QString& replacement);
    void patchRejected();

private slots:
    void repositionPill();

private:
    void applyDiffSelections();

    QPlainTextEdit* editor_ = nullptr;
    InlinePatchPill* pill_ = nullptr;

    bool active_ = false;
    int selectionStart_ = 0;
    int selectionLength_ = 0;
    QString originalText_;
    QString replacementText_;
};

}  // namespace aquila::gui
