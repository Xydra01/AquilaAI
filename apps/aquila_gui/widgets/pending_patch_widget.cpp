// apps/aquila_gui/widgets/pending_patch_widget.cpp
#include "pending_patch_widget.hpp"

#include <QHBoxLayout>

namespace aquila::gui {

PendingPatchWidget::PendingPatchWidget(const QString& filePath, const QString& diffText, QWidget* parent)
    : QFrame(parent), filePath_(filePath) {
    setObjectName(QStringLiteral("pendingPatchCard"));
    setFrameShape(QFrame::StyledPanel);
    setStyleSheet(QStringLiteral(
        "#pendingPatchCard {"
        "    background-color: #252526;"
        "    border: 1px solid #3c3c3c;"
        "    border-radius: 8px;"
        "    margin: 4px;"
        "}"
    ));

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(12, 10, 12, 10);
    layout->setSpacing(8);

    // Header: File path
    auto* headerLayout = new QHBoxLayout();
    titleLabel_ = new QLabel(QStringLiteral("📄 %1").arg(filePath), this);
    titleLabel_->setStyleSheet(QStringLiteral("font-weight: bold; font-size: 13px; color: #ffffff;"));
    headerLayout->addWidget(titleLabel_);
    headerLayout->addStretch(1);

    auto* badge = new QLabel(QStringLiteral("Pending Review"), this);
    badge->setStyleSheet(QStringLiteral(
        "background-color: rgba(255, 185, 0, 0.2);"
        "color: #ffb900;"
        "border-radius: 4px;"
        "padding: 2px 6px;"
        "font-size: 11px;"
    ));
    headerLayout->addWidget(badge);
    layout->addLayout(headerLayout);

    // Diff Content Viewer
    diffViewer_ = new QTextEdit(this);
    diffViewer_->setReadOnly(true);
    diffViewer_->setFont(QFont(QStringLiteral("Consolas"), 10));
    diffViewer_->setMinimumHeight(120);
    diffViewer_->setMaximumHeight(260);

    // Colorize diff lines into HTML
    QString html = QStringLiteral("<pre style='margin:0; font-family:Consolas, monospace;'>");
    const QStringList lines = diffText.split(QLatin1Char('\n'));
    for (const auto& line : lines) {
        if (line.startsWith(QLatin1Char('+')) && !line.startsWith(QStringLiteral("+++"))) {
            html += QStringLiteral("<div style='background-color: rgba(46, 160, 67, 0.25); color: #7ee787;'>%1</div>")
                        .arg(line.toHtmlEscaped());
        } else if (line.startsWith(QLatin1Char('-')) && !line.startsWith(QStringLiteral("---"))) {
            html += QStringLiteral("<div style='background-color: rgba(248, 81, 73, 0.25); color: #ffa198;'>%1</div>")
                        .arg(line.toHtmlEscaped());
        } else if (line.startsWith(QLatin1Char('@'))) {
            html += QStringLiteral("<div style='color: #79c0ff; font-weight:bold;'>%1</div>").arg(line.toHtmlEscaped());
        } else {
            html += QStringLiteral("<div style='color: #8b949e;'>%1</div>").arg(line.toHtmlEscaped());
        }
    }
    html += QStringLiteral("</pre>");
    diffViewer_->setHtml(html);
    layout->addWidget(diffViewer_);

    // Button Row: Accept and Reject
    auto* btnLayout = new QHBoxLayout();
    btnLayout->addStretch(1);

    rejectButton_ = new QPushButton(QStringLiteral("✕ Discard"), this);
    rejectButton_->setStyleSheet(QStringLiteral(
        "QPushButton { background-color: #333333; color: #f85149; border: 1px solid #da3633; }"
        "QPushButton:hover { background-color: #b62324; color: #ffffff; }"
    ));
    connect(rejectButton_, &QPushButton::clicked, this, [this]() {
        emit patchRejected(filePath_);
    });
    btnLayout->addWidget(rejectButton_);

    acceptButton_ = new QPushButton(QStringLiteral("✓ Apply Patch"), this);
    acceptButton_->setProperty("accent", true);
    acceptButton_->setStyleSheet(QStringLiteral(
        "QPushButton { background-color: #238636; color: #ffffff; border: 1px solid #2ea043; font-weight:bold; }"
        "QPushButton:hover { background-color: #2ea043; }"
    ));
    connect(acceptButton_, &QPushButton::clicked, this, [this]() {
        emit patchAccepted(filePath_);
    });
    btnLayout->addWidget(acceptButton_);

    layout->addLayout(btnLayout);
}

}  // namespace aquila::gui

