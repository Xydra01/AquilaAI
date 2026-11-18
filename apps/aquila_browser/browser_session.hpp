#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>

#include <functional>

class QWebEnginePage;
class QWebEngineProfile;
class QWebEngineView;

namespace aquila::browser {

// Manages an off-the-record offscreen QtWebEngineView session and executes
// bounded asynchronous commands (navigate, search, click, type, scroll,
// extract_text, screenshot) returning structured JSON payloads.
class BrowserSession final : public QObject {
    Q_OBJECT
public:
    explicit BrowserSession(QObject* parent = nullptr);
    ~BrowserSession() override;

    void handle_request(const QJsonObject& req, std::function<void(const QJsonObject&)> reply);

private:
    using ReplyFn = std::function<void(const QJsonObject&)>;

    void cmd_ping(const QString& id, const ReplyFn& reply);
    void cmd_navigate(const QString& id, const QJsonObject& params, const ReplyFn& reply);
    void cmd_search(const QString& id, const QJsonObject& params, const ReplyFn& reply);
    void cmd_click(const QString& id, const QJsonObject& params, const ReplyFn& reply);
    void cmd_type(const QString& id, const QJsonObject& params, const ReplyFn& reply);
    void cmd_scroll(const QString& id, const QJsonObject& params, const ReplyFn& reply);
    void cmd_extract_text(const QString& id, const QJsonObject& params, const ReplyFn& reply);
    void cmd_screenshot(const QString& id, const QJsonObject& params, const ReplyFn& reply);

    void finish_with_snapshot(const QString& id,
                              const QString& screenshot_path,
                              int max_chars,
                              const ReplyFn& reply,
                              const QJsonObject& extra = {});

    QJsonObject capture_screenshot(const QString& screenshot_path);
    static bool is_allowed_http_url(const QString& url_str, QString& error_out);
    static QJsonObject detect_challenge(const QString& url, const QString& title, const QString& text, bool has_captcha_dom);

    QWebEngineProfile* profile_ = nullptr;
    QWebEnginePage* page_ = nullptr;
    QWebEngineView* view_ = nullptr;
};

} // namespace aquila::browser

