#include "browser_session.hpp"

#include <QApplication>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaObject>
#include <QProcess>
#include <QTcpServer>
#include <QTcpSocket>
#include <QThread>
#include <QTimer>
#include <QWebEnginePage>
#include <QWebEngineProfile>
#include <QWebEngineView>

#include <iostream>
#include <string>
#include <vector>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <fcntl.h>
#include <io.h>
#include <windows.h>
#endif

namespace {

int run_smoke(aquila::browser::BrowserSession& session, const QString& out_dir) {
    QTcpServer server;
    if (!server.listen(QHostAddress::LocalHost, 0)) {
        std::cerr << "smoke server listen failed\n";
        return 2;
    }
    QObject::connect(&server, &QTcpServer::newConnection, &server, [&server]() {
        while (QTcpSocket* sock = server.nextPendingConnection()) {
            QObject::connect(sock, &QTcpSocket::readyRead, sock, [sock]() {
                sock->readAll();
                const QByteArray html =
                    "<!doctype html><html><head><title>Aquila Browser Smoke</title>"
                    "<style>body{background:#121826;color:#f8fafc;font-family:sans-serif;padding:32px}"
                    "button{background:#2563eb;color:#fff;padding:12px 20px;border:none;border-radius:6px}</style>"
                    "</head><body><h1>Interactive Test</h1>"
                    "<p id=\"status\">initial state</p>"
                    "<button id=\"btn\" onclick=\"document.getElementById('status').textContent='clicked_ok'\">Trigger</button>"
                    "</body></html>";
                const QByteArray resp =
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    "Content-Length: " + QByteArray::number(html.size()) + "\r\n"
                    "Connection: close\r\n\r\n" + html;
                sock->write(resp);
                sock->disconnectFromHost();
            });
            QObject::connect(sock, &QTcpSocket::disconnected, sock, &QObject::deleteLater);
        }
    });

    const QString url = QStringLiteral("http://127.0.0.1:%1/").arg(server.serverPort());
    const QString shot_path = QDir(out_dir).filePath(QStringLiteral("browser_smoke.png"));

    int exit_code = 1;
    QTimer::singleShot(30000, qApp, []() {
        std::cerr << "[BROWSER-SMOKE-TIMEOUT]\n";
        QCoreApplication::exit(3);
    });

    QJsonObject nav_req;
    nav_req.insert("id", "smoke_nav");
    nav_req.insert("action", "navigate");
    nav_req.insert("params", QJsonObject{{"url", url}});
    session.handle_request(nav_req, [&](const QJsonObject& nav_res) {
        if (!nav_res.value("ok").toBool()) {
            std::cerr << "navigate failed: " << nav_res.value("error").toString().toStdString() << "\n";
            QCoreApplication::exit(4);
            return;
        }
        QJsonObject click_req;
        click_req.insert("id", "smoke_click");
        click_req.insert("action", "click");
        click_req.insert("params", QJsonObject{
            {"selector", "#btn"},
            {"screenshot_path", shot_path}
        });
        session.handle_request(click_req, [&](const QJsonObject& click_res) {
            const bool ok = click_res.value("ok").toBool();
            const QString text = click_res.value("text").toString();
            const int colors = click_res.value("screenshot_unique_colors").toInt(0);
            if (!ok || !text.contains("clicked_ok") || colors < 2) {
                std::cerr << "click/screenshot validation failed: ok=" << ok
                          << " colors=" << colors
                          << " text=" << text.toStdString() << "\n";
                QCoreApplication::exit(5);
                return;
            }
            std::cout << "[BROWSER-SMOKE-OK] clicked_ok screenshot=" << shot_path.toStdString()
                      << " colors=" << colors << "\n" << std::flush;
            exit_code = 0;
            QCoreApplication::exit(0);
        });
    });

    QCoreApplication::exec();
    return exit_code;
}

int run_interactive_login(const QString& target_url) {
    const QString profilePath = QDir::homePath() + QStringLiteral("/.aquila/browser_profile");
    QDir().mkpath(profilePath);

    auto* profile = new QWebEngineProfile(QStringLiteral("aquila_user"), qApp);
    profile->setPersistentStoragePath(profilePath);
    profile->setCachePath(profilePath + QStringLiteral("/cache"));
    profile->setPersistentCookiesPolicy(QWebEngineProfile::AllowPersistentCookies);
    profile->setHttpCacheType(QWebEngineProfile::DiskHttpCache);
    profile->setHttpUserAgent(QStringLiteral("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"));

    auto* page = new QWebEnginePage(profile, nullptr);
    auto* view = new QWebEngineView();
    view->setPage(page);
    view->setWindowTitle(QStringLiteral("Aquila Browser - Interactive Login & 2FA Session"));
    view->resize(1280, 850);
    view->setUrl(QUrl(target_url));
    view->setAttribute(Qt::WA_DeleteOnClose);
    view->show();

    std::cout << "[Aquila Browser] Interactive login session opened for: " << target_url.toStdString() << "\n"
              << "Log in and complete any 2-factor / phone prompts in the browser window.\n"
              << "When done, simply close the browser window to save cookies and return to Aquila.\n" << std::flush;

    QObject::connect(view, &QObject::destroyed, qApp, &QCoreApplication::quit);

    return QApplication::exec();
}

class StdinReader final : public QObject {
    Q_OBJECT
public:
    explicit StdinReader(aquila::browser::BrowserSession* session) : session_(session) {}

public slots:
    void read_loop() {
        std::string line;
        while (std::getline(std::cin, line)) {
            if (!line.empty() && line.back() == '\r') {
                line.pop_back();
            }
            if (line.empty()) {
                continue;
            }
            const QByteArray raw(line.data(), static_cast<int>(line.size()));
            QJsonParseError perr{};
            const QJsonDocument doc = QJsonDocument::fromJson(raw, &perr);
            if (perr.error != QJsonParseError::NoError || !doc.isObject()) {
                const QJsonObject err{
                    {"id", QString{}},
                    {"ok", false},
                    {"error_code", "invalid_json"},
                    {"error", perr.errorString()}
                };
                const QByteArray out = QJsonDocument(err).toJson(QJsonDocument::Compact);
                std::cout << out.constData() << '\n' << std::flush;
                continue;
            }
            const QJsonObject req = doc.object();
            if (req.value("action").toString() == QStringLiteral("quit")) {
                const QJsonObject ack{{"id", req.value("id").toString()}, {"ok", true}};
                std::cout << QJsonDocument(ack).toJson(QJsonDocument::Compact).constData() << '\n' << std::flush;
                QMetaObject::invokeMethod(qApp, "quit", Qt::QueuedConnection);
                break;
            }
            QMetaObject::invokeMethod(session_, [s = session_, req]() {
                s->handle_request(req, [](const QJsonObject& res) {
                    const QByteArray out = QJsonDocument(res).toJson(QJsonDocument::Compact);
                    std::cout << out.constData() << '\n' << std::flush;
                });
            }, Qt::QueuedConnection);
        }
        QMetaObject::invokeMethod(qApp, "quit", Qt::QueuedConnection);
    }

private:
    aquila::browser::BrowserSession* session_;
};

} // namespace

