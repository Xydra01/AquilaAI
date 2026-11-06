// apps/aquila_gui/pages/base_page.hpp
#pragma once

#include <QLabel>
#include <QVBoxLayout>
#include <QWidget>

namespace aquila::gui {

class BasePage : public QWidget {
    Q_OBJECT
public:
    explicit BasePage(const QString& title, const QString& subtitle, const QString& icon, QWidget* parent = nullptr);

    void setStatus(const QString& text);
    QString title() const { return title_; }

protected:
    QVBoxLayout* contentLayout() { return contentLayout_; }

private:
    QString title_;
    QLabel* statusLabel_ = nullptr;
    QVBoxLayout* contentLayout_ = nullptr;
};

}  // namespace aquila::gui
