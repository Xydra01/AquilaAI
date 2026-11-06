// apps/aquila_gui/pages/base_page.cpp
#include "base_page.hpp"

#include <QFrame>
#include <QHBoxLayout>

namespace aquila::gui {

BasePage::BasePage(const QString& title, const QString& subtitle, const QString& icon, QWidget* parent)
    : QWidget(parent), title_(title) {
    auto* mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(20, 16, 20, 12);
    mainLayout->setSpacing(12);

    // Header bar
    auto* header = new QHBoxLayout();
    header->setSpacing(12);

    auto* iconLabel = new QLabel(icon, this);
    iconLabel->setStyleSheet(QStringLiteral("font-size: 28px;"));
    header->addWidget(iconLabel);

    auto* titles = new QVBoxLayout();
    titles->setSpacing(2);

    auto* titleLabel = new QLabel(title, this);
    titleLabel->setStyleSheet(QStringLiteral("font-size: 18px; font-weight: bold; color: #ffffff;"));
    titles->addWidget(titleLabel);

    auto* subtitleLabel = new QLabel(subtitle, this);
    subtitleLabel->setStyleSheet(QStringLiteral("font-size: 12px; color: #888888;"));
    titles->addWidget(subtitleLabel);

    header->addLayout(titles);
    header->addStretch(1);

    mainLayout->addLayout(header);

    auto* sep = new QFrame(this);
    sep->setFrameShape(QFrame::HLine);
    sep->setStyleSheet(QStringLiteral("color: #333333;"));
    mainLayout->addWidget(sep);

    // Content container layout
    contentLayout_ = new QVBoxLayout();
    contentLayout_->setContentsMargins(0, 0, 0, 0);
    contentLayout_->setSpacing(8);
    mainLayout->addLayout(contentLayout_, 1);

    // Status bar at bottom
    statusLabel_ = new QLabel(QStringLiteral("Ready"), this);
    statusLabel_->setStyleSheet(QStringLiteral("font-size: 11px; color: #777777; padding-top: 4px;"));
    mainLayout->addWidget(statusLabel_);
}

void BasePage::setStatus(const QString& text) {
    if (statusLabel_) {
        statusLabel_->setText(text);
    }
}

}  // namespace aquila::gui