#include "main.moc"

int main(int argc, char* argv[]) {
    bool is_interactive_login = false;
    QString login_url = QStringLiteral("https://www.google.com");
    for (int i = 1; i < argc; ++i) {
        const std::string_view arg(argv[i]);
        if (arg == "--help" || arg == "-h") {
            std::cout << "Aquila Headless Browser Helper (JSON-RPC stdio worker)\n"
                      << "Usage:\n"
                      << "  aquila_browser [--smoke [output_dir]]\n"
                      << "  aquila_browser --login <url>\n"
                      << "  aquila_browser --help\n"
                      << "When invoked without flags, reads single-line JSON-RPC requests on stdin.\n";
            return 0;
        }
        if (arg == "--login") {
            is_interactive_login = true;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                login_url = QString::fromUtf8(argv[++i]);
            }
        }
    }

    // Route Qt logs to stderr so stdout remains strictly reserved for 1-line JSON-RPC replies.
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext&, const QString& msg) {
        std::cerr << "[qt-browser] " << msg.toStdString() << '\n';
    });

    // Software compositing keeps VRAM free for llama.cpp CUDA while ensuring QWebEngineView::grab
    // reads a painted offscreen framebuffer without popping up a visible desktop window.
    if (!is_interactive_login && qEnvironmentVariableIsEmpty("QTWEBENGINE_CHROMIUM_FLAGS")) {
        qputenv("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-gpu-compositing --mute-audio --no-sandbox");
    }

