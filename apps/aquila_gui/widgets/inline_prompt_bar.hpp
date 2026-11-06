// apps/aquila_gui/widgets/inline_prompt_bar.hpp
#pragma once

#include <QFrame>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>

namespace aquila::gui {

class InlinePromptBar : public QFrame {
    Q_OBJECT
public:
    explicit InlinePromptBar(QWidget* parent = nullptr);

    void setPromptText(const QString& text);
    QString promptText() const;
    void focusInput();
    void clearInput();

signals:
    void submitRequested(const QString& prompt);
    void cancelRequested();

protected:
    void keyPressEvent(QKeyEvent* event) override;

private slots:
    void onSubmitClicked();
    void onCancelClicked();

private:
    QLabel* iconLabel_ = nullptr;
    QLineEdit* promptInput_ = nullptr;
    QPushButton* submitButton_ = nullptr;
    QPushButton* cancelButton_ = nullptr;
};

}  // namespace aquila::gui