#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
#endif

    // Ensure Qt can locate plugins in the application directory or relative Qt plugins
    if (argc > 0 && argv[0]) {
        const QString app_dir = QDir::toNativeSeparators(QFileInfo(QString::fromLocal8Bit(argv[0])).dir().absolutePath());
        QCoreApplication::addLibraryPath(app_dir);
        QCoreApplication::addLibraryPath(app_dir + QStringLiteral("/platforms"));
        QCoreApplication::addLibraryPath(app_dir + QStringLiteral("/plugins"));
    }

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("aquila_browser"));

    if (is_interactive_login) {
        return run_interactive_login(login_url);
    }

    aquila::browser::BrowserSession session;

    for (int i = 1; i < argc; ++i) {
        if (std::string_view(argv[i]) == "--smoke") {
            const QString out_dir = (i + 1 < argc && argv[i + 1][0] != '-')
                ? QString::fromUtf8(argv[i + 1])
                : QDir::tempPath();
            return run_smoke(session, out_dir);
        }
    }

    QThread reader_thread;
    StdinReader reader(&session);
    reader.moveToThread(&reader_thread);
    QObject::connect(&reader_thread, &QThread::started, &reader, &StdinReader::read_loop);
    reader_thread.start();

    // Auto-start local SearXNG in background when aquila_browser runs standalone and
    // http://127.0.0.1:8888 is not already listening (Option A: tied to process lifetime).
    if (qEnvironmentVariable("AQUILA_DISABLE_SEARXNG_AUTOSTART") != QStringLiteral("1")) {
        QTcpSocket probe;
        probe.connectToHost(QStringLiteral("127.0.0.1"), 8888);
        const bool already_listening = probe.waitForConnected(150);
        if (already_listening) {
            probe.disconnectFromHost();
        } else {
            QString script_path = qEnvironmentVariable("AQUILA_SEARXNG_SCRIPT");
#ifdef AQUILA_DEFAULT_SEARXNG_SCRIPT
            if (script_path.isEmpty() && QFileInfo::exists(QStringLiteral(AQUILA_DEFAULT_SEARXNG_SCRIPT))) {
                script_path = QStringLiteral(AQUILA_DEFAULT_SEARXNG_SCRIPT);
            }
#endif
            if (script_path.isEmpty()) {
                QDir dir(QCoreApplication::applicationDirPath());
                for (int depth = 0; depth < 6; ++depth) {
                    const QString cand = dir.filePath(QStringLiteral("scripts/run_searxng.py"));
                    if (QFileInfo::exists(cand)) {
                        script_path = cand;
                        break;
                    }
                    if (!dir.cdUp()) break;
                }
            }
            if (!script_path.isEmpty()) {
#ifdef _WIN32
                HANDLE searxng_job = CreateJobObjectW(nullptr, nullptr);
                HANDLE searxng_proc_h = nullptr;
                if (searxng_job) {
                    JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli{};
                    jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                    SetInformationJobObject(searxng_job, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));

                    SECURITY_ATTRIBUTES sa{};
                    sa.nLength = sizeof(sa);
                    sa.bInheritHandle = TRUE;
                    HANDLE nul_in = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                                &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
                    HANDLE nul_out = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                                 &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);

                    const std::wstring wscript = script_path.toStdWString();
                    for (const wchar_t* py : {L"python", L"py -3"}) {
                        std::wstring cmd = std::wstring(py) + L" \"" + wscript + L"\" --host 127.0.0.1 --port 8888";
                        std::vector<wchar_t> cmd_mut(cmd.begin(), cmd.end());
                        cmd_mut.push_back(L'\0');

                        STARTUPINFOW si{};
                        si.cb = sizeof(si);
                        si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
                        si.wShowWindow = SW_HIDE;
                        si.hStdInput = (nul_in != INVALID_HANDLE_VALUE) ? nul_in : GetStdHandle(STD_INPUT_HANDLE);
                        si.hStdOutput = (nul_out != INVALID_HANDLE_VALUE) ? nul_out : GetStdHandle(STD_OUTPUT_HANDLE);
                        si.hStdError = (nul_out != INVALID_HANDLE_VALUE) ? nul_out : GetStdHandle(STD_ERROR_HANDLE);

                        PROCESS_INFORMATION pi{};
                        // CREATE_SUSPENDED ensures the Python launcher shim is in the Job Object
                        // BEFORE it spawns the real pythoncore child process (zero orphan race).
                        if (CreateProcessW(nullptr, cmd_mut.data(), nullptr, nullptr, TRUE,
                                           CREATE_NO_WINDOW | CREATE_SUSPENDED, nullptr, nullptr, &si, &pi)) {
                            AssignProcessToJobObject(searxng_job, pi.hProcess);
                            ResumeThread(pi.hThread);
                            CloseHandle(pi.hThread);
                            searxng_proc_h = pi.hProcess;
                            break;
                        }
                    }
                    if (nul_in != INVALID_HANDLE_VALUE) CloseHandle(nul_in);
                    if (nul_out != INVALID_HANDLE_VALUE) CloseHandle(nul_out);
                }
                QObject::connect(&app, &QCoreApplication::aboutToQuit, [searxng_job, searxng_proc_h]() {
                    if (searxng_job) {
                        TerminateJobObject(searxng_job, 0);
                        CloseHandle(searxng_job);
                    }
                    if (searxng_proc_h) {
                        WaitForSingleObject(searxng_proc_h, 1000);
                        CloseHandle(searxng_proc_h);
                    }
                });
#else
                auto* searxng_proc = new QProcess(&app);
                searxng_proc->setProcessChannelMode(QProcess::ForwardedErrorChannel);
                searxng_proc->setStandardOutputFile(QProcess::nullDevice());
                searxng_proc->start(QStringLiteral("python3"),
                                    {script_path, QStringLiteral("--host"), QStringLiteral("127.0.0.1"),
                                     QStringLiteral("--port"), QStringLiteral("8888")});
                QObject::connect(&app, &QCoreApplication::aboutToQuit, [searxng_proc]() {
                    if (searxng_proc && searxng_proc->state() != QProcess::NotRunning) {
                        searxng_proc->terminate();
                        if (!searxng_proc->waitForFinished(800)) {
                            searxng_proc->kill();
                            searxng_proc->waitForFinished(500);
                        }
                    }
                });
#endif
            }
        }
    }

    const int rc = app.exec();
    reader_thread.wait(1000);
    return rc;
}

