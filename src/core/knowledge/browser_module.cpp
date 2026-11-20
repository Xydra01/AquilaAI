#include "aquila/knowledge/browser_module.hpp"

#include "aquila/exec/process.hpp"
#include "aquila/knowledge/credential_store.hpp"
#include "aquila/knowledge/html_cleaner.hpp"
#include "aquila/knowledge/searxng_manager.hpp"
#include "aquila/knowledge/web_fetcher.hpp"

#include <fmt/format.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <sstream>
#include <thread>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <cerrno>
#include <poll.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace aquila::knowledge {

namespace fs = std::filesystem;

namespace {

std::filesystem::path current_executable_dir() {
#ifdef _WIN32
    std::wstring buf(1024, L'\0');
    const DWORD len = GetModuleFileNameW(nullptr, buf.data(), static_cast<DWORD>(buf.size()));
    if (len > 0 && len < buf.size()) {
        buf.resize(len);
        return fs::path(buf).parent_path();
    }
    return {};
#else
    std::error_code ec;
    const auto p = fs::read_symlink("/proc/self/exe", ec);
    return ec ? fs::path{} : p.parent_path();
#endif
}

} // namespace

std::string BrowserModule::resolve_browser_binary(const std::string& configured) {
    auto is_file = [](const fs::path& p) {
        std::error_code ec;
        return !p.empty() && fs::exists(p, ec) && fs::is_regular_file(p, ec);
    };

    if (!configured.empty()) {
        fs::path p(configured);
        if (is_file(p)) {
            return p.string();
        }
    }
    if (const char* env_bin = std::getenv("AQUILA_BROWSER_BIN")) {
        fs::path p(env_bin);
        if (is_file(p)) {
            return p.string();
        }
    }
#ifdef AQUILA_DEFAULT_BROWSER_BIN
    {
        fs::path p(AQUILA_DEFAULT_BROWSER_BIN);
        if (is_file(p)) {
            return p.string();
        }
    }
#endif
    const fs::path exe_dir = current_executable_dir();
#ifdef _WIN32
    constexpr const char* kExeName = "aquila_browser.exe";
#else
    constexpr const char* kExeName = "aquila_browser";
#endif
    if (!exe_dir.empty()) {
        for (const fs::path& candidate : {
                 exe_dir / kExeName,
                 exe_dir / ".." / "aquila_browser" / kExeName,
                 exe_dir / ".." / ".." / "apps" / "aquila_browser" / kExeName,
             }) {
            std::error_code ec;
            fs::path norm = fs::weakly_canonical(candidate, ec);
            if (is_file(ec ? candidate : norm)) {
                return (ec ? candidate : norm).string();
            }
        }
    }
    const fs::path found = exec::find_program("aquila_browser");
    if (!found.empty() && is_file(found)) {
        return found.string();
    }
    return {};
}

namespace {

ActionResult make_ok(std::string output, std::vector<std::string> images = {}) {
    ActionResult r;
    r.success = true;
    r.llm_facing_output = std::move(output);
    r.images = std::move(images);
    return r;
}

ActionResult make_err(std::string code, std::string output) {
    ActionResult r;
    r.success = false;
    r.error_code = std::move(code);
    r.llm_facing_output = std::move(output);
    return r;
}

std::string truncate_str(const std::string& s, std::size_t max_chars) {
    return json_io::truncate_utf8(s, max_chars);
}

#ifdef _WIN32
std::wstring widen_utf8(std::string_view s) {
    if (s.empty()) return {};
    const int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
    std::wstring w(static_cast<std::size_t>(n), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), w.data(), n);
    return w;
}

std::wstring build_env_with_qt_bin() {
    std::string qt_bin;
#ifdef AQUILA_DEFAULT_QT_BIN_DIR
    qt_bin = AQUILA_DEFAULT_QT_BIN_DIR;
#endif
    if (qt_bin.empty()) {
        if (const char* root = std::getenv("QT_ROOT_DIR")) {
            qt_bin = (fs::path(root) / "bin").string();
        }
    }
    std::string qt_plugins;
    if (!qt_bin.empty()) {
        std::error_code ec;
        const fs::path p = fs::path(qt_bin).parent_path() / "plugins";
        if (fs::exists(p, ec) && fs::is_directory(p, ec)) {
            qt_plugins = p.string();
        }
    }

    std::wstring extra_prefix = qt_bin.empty() ? L"" : widen_utf8(qt_bin) + L";";
    std::vector<std::wstring> entries;
    bool has_qt_plugin = false;
    bool has_qpa_plugin = false;

    if (wchar_t* block = GetEnvironmentStringsW()) {
        for (const wchar_t* p = block; *p != L'\0'; p += wcslen(p) + 1) {
            std::wstring entry(p);
            if (_wcsnicmp(entry.c_str(), L"PATH=", 5) == 0 && !extra_prefix.empty()) {
                entry = L"PATH=" + extra_prefix + entry.substr(5);
            } else if (_wcsnicmp(entry.c_str(), L"QT_PLUGIN_PATH=", 15) == 0) {
                has_qt_plugin = true;
            } else if (_wcsnicmp(entry.c_str(), L"QT_QPA_PLATFORM_PLUGIN_PATH=", 28) == 0) {
                has_qpa_plugin = true;
            }
            entries.push_back(std::move(entry));
        }
        FreeEnvironmentStringsW(block);
    }

    if (!has_qt_plugin && !qt_plugins.empty()) {
        entries.push_back(L"QT_PLUGIN_PATH=" + widen_utf8(qt_plugins));
    }
    if (!has_qpa_plugin && !qt_plugins.empty()) {
        entries.push_back(L"QT_QPA_PLATFORM_PLUGIN_PATH=" + widen_utf8((fs::path(qt_plugins) / "platforms").string()));
    }

    std::wstring out;
    for (const auto& e : entries) {
        out += e;
        out.push_back(L'\0');
    }
    out.push_back(L'\0');
    return out;
}
#endif

} // namespace

struct BrowserModule::WorkerProcess {
#ifdef _WIN32
    HANDLE job = nullptr;
    HANDLE process = nullptr;
    HANDLE stdin_write = nullptr;
    HANDLE stdout_read = nullptr;
    std::string read_buf;
#else
    pid_t pid = -1;
    int stdin_write = -1;
    int stdout_read = -1;
    std::string read_buf;
#endif

    ~WorkerProcess() { stop(); }

    bool is_alive() const {
#ifdef _WIN32
        if (!process) return false;
        return WaitForSingleObject(process, 0) == WAIT_TIMEOUT;
#else
        if (pid <= 0) return false;
        int status = 0;
        return waitpid(pid, &status, WNOHANG) == 0;
#endif
    }

    bool start(const std::string& bin_path, std::string& error_out) {
        stop();
#ifdef _WIN32
        SECURITY_ATTRIBUTES sa{};
        sa.nLength = sizeof(sa);
        sa.bInheritHandle = TRUE;

        HANDLE in_rd = nullptr, in_wr = nullptr, out_rd = nullptr, out_wr = nullptr;
        if (!CreatePipe(&in_rd, &in_wr, &sa, 0) || !CreatePipe(&out_rd, &out_wr, &sa, 0)) {
            error_out = "CreatePipe failed starting aquila_browser";
            if (in_rd) CloseHandle(in_rd);
            if (in_wr) CloseHandle(in_wr);
            if (out_rd) CloseHandle(out_rd);
            if (out_wr) CloseHandle(out_wr);
            return false;
        }
        SetHandleInformation(in_wr, HANDLE_FLAG_INHERIT, 0);
        SetHandleInformation(out_rd, HANDLE_FLAG_INHERIT, 0);

        job = CreateJobObjectW(nullptr, nullptr);
        if (job) {
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli{};
            jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            SetInformationJobObject(job, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));
        }

        STARTUPINFOW si{};
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        si.hStdInput = in_rd;
        si.hStdOutput = out_wr;
        si.hStdError = GetStdHandle(STD_ERROR_HANDLE);

        PROCESS_INFORMATION pi{};
        std::wstring cmd = L"\"" + widen_utf8(bin_path) + L"\"";
        std::wstring env_block = build_env_with_qt_bin();

        const BOOL ok = CreateProcessW(
            nullptr, cmd.data(), nullptr, nullptr, TRUE,
            CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW | CREATE_SUSPENDED,
            env_block.data(), nullptr, &si, &pi);

        CloseHandle(in_rd);
        CloseHandle(out_wr);

        if (!ok) {
            CloseHandle(in_wr);
            CloseHandle(out_rd);
            if (job) {
                CloseHandle(job);
                job = nullptr;
            }
            error_out = fmt::format("Failed to spawn '{}' (Win32 error {})", bin_path, GetLastError());
            return false;
        }

        if (job) {
            AssignProcessToJobObject(job, pi.hProcess);
        }
        ResumeThread(pi.hThread);
        CloseHandle(pi.hThread);

        process = pi.hProcess;
        stdin_write = in_wr;
        stdout_read = out_rd;
        read_buf.clear();
        return true;
#else
        int in_pipe[2]{-1, -1};
        int out_pipe[2]{-1, -1};
        if (pipe(in_pipe) != 0 || pipe(out_pipe) != 0) {
            error_out = "pipe() failed starting aquila_browser";
            return false;
        }
        const pid_t child = fork();
        if (child < 0) {
            close(in_pipe[0]);
            close(in_pipe[1]);
            close(out_pipe[0]);
            close(out_pipe[1]);
            error_out = "fork() failed starting aquila_browser";
            return false;
        }
        if (child == 0) {
            dup2(in_pipe[0], STDIN_FILENO);
            dup2(out_pipe[1], STDOUT_FILENO);
            close(in_pipe[0]);
            close(in_pipe[1]);
            close(out_pipe[0]);
            close(out_pipe[1]);
            execl(bin_path.c_str(), bin_path.c_str(), nullptr);
            _exit(127);
        }
        close(in_pipe[0]);
        close(out_pipe[1]);
        pid = child;
        stdin_write = in_pipe[1];
        stdout_read = out_pipe[0];
        read_buf.clear();
        return true;
#endif
    }

    bool write_line(const std::string& line) {
        const std::string wire = line + "\n";
#ifdef _WIN32
        if (!stdin_write) return false;
        std::size_t off = 0;
        while (off < wire.size()) {
            DWORD written = 0;
            if (!WriteFile(stdin_write, wire.data() + off, static_cast<DWORD>(wire.size() - off), &written, nullptr) || written == 0) {
                return false;
            }
            off += written;
        }
        return true;
#else
        if (stdin_write < 0) return false;
        std::size_t off = 0;
        while (off < wire.size()) {
            const ssize_t n = write(stdin_write, wire.data() + off, wire.size() - off);
            if (n <= 0) return false;
            off += static_cast<std::size_t>(n);
        }
        return true;
#endif
    }

    bool read_line_timeout(std::string& line_out, int timeout_ms) {
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
        for (;;) {
            const std::size_t nl = read_buf.find('\n');
            if (nl != std::string::npos) {
                line_out = read_buf.substr(0, nl);
                read_buf.erase(0, nl + 1);
                if (!line_out.empty() && line_out.back() == '\r') {
                    line_out.pop_back();
                }
                return true;
            }
            if (std::chrono::steady_clock::now() >= deadline) {
                return false;
            }
#ifdef _WIN32
            DWORD avail = 0;
            if (!PeekNamedPipe(stdout_read, nullptr, 0, nullptr, &avail, nullptr)) {
                return false;
            }
            if (avail > 0) {
                char buf[4096];
                DWORD got = 0;
                const DWORD to_read = std::min<DWORD>(avail, sizeof(buf));
                if (!ReadFile(stdout_read, buf, to_read, &got, nullptr) || got == 0) {
                    return false;
                }
                read_buf.append(buf, got);
            } else {
                if (!is_alive()) {
                    DWORD avail_after = 0;
                    if (!PeekNamedPipe(stdout_read, nullptr, 0, nullptr, &avail_after, nullptr) || avail_after == 0) {
                        return false;
                    }
                    continue;
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
#else
            const auto rem = std::chrono::duration_cast<std::chrono::milliseconds>(
                deadline - std::chrono::steady_clock::now());
            pollfd pfd{stdout_read, POLLIN, 0};
            const int prc = poll(&pfd, 1, static_cast<int>(std::max<long long>(1, rem.count())));
            if (prc < 0) {
                if (errno == EINTR) continue;
                return false;
            }
            if (prc == 0) {
                return false;
            }
            char buf[4096];
            const ssize_t got = read(stdout_read, buf, sizeof(buf));
            if (got <= 0) return false;
            read_buf.append(buf, static_cast<std::size_t>(got));
#endif
        }
    }

    void stop() {
#ifdef _WIN32
        if (stdin_write) {
            const std::string quit_cmd = R"({"id":"quit","action":"quit"})" "\n";
            DWORD written = 0;
            WriteFile(stdin_write, quit_cmd.data(), static_cast<DWORD>(quit_cmd.size()), &written, nullptr);
            CloseHandle(stdin_write);
            stdin_write = nullptr;
        }
        if (process) {
            if (WaitForSingleObject(process, 300) == WAIT_TIMEOUT) {
                if (job) {
                    TerminateJobObject(job, 1);
                } else {
                    TerminateProcess(process, 1);
                }
            }
            CloseHandle(process);
            process = nullptr;
        }
        if (job) {
            CloseHandle(job);
            job = nullptr;
        }
        if (stdout_read) {
            CloseHandle(stdout_read);
            stdout_read = nullptr;
        }
#else
        if (stdin_write >= 0) {
            const std::string quit_cmd = R"({"id":"quit","action":"quit"})" "\n";
            (void)write(stdin_write, quit_cmd.data(), quit_cmd.size());
            close(stdin_write);
            stdin_write = -1;
        }
        if (stdout_read >= 0) {
            close(stdout_read);
            stdout_read = -1;
        }
        if (pid > 0) {
            int status = 0;
            if (waitpid(pid, &status, WNOHANG) == 0) {
                kill(pid, SIGTERM);
                std::this_thread::sleep_for(std::chrono::milliseconds(150));
                if (waitpid(pid, &status, WNOHANG) == 0) {
                    kill(pid, SIGKILL);
                    waitpid(pid, &status, 0);
                }
            }
            pid = -1;
        }
#endif
        read_buf.clear();
    }
};

std::string canonicalize_url_key(std::string_view raw) {
    std::string s(raw);
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) s.erase(s.begin());
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) s.pop_back();
    if (const auto hash = s.find('#'); hash != std::string::npos) {
        s.resize(hash);
    }
    // Lowercase scheme and host only; preserve path case (important for Wikipedia/GitHub URLs).
    if (const auto scheme_end = s.find("://"); scheme_end != std::string::npos) {
        const auto host_start = scheme_end + 3;
        const auto path_start = s.find('/', host_start);
        const auto host_end = (path_start == std::string::npos) ? s.size() : path_start;
        for (std::size_t i = 0; i < host_end; ++i) {
            s[i] = static_cast<char>(std::tolower(static_cast<unsigned char>(s[i])));
        }
        if (path_start != std::string::npos && s.size() > path_start + 1 && s.back() == '/') {
            s.pop_back();
        }
    }
    return s;
}

std::string make_session_stamp() {
    static std::atomic<std::uint64_t> instance_seq{0};
    const std::uint64_t inst = ++instance_seq;
    const auto now = std::chrono::system_clock::now();
    const std::time_t tt = std::chrono::system_clock::to_time_t(now);
    std::tm tm_buf{};
#ifdef _WIN32
    localtime_s(&tm_buf, &tt);
#else
    localtime_r(&tt, &tm_buf);
#endif
    return fmt::format("{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}_{:03d}",
                       tm_buf.tm_year + 1900, tm_buf.tm_mon + 1, tm_buf.tm_mday,
                       tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec,
                       inst % 1000);
}

BrowserModule::BrowserModule(const ModuleContext& ctx)
    : ctx_(ctx), session_stamp_(make_session_stamp()) {}

BrowserModule::~BrowserModule() = default;

std::vector<ActionSchema> BrowserModule::get_actions() const {
    return {
        {
            "browser_search",
            "Search the web via local multi-source SearXNG (GitHub, arXiv, Hacker News, Wikipedia, general web) and return titles, URLs, and snippets",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"query", Json::object({{"type", "string"}, {"description", "Search query keywords"}})},
                    {"screenshot", Json::object({{"type", "boolean"}, {"description", "Capture viewport PNG screenshot when using rendered browser search (default false)"}})},
                })},
                {"required", Json::array({"query"})},
            }),
        },
        {
            "browser_navigate",
            "Navigate the headless browser to an HTTP/HTTPS URL, wait for JS render, extract page text/links/controls, and automatically capture a visual screenshot",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"url", Json::object({{"type", "string"}, {"description", "Target http:// or https:// URL"}})},
                })},
                {"required", Json::array({"url"})},
            }),
        },
        {
            "browser_click",
            "Click a visible element on the current webpage by CSS selector or viewport (x, y) coordinates and capture an updated visual screenshot",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"selector", Json::object({{"type", "string"}, {"description", "CSS selector of target element"}})},
                    {"x", Json::object({{"type", "integer"}, {"description", "Viewport X coordinate (if omitting selector)"}})},
                    {"y", Json::object({{"type", "integer"}, {"description", "Viewport Y coordinate (if omitting selector)"}})},
                })},
            }),
        },
        {
            "browser_type",
            "Type text into an input or textarea matched by CSS selector and optionally submit",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"selector", Json::object({{"type", "string"}, {"description", "CSS selector of input/textarea"}})},
                    {"text", Json::object({{"type", "string"}, {"description", "Text to fill into the field"}})},
                    {"submit", Json::object({{"type", "boolean"}, {"description", "Submit form or press Enter (default false)"}})},
                })},
                {"required", Json::array({"selector", "text"})},
            }),
        },
        {
            "browser_scroll",
            "Scroll the current webpage viewport vertically and return the updated view and screenshot",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"direction", Json::object({{"type", "string"}, {"description", "Scroll direction: down, up, top, or bottom"}})},
                    {"pixels", Json::object({{"type", "integer"}, {"description", "Pixel delta for up/down scrolling (default 700, max 1600px per step so sections are not skipped)"}})},
                })},
            }),
        },
        {
            "browser_find",
            "Search for keywords or phrases inside the currently loaded webpage (in-page Ctrl+F), automatically center the viewport on the match, and extract surrounding context",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"query", Json::object({{"type", "string"}, {"description", "Keyword or phrase to locate on page"}})},
                    {"match_index", Json::object({{"type", "integer"}, {"description", "Occurrence index to jump to (1-based, default 1)"}})},
                    {"screenshot", Json::object({{"type", "boolean"}, {"description", "Capture viewport screenshot with match highlighted (default true)"}})},
                })},
                {"required", Json::array({"query"})},
            }),
        },
        {
            "browser_login",
            "Automatically detect and populate login credentials for the current page or specified domain using the secure local CredentialStore, submit the form, and check for 2FA / authentication status",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"domain", Json::object({{"type", "string"}, {"description", "Optional domain name to retrieve credentials for (defaults to current page domain)"}})},
                    {"submit", Json::object({{"type", "boolean"}, {"description", "Automatically click submit button after filling (default true)"}})},
                    {"screenshot", Json::object({{"type", "boolean"}, {"description", "Capture viewport screenshot after login attempt (default true)"}})},
                })},
            }),
        },
        {
            "browser_extract_text",
            "Extract visible rendered text, links, and interactive controls from the current webpage",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"selector", Json::object({{"type", "string"}, {"description", "Optional CSS selector subtree to extract"}})},
                    {"max_chars", Json::object({{"type", "integer"}, {"description", "Maximum text characters to return"}})},
                    {"screenshot", Json::object({{"type", "boolean"}, {"description", "Attach visual PNG (default false)"}})},
                })},
            }),
        },
        {
            "browser_screenshot",
            "Capture and attach a PNG viewport screenshot of the current webpage",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({})},
            }),
        },
    };
}

std::vector<SearchResult> BrowserModule::search_browser_direct(const std::string& query, int max_results) {
    return search_structured(query, max_results, /*force_browser=*/true);
}

std::vector<SearchResult> BrowserModule::search_structured(const std::string& query, int max_results, bool force_browser) {
    if (query.empty() || max_results <= 0) {
        return {};
    }

    // Default to local SearXNG multi-source search unless an explicit search_base_url_
    // override is configured (e.g. localhost Chromium search test fixtures) or force_browser is requested.
    if (!force_browser && search_base_url_.empty()) {
        SearchOptions opts;
        opts.provider = SearchProvider::searxng;
        opts.searxng_endpoint = searxng_endpoint_;
        opts.max_results = max_results;
        WebSearchEngine engine(opts);
        auto sx = engine.search_searxng(query, max_results);
        const bool only_wiki = !sx.empty() && std::all_of(sx.begin(), sx.end(), [](const auto& item) {
            return item.engine == "wikipedia" || item.url.find("wikipedia.org") != std::string::npos;
        });
        if (!sx.empty() && !only_wiki) {
            for (const auto& item : sx) {
                record_discovered_url(item.url, item.snippet);
            }
            return sx;
        }
    }

    Json params = Json::object({
        {"query", query},
        {"timeout_ms", default_timeout_ms_},
    });
    if (!search_base_url_.empty()) {
        params["search_base_url"] = search_base_url_;
    }
    std::string code, msg;
    const Json res = call_worker("search", params, code, msg);
    if (!code.empty() || !res.contains("results") || !res["results"].is_array()) {
        return {};
    }
    current_url_ = res.value("url", current_url_);
    current_title_ = res.value("title", current_title_);

    std::vector<SearchResult> out;
    int idx = 0;
    for (const auto& item : res["results"]) {
        if (idx >= max_results) break;
        SearchResult sr;
        sr.title = item.value("title", std::string{});
        sr.url = item.value("url", std::string{});
        sr.snippet = item.value("snippet", std::string{});
        sr.engine = "aquila_browser";
        sr.score = std::max(0.1, 1.0 - (0.05 * idx));
        record_discovered_url(sr.url, sr.snippet);
        out.push_back(std::move(sr));
        ++idx;
    }
    return out;
}

void BrowserModule::configure(const Json& initial_state) {
    if (initial_state.contains("browser_bin") && initial_state["browser_bin"].is_string()) {
        browser_bin_ = initial_state["browser_bin"].get<std::string>();
    }
    if (initial_state.contains("search_base_url") && initial_state["search_base_url"].is_string()) {
        search_base_url_ = initial_state["search_base_url"].get<std::string>();
    }
    if (initial_state.contains("searxng_endpoint") && initial_state["searxng_endpoint"].is_string()) {
        const std::string ep = initial_state["searxng_endpoint"].get<std::string>();
        if (!ep.empty()) {
            searxng_endpoint_ = ep;
        }
    }
    if (initial_state.contains("timeout_ms") && initial_state["timeout_ms"].is_number_integer()) {
        default_timeout_ms_ = std::clamp(initial_state["timeout_ms"].get<int>(), 1000, 60000);
    }
    if (initial_state.contains("max_output_chars") && initial_state["max_output_chars"].is_number_integer()) {
        max_output_chars_ = static_cast<std::size_t>(
            std::clamp(initial_state["max_output_chars"].get<int>(), 512, 32000));
    }
    if (initial_state.contains("max_screenshots") && initial_state["max_screenshots"].is_number_integer()) {
        max_screenshots_ = static_cast<std::size_t>(
            std::clamp(initial_state["max_screenshots"].get<int>(), 0, 10000));
    }
}

void BrowserModule::record_discovered_url(const std::string& url, const std::string& snippet) {
    if (url.empty() || (!url.starts_with("http://") && !url.starts_with("https://"))) {
        return;
    }
    const std::string key = canonicalize_url_key(url);
    if (!snippet.empty()) {
        discovered_snippets_[key] = snippet;
    }
    for (const auto& existing : discovered_urls_) {
        if (canonicalize_url_key(existing) == key) {
            return;
        }
    }
    if (discovered_urls_.size() >= 60) {
        const std::string oldest_key = canonicalize_url_key(discovered_urls_.front());
        discovered_snippets_.erase(oldest_key);
        discovered_urls_.erase(discovered_urls_.begin());
    }
    discovered_urls_.push_back(url);
}

void BrowserModule::record_visited_url(const std::string& url,
                                       const std::string& title,
                                       int scroll_pct,
                                       bool increment_visit) {
    if (url.empty() || (!url.starts_with("http://") && !url.starts_with("https://"))) {
        return;
    }
    record_discovered_url(url);
    const std::string key = canonicalize_url_key(url);
    auto it = visited_urls_.find(key);
    if (it == visited_urls_.end()) {
        if (visited_order_.size() >= 30) {
            const std::string oldest = visited_order_.front();
            visited_order_.erase(visited_order_.begin());
            visited_urls_.erase(oldest);
        }
        visited_order_.push_back(key);
        visited_urls_[key] = VisitedUrlInfo{
            .url = url,
            .title = title,
            .visit_count = 1,
            .max_scroll_pct = std::clamp(scroll_pct, 0, 100),
        };
    } else {
        if (!title.empty()) it->second.title = title;
        if (increment_visit) it->second.visit_count += 1;
        it->second.max_scroll_pct = std::max(it->second.max_scroll_pct, std::clamp(scroll_pct, 0, 100));
    }
}

void BrowserModule::record_failed_url(const std::string& url,
                                      const std::string& error_code,
                                      const std::string& reason) {
    if (url.empty() || (!url.starts_with("http://") && !url.starts_with("https://"))) {
        return;
    }
    const std::string key = canonicalize_url_key(url);
    if (failed_urls_.find(key) == failed_urls_.end()) {
        if (failed_order_.size() >= 25) {
            const std::string oldest = failed_order_.front();
            failed_order_.erase(failed_order_.begin());
            failed_urls_.erase(oldest);
        }
        failed_order_.push_back(key);
    }
    failed_urls_[key] = FailedUrlInfo{
        .url = url,
        .error_code = error_code,
        .reason = reason,
    };
}

std::vector<std::string> BrowserModule::unvisited_suggestions(std::size_t max_count) const {
    std::vector<std::string> out;
    for (const auto& u : discovered_urls_) {
        const std::string key = canonicalize_url_key(u);
        if (visited_urls_.find(key) == visited_urls_.end() &&
            failed_urls_.find(key) == failed_urls_.end()) {
            out.push_back(u);
            if (out.size() >= max_count) break;
        }
    }
    return out;
}

Json BrowserModule::export_state_snapshot() const {
    Json visited_arr = Json::array();
    for (const auto& key : visited_order_) {
        if (auto it = visited_urls_.find(key); it != visited_urls_.end()) {
            visited_arr.push_back(Json::object({
                {"url", it->second.url},
                {"title", it->second.title},
                {"visit_count", it->second.visit_count},
                {"max_scroll_pct", it->second.max_scroll_pct},
            }));
        }
    }
    Json failed_arr = Json::array();
    for (const auto& key : failed_order_) {
        if (auto it = failed_urls_.find(key); it != failed_urls_.end()) {
            failed_arr.push_back(Json::object({
                {"url", it->second.url},
                {"error_code", it->second.error_code},
                {"reason", it->second.reason},
            }));
        }
    }
    return Json::object({
        {"current_url", current_url_},
        {"current_title", current_title_},
        {"shot_seq", shot_seq_},
        {"search_base_url", search_base_url_},
        {"searxng_endpoint", searxng_endpoint_},
        {"visited_urls", std::move(visited_arr)},
        {"failed_urls", std::move(failed_arr)},
        {"discovered_urls", discovered_urls_},
        {"searched_queries", searched_queries_},
    });
}

void BrowserModule::restore_state_snapshot(const Json& snapshot) {
    current_url_ = snapshot.value("current_url", std::string{});
    current_title_ = snapshot.value("current_title", std::string{});
    shot_seq_ = snapshot.value("shot_seq", std::uint64_t{0});
    if (snapshot.contains("search_base_url") && snapshot["search_base_url"].is_string()) {
        search_base_url_ = snapshot["search_base_url"].get<std::string>();
    }
    if (snapshot.contains("searxng_endpoint") && snapshot["searxng_endpoint"].is_string()) {
        const std::string ep = snapshot["searxng_endpoint"].get<std::string>();
        if (!ep.empty()) searxng_endpoint_ = ep;
    }
    visited_order_.clear();
    visited_urls_.clear();
    if (snapshot.contains("visited_urls") && snapshot["visited_urls"].is_array()) {
        for (const auto& item : snapshot["visited_urls"]) {
            if (!item.is_object()) continue;
            const std::string u = item.value("url", std::string{});
            if (u.empty()) continue;
            const std::string key = canonicalize_url_key(u);
            visited_order_.push_back(key);
            visited_urls_[key] = VisitedUrlInfo{
                .url = u,
                .title = item.value("title", std::string{}),
                .visit_count = item.value("visit_count", 1),
                .max_scroll_pct = item.value("max_scroll_pct", 0),
            };
        }
    }
    failed_order_.clear();
    failed_urls_.clear();
    if (snapshot.contains("failed_urls") && snapshot["failed_urls"].is_array()) {
        for (const auto& item : snapshot["failed_urls"]) {
            if (!item.is_object()) continue;
            const std::string u = item.value("url", std::string{});
            if (u.empty()) continue;
            record_failed_url(u, item.value("error_code", std::string{}), item.value("reason", std::string{}));
        }
    }
    discovered_urls_.clear();
    if (snapshot.contains("discovered_urls") && snapshot["discovered_urls"].is_array()) {
        for (const auto& item : snapshot["discovered_urls"]) {
            if (item.is_string()) record_discovered_url(item.get<std::string>());
        }
    }
    searched_queries_.clear();
    if (snapshot.contains("searched_queries") && snapshot["searched_queries"].is_array()) {
        for (const auto& item : snapshot["searched_queries"]) {
            if (item.is_string()) searched_queries_.push_back(item.get<std::string>());
        }
    }
}

Json BrowserModule::export_context_summary() const {
    if (current_url_.empty() && visited_order_.empty() && failed_order_.empty() && searched_queries_.empty()) {
        return Json::object();
    }
    Json out = Json::object();
    if (!current_url_.empty()) {
        out["current_url"] = current_url_;
        out["current_title"] = current_title_;
    }
    out["screenshots"] = shot_seq_;
    if (!visited_order_.empty()) {
        Json arr = Json::array();
        const std::size_t start = visited_order_.size() > 10 ? visited_order_.size() - 10 : 0;
        for (std::size_t i = start; i < visited_order_.size(); ++i) {
            if (auto it = visited_urls_.find(visited_order_[i]); it != visited_urls_.end()) {
                arr.push_back(fmt::format("{} ({}% viewed, visits={})",
                                          it->second.url, it->second.max_scroll_pct, it->second.visit_count));
            }
        }
        out["visited_urls_do_not_reload"] = std::move(arr);
    }
    if (!failed_order_.empty()) {
        Json arr = Json::array();
        const std::size_t start = failed_order_.size() > 8 ? failed_order_.size() - 8 : 0;
        for (std::size_t i = start; i < failed_order_.size(); ++i) {
            if (auto it = failed_urls_.find(failed_order_[i]); it != failed_urls_.end()) {
                arr.push_back(fmt::format("{} ({})", it->second.url, it->second.error_code));
            }
        }
        out["failed_urls_do_not_retry"] = std::move(arr);
    }
    if (!searched_queries_.empty()) {
        Json arr = Json::array();
        const std::size_t start = searched_queries_.size() > 5 ? searched_queries_.size() - 5 : 0;
        for (std::size_t i = start; i < searched_queries_.size(); ++i) {
            arr.push_back(searched_queries_[i]);
        }
        out["recent_queries"] = std::move(arr);
    }
    return out;
}

std::string BrowserModule::next_screenshot_path() {
    ++shot_seq_;
    const fs::path base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
    const fs::path dir = base / ".aquila" / "browser_screenshots";
    std::error_code ec;
    fs::create_directories(dir, ec);
    return (dir / fmt::format("shot_{}_{:03d}.png", session_stamp_, shot_seq_)).string();
}

void BrowserModule::prune_old_screenshots(const std::string& just_saved_path) const {
    if (max_screenshots_ == 0 || just_saved_path.empty()) {
        return;
    }
    std::error_code ec;
    const fs::path dir = fs::path(just_saved_path).parent_path();
    if (dir.empty() || !fs::exists(dir, ec) || !fs::is_directory(dir, ec)) {
        return;
    }
    struct Entry {
        fs::path path;
        fs::file_time_type mtime;
        std::string name;
    };
    std::vector<Entry> shots;
    for (const auto& de : fs::directory_iterator(dir, ec)) {
        if (ec) break;
        if (!de.is_regular_file(ec)) continue;
        const std::string fname = de.path().filename().string();
        if (fname.rfind("shot_", 0) == 0 && de.path().extension() == ".png") {
            const auto mt = de.last_write_time(ec);
            shots.push_back(Entry{de.path(), ec ? fs::file_time_type{} : mt, fname});
        }
    }
    if (shots.size() <= max_screenshots_) {
        return;
    }
    // Sort newest first; break ties lexicographically by timestamped filename descending.
    std::sort(shots.begin(), shots.end(), [](const Entry& a, const Entry& b) {
        if (a.mtime != b.mtime) return a.mtime > b.mtime;
        return a.name > b.name;
    });
    for (std::size_t i = max_screenshots_; i < shots.size(); ++i) {
        std::error_code rm_ec;
        fs::remove(shots[i].path, rm_ec);
    }
}

bool BrowserModule::ensure_worker(std::string& error_out) {
    if (worker_ && worker_->is_alive()) {
        return true;
    }
    const std::string bin = resolve_browser_binary(browser_bin_);
    if (bin.empty()) {
        error_out = "aquila_browser binary not found (build with Qt6 WebEngineWidgets or set AQUILA_BROWSER_BIN)";
        return false;
    }
    auto proc = std::make_unique<WorkerProcess>();
    if (!proc->start(bin, error_out)) {
        return false;
    }
    if (!proc->write_line(R"({"id":"init_ping","action":"ping"})")) {
        error_out = "Failed writing initial ping to aquila_browser";
        return false;
    }
    std::string pong_line;
    if (!proc->read_line_timeout(pong_line, 15000)) {
        error_out = "aquila_browser failed to respond to initial ping within 15s";
        return false;
    }
    const Json pong = Json::parse(pong_line, nullptr, false);
    if (pong.is_discarded() || !pong.value("ok", false)) {
        error_out = "aquila_browser initial handshake rejected: " + pong_line;
        return false;
    }
    worker_ = std::move(proc);
    return true;
}

Json BrowserModule::call_worker(const std::string& action,
                                const Json& params,
                                std::string& error_code,
                                std::string& error_msg) {
    std::string start_err;
    if (!ensure_worker(start_err)) {
        error_code = "browser_unavailable";
        error_msg = start_err;
        return Json{};
    }

    const int rpc_timeout = params.contains("timeout_ms") && params["timeout_ms"].is_number_integer()
        ? std::clamp(params["timeout_ms"].get<int>(), 1000, 60000)
        : default_timeout_ms_;

    const std::string req_id = fmt::format("req_{}", ++req_seq_);
    const Json req = Json::object({
        {"id", req_id},
        {"action", action},
        {"params", params},
    });

    if (!worker_->write_line(req.dump())) {
        worker_.reset();
        error_code = "browser_io_error";
        error_msg = "Failed writing command to aquila_browser pipe";
        return Json{};
    }

    std::string reply_line;
    if (!worker_->read_line_timeout(reply_line, rpc_timeout + 4000)) {
        worker_.reset(); // Kills stalled Chromium process tree
        error_code = "browser_timeout";
        error_msg = fmt::format("aquila_browser timed out executing '{}'", action);
        return Json{};
    }

    const Json reply = Json::parse(reply_line, nullptr, false);
    if (reply.is_discarded() || !reply.is_object()) {
        error_code = "browser_protocol_error";
        error_msg = "Malformed JSON response from aquila_browser";
        return Json{};
    }
    if (!reply.value("ok", false)) {
        error_code = reply.value("error_code", std::string("browser_error"));
        error_msg = reply.value("error", std::string("Browser action failed"));
        return reply;
    }
    return reply;
}

ActionResult BrowserModule::format_snapshot_result(const std::string& header,
                                                   const Json& res,
                                                   bool attach_screenshot,
                                                   bool count_as_new_visit,
                                                   const std::string& leading_note) {
    const std::string prev_url = current_url_;
    current_url_ = res.value("url", current_url_);
    current_title_ = res.value("title", current_title_);

    if (res.value("challenge_detected", false)) {
        const std::string reason = res.value("challenge_reason", std::string("challenge page"));
        record_failed_url(current_url_, "challenge_detected", reason);
        return make_err(
            "challenge_detected",
            fmt::format("{} at {}: {} (Aquila does not bypass anti-bot/CAPTCHA challenges)",
                        header, current_url_, reason));
    }

    if (res.value("soft_404", false)) {
        const std::string reason = res.value("soft_404_reason", std::string("Page not found (404)"));
        record_failed_url(current_url_, "page_not_found", reason);
        std::string msg = fmt::format("{} at {}: {}. Do NOT retry this URL.", header, current_url_, reason);
        const auto alts = unvisited_suggestions(3);
        if (!alts.empty()) {
            msg += " Try one of these unvisited URLs instead: ";
            for (std::size_t i = 0; i < alts.size(); ++i) {
                if (i > 0) msg += ", ";
                msg += alts[i];
            }
        }
        return make_err("page_not_found", msg);
    }

    int scroll_pct = 0;
    bool has_scroll = false;
    int sy = 0, sh = 800, vh = 800, remaining_px = 0;
    if (res.contains("scroll_y") && res.contains("scroll_height")) {
        has_scroll = true;
        sy = res.value("scroll_y", 0);
        sh = std::max(1, res.value("scroll_height", 800));
        vh = std::max(1, res.value("viewport_height", 800));
        const int bottom_y = std::min(sh, sy + vh);
        scroll_pct = std::clamp(static_cast<int>((100.0 * bottom_y) / sh), 0, 100);
        remaining_px = std::max(0, sh - bottom_y);
    }

    const bool url_changed = !current_url_.empty() &&
                             canonicalize_url_key(current_url_) != canonicalize_url_key(prev_url);
    record_visited_url(current_url_, current_title_, scroll_pct, count_as_new_visit || url_changed);

    std::ostringstream out;
    if (!leading_note.empty()) {
        out << leading_note << "\n";
    }
    out << "[" << header << "]\n"
        << "URL: " << current_url_ << "\n"
        << "Title: " << current_title_ << "\n";

    if (has_scroll) {
        out << "Scroll: y=" << sy
            << " / total_height=" << sh
            << " (viewport=" << vh << ", " << scroll_pct << "% viewed";
        if (remaining_px > 200) {
            out << " — " << remaining_px << "px remaining below fold; call browser_scroll(direction=\"down\") to read further";
        } else {
            out << " — reached bottom of page";
        }
        out << ")\n";
    }

    if (res.contains("clamped_from") && res.contains("clamped_to")) {
        out << "Scroll Note: step clamped from " << res.value("clamped_from", 0)
            << "px to " << res.value("clamped_to", 1600)
            << "px so intermediate sections are not skipped.\n";
    }
    if (res.value("partial_load", false)) {
        out << "Load Note: stopped slow background scripts/ads after "
            << res.value("partial_load_timeout_ms", default_timeout_ms_)
            << "ms; rendered article text captured.\n";
    }

    const std::string text = json_io::sanitize_utf8(res.value("text", std::string{}));
    const std::size_t full_len = res.value("full_text_length", std::size_t{0});
    if (full_len > text.size() + 100) {
        out << "Text Coverage: showing " << text.size() << " of " << full_len
            << " total page chars (scroll down or use browser_extract_text with a CSS selector to inspect deeper sections)\n";
    }
    if (!text.empty()) {
        out << "\n--- Visible Page Text ---\n"
            << truncate_str(text, max_output_chars_) << "\n";
    }

    if (res.contains("links") && res["links"].is_array() && !res["links"].empty()) {
        out << "\n--- Links (clickable via browser_click selector or browser_navigate url) ---\n";
        std::size_t shown = 0;
        for (const auto& link : res["links"]) {
            if (shown >= 25) break;
            out << fmt::format("[{}] {} -> {} (selector: `{}`){}\n",
                               link.value("index", static_cast<int>(shown + 1)),
                               link.value("text", std::string{}),
                               link.value("url", std::string{}),
                               link.value("selector", std::string{}),
                               link.value("in_viewport", false) ? " [in-view]" : "");
            ++shown;
        }
    }

    if (res.contains("interactive") && res["interactive"].is_array() && !res["interactive"].empty()) {
        out << "\n--- Interactive Controls (use browser_click / browser_type with selector) ---\n";
        std::size_t shown = 0;
        bool has_search_box = false;
        for (const auto& el : res["interactive"]) {
            if (shown >= 18) break;
            std::string flags;
            if (el.value("is_search", false)) {
                flags += " [search-input]";
                has_search_box = true;
            }
            if (el.value("in_viewport", false)) flags += " [in-view]";
            const std::string role = el.value("role", std::string{});
            if (!role.empty()) flags += " [role=" + role + "]";
            const std::string exp = el.value("expanded", std::string{});
            if (exp == "false") flags += " [collapsed]";
            else if (exp == "true") flags += " [expanded]";
            out << fmt::format("- <{}> text=\"{}\" selector=`{}` center=({},{}){}\n",
                               el.value("tag", std::string{}),
                               el.value("text", std::string{}),
                               el.value("selector", std::string{}),
                               el.value("x", 0),
                               el.value("y", 0),
                               flags);
            ++shown;
        }
        if (has_search_box) {
            out << "(Tip: You can search within this site via browser_type(selector, text, submit=true) on a [search-input] control.)\n";
        }
    }

    ActionResult result = make_ok(truncate_str(out.str(), max_output_chars_ + 2000));
    if (attach_screenshot && res.value("screenshot_ok", false)) {
        const std::string shot = res.value("screenshot_path", std::string{});
        std::error_code ec;
        if (!shot.empty() && fs::exists(shot, ec)) {
            prune_old_screenshots(shot);
            result.images.push_back(shot);
        }
    }
    return result;
}

ActionResult BrowserModule::run(const std::string& action_name, const Json& args) {
    if (action_name == "browser_search") {
        const std::string query = args.at("query").get<std::string>();
        const bool want_shot = args.value("screenshot", false);

        if (!query.empty()) {
            if (std::find(searched_queries_.begin(), searched_queries_.end(), query) == searched_queries_.end()) {
                if (searched_queries_.size() >= 15) {
                    searched_queries_.erase(searched_queries_.begin());
                }
                searched_queries_.push_back(query);
            }
        }

        const bool force_browser = args.value("force_browser", false) || args.value("engine", "") == "browser";
        // Default to local multi-source SearXNG unless an explicit search_base_url_
        // override is configured (e.g. localhost Chromium search test fixtures) or force_browser is requested.
        if (!force_browser && search_base_url_.empty()) {
            SearchOptions opts;
            opts.provider = SearchProvider::searxng;
            opts.searxng_endpoint = searxng_endpoint_;
            opts.max_results = 10;
            WebSearchEngine search_engine(opts);
            std::vector<SearchResult> sx = search_engine.search_searxng(query, 10);
            const bool only_wiki = !sx.empty() && std::all_of(sx.begin(), sx.end(), [](const auto& item) {
                return item.engine == "wikipedia" || item.url.find("wikipedia.org") != std::string::npos;
            });
            if (!sx.empty() && !only_wiki) {
                std::ostringstream out;
                out << "[Browser Search Results for \"" << query << "\" via Local SearXNG]\n"
                    << "(Use browser_navigate on promising URLs below to read full pages, scroll deeper sections, and inspect primary sources.)\n";
                int idx = 0;
                for (const auto& item : sx) {
                    ++idx;
                    record_discovered_url(item.url, item.snippet);
                    out << fmt::format("[{}] [{}] {}\n    URL: {}\n",
                                       idx,
                                       item.engine.empty() ? std::string("web") : item.engine,
                                       item.title,
                                       item.url);
                    if (!item.snippet.empty()) {
                        out << "    Snippet: " << item.snippet << "\n";
                    }
                }
                return make_ok(truncate_str(out.str(), max_output_chars_));
            }
        }

        Json params = Json::object({
            {"query", query},
            {"timeout_ms", default_timeout_ms_},
        });
        if (!search_base_url_.empty()) {
            params["search_base_url"] = search_base_url_;
        }
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }
        std::string code, msg;
        const Json res = call_worker("search", params, code, msg);
        const bool worker_failed = !code.empty();
        const auto worker_results = worker_failed ? Json::array() : res.value("results", Json::array());

        // Fallback to Wikipedia API if both SearXNG and rendered search fail/challenge.
        if (search_base_url_.empty() && (worker_failed || worker_results.empty())) {
            SearchOptions opts;
            opts.provider = SearchProvider::wikipedia;
            WebSearchEngine fallback_engine(opts);
            std::vector<SearchResult> fb = fallback_engine.search_wikipedia(query, 8);
            if (!fb.empty()) {
                std::ostringstream out;
                out << "[Browser Search Results for \"" << query << "\" (Fallback via wikipedia)]\n";
                if (worker_failed) {
                    out << "(Note: Rendered search returned '" << code
                        << "'; switched cleanly to wikipedia API. Use browser_navigate on any URL below to read, scroll, and interact with the page.)\n";
                }
                int idx = 0;
                for (const auto& item : fb) {
                    ++idx;
                    record_discovered_url(item.url, item.snippet);
                    out << fmt::format("[{}] {}\n    URL: {}\n", idx, item.title, item.url);
                    if (!item.snippet.empty()) {
                        out << "    Snippet: " << item.snippet << "\n";
                    }
                }
                return make_ok(truncate_str(out.str(), max_output_chars_));
            }
        }

        if (worker_failed) {
            return make_err(code, msg);
        }
        current_url_ = res.value("url", current_url_);
        current_title_ = res.value("title", current_title_);

        std::ostringstream out;
        out << "[Browser Search Results for \"" << query << "\"]\n";
        const auto& results = worker_results;
        if (results.empty()) {
            out << "No search results extracted from " << current_url_ << ".\n";
            const std::string body = res.value("text", std::string{});
            if (!body.empty()) {
                out << "Page excerpt:\n" << truncate_str(body, 800) << "\n";
            }
        } else {
            int idx = 0;
            for (const auto& item : results) {
                ++idx;
                const std::string rurl = item.value("url", std::string{});
                const std::string sn = item.value("snippet", std::string{});
                record_discovered_url(rurl, sn);
                out << fmt::format("[{}] {}\n    URL: {}\n",
                                   idx,
                                   item.value("title", std::string{}),
                                   rurl);
                if (!sn.empty()) {
                    out << "    Snippet: " << sn << "\n";
                }
            }
        }
        ActionResult ar = make_ok(truncate_str(out.str(), max_output_chars_));
        if (want_shot && res.value("screenshot_ok", false)) {
            const std::string shot = res.value("screenshot_path", std::string{});
            std::error_code ec;
            if (!shot.empty() && fs::exists(shot, ec)) {
                prune_old_screenshots(shot);
                ar.images.push_back(shot);
            }
        }
        return ar;
    }

    if (action_name == "browser_navigate") {
        const std::string url = args.at("url").get<std::string>();
        const std::string key = canonicalize_url_key(url);
        const bool is_same_page_anchor =
            url.find('#') != std::string::npos &&
            !current_url_.empty() &&
            canonicalize_url_key(current_url_) == key;

        // Fast-fail if this exact URL already failed (e.g. 404 or CAPTCHA) in this session.
        if (!is_same_page_anchor) {
            if (auto fit = failed_urls_.find(key); fit != failed_urls_.end()) {
                std::string msg = fmt::format(
                    "Skipping already-failed URL '{}' (previous error: {} - {}). Choose a different URL or search query.",
                    url, fit->second.error_code, fit->second.reason);
                const auto alts = unvisited_suggestions(3);
                if (!alts.empty()) {
                    msg += " Unvisited URLs from your search results: ";
                    for (std::size_t i = 0; i < alts.size(); ++i) {
                        if (i > 0) msg += ", ";
                        msg += alts[i];
                    }
                }
                return make_err("already_failed_url", msg);
            }
        }

        // Guard against duplicate reloads of already-visited URLs after context condensation
        // (allow same-page #anchor jumps cleanly).
        std::string revisit_note;
        if (!is_same_page_anchor) {
            if (auto vit = visited_urls_.find(key); vit != visited_urls_.end()) {
                if (vit->second.visit_count >= 2 && vit->second.max_scroll_pct >= 80) {
                    std::string msg = fmt::format(
                        "Already navigated to '{}' {} times ({}% viewed). Move on to a new source URL or synthesize your findings.",
                        url, vit->second.visit_count, vit->second.max_scroll_pct);
                    const auto alts = unvisited_suggestions(3);
                    if (!alts.empty()) {
                        msg += " Unvisited URLs: ";
                        for (std::size_t i = 0; i < alts.size(); ++i) {
                            if (i > 0) msg += ", ";
                            msg += alts[i];
                        }
                    }
                    return make_err("duplicate_navigation", msg);
                }
                revisit_note = fmt::format(
                    "[REVISIT NOTICE: You already visited '{}' ({}% viewed, visit #{}). Prefer browser_scroll to read deeper sections or navigate to a new unvisited source URL.]",
                    url, vit->second.max_scroll_pct, vit->second.visit_count + 1);
            }
        }

        const bool want_shot = args.value("screenshot", true);
        int nav_timeout_ms = args.value("timeout_ms", default_timeout_ms_);
        if (!SearxngManager::is_loopback_endpoint(url)) {
            nav_timeout_ms = std::clamp(nav_timeout_ms, 15000, 60000);
        } else {
            nav_timeout_ms = std::clamp(nav_timeout_ms, 1000, 60000);
        }
        Json params = Json::object({
            {"url", url},
            {"timeout_ms", nav_timeout_ms},
            {"max_chars", static_cast<int>(max_output_chars_)},
        });
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }
        std::string code, msg;
        const Json res = call_worker("navigate", params, code, msg);
        if (!code.empty()) {
            // Attempt direct HTTP fallback extraction before declaring failure.
            // Many academic or paywalled sites (e.g. Royal Society, Oxford Academic, Karger, ResearchGate)
            // block automated WebEngine browsers with WAF challenges or timeouts, but may yield readable
            // HTML/abstract text or metadata over standard HTTP requests.
            try {
                FetchOptions fetch_opts;
                fetch_opts.timeout_seconds = 8;
                fetch_opts.max_redirects = 5;
                WebFetcher fetcher(fetch_opts);
                auto fetch_res = fetcher.fetch(url);
                if (fetch_res.status_code >= 200 && fetch_res.status_code < 400 && !fetch_res.body.empty()) {
                    HtmlCleaner cleaner;
                    auto clean = cleaner.clean(fetch_res.body);
                    if (clean.text.size() >= 150) {
                        const std::string page_title = clean.title.empty() ? url : clean.title;
                        record_visited_url(url, page_title, 100, true);
                        current_url_ = url;
                        current_title_ = page_title;
                        timeout_counts_.erase(key);
                        std::ostringstream out;
                        out << "[Browser Navigation Fallback (HTTP Extract)]\n"
                            << "URL: " << url << "\n"
                            << "Title: " << page_title << "\n"
                            << "Note: Live browser view encountered '" << code
                            << "'; successfully extracted page text via direct HTTP fallback.\n"
                            << "\n--- Visible Page Text ---\n"
                            << truncate_str(clean.text, max_output_chars_) << "\n";
                        return make_ok(out.str());
                    }
                }
            } catch (...) {
                // Fallback attempt failed; proceed with standard error handling
            }

            if (code == "challenge_detected" || code == "navigation_failed" || code == "page_not_found") {
                record_failed_url(url, code, msg);
            } else if (code == "navigation_timeout") {
                const int count = ++timeout_counts_[key];
                if (count >= 2) {
                    record_failed_url(url, code, msg);
                }
            }
            auto snip_it = discovered_snippets_.find(key);
            if (snip_it != discovered_snippets_.end() && !snip_it->second.empty()) {
                msg += fmt::format(" (Snippet from search index: \"{}\")", snip_it->second);
            }
            return make_err(code, msg);
        }
        timeout_counts_.erase(key);
        return format_snapshot_result("Browser Navigated", res, want_shot, !is_same_page_anchor, revisit_note);
    }

    if (action_name == "browser_click") {
        const std::string selector = args.value("selector", std::string{});
        const bool has_xy = args.contains("x") && args.contains("y");
        if (selector.empty() && !has_xy) {
            return make_err("invalid_args",
                                    "browser_click requires either 'selector' or integer 'x' and 'y'");
        }
        const bool want_shot = args.value("screenshot", true);
        Json params = Json::object({
            {"max_chars", static_cast<int>(max_output_chars_)},
        });
        if (!selector.empty()) params["selector"] = selector;
        if (has_xy) {
            params["x"] = args.at("x").get<int>();
            params["y"] = args.at("y").get<int>();
        }
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }
        std::string code, msg;
        const Json res = call_worker("click", params, code, msg);
        if (!code.empty()) {
            return make_err(code, msg);
        }
        return format_snapshot_result("Browser Clicked", res, want_shot, false);
    }

    if (action_name == "browser_type") {
        const std::string selector = args.at("selector").get<std::string>();
        const std::string text = args.at("text").get<std::string>();
        const bool submit = args.value("submit", false);
        const bool want_shot = args.value("screenshot", true);
        Json params = Json::object({
            {"selector", selector},
            {"text", text},
            {"submit", submit},
            {"max_chars", static_cast<int>(max_output_chars_)},
        });
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }
        std::string code, msg;
        const Json res = call_worker("type", params, code, msg);
        if (!code.empty()) {
            return make_err(code, msg);
        }
        return format_snapshot_result("Browser Typed", res, want_shot, false);
    }

    if (action_name == "browser_scroll") {
        const std::string direction = args.value("direction", std::string("down"));
        const int raw_pixels = args.value("pixels", 700);
        const int pixels = std::clamp(raw_pixels, -1600, 1600);
        const bool want_shot = args.value("screenshot", true);
        Json params = Json::object({
            {"direction", direction},
            {"pixels", pixels},
            {"max_chars", static_cast<int>(max_output_chars_)},
        });
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }
        std::string code, msg;
        const Json res = call_worker("scroll", params, code, msg);
        if (!code.empty()) {
            return make_err(code, msg);
        }
        std::string clamp_note;
        if ((direction == "down" || direction == "up") && std::abs(raw_pixels) > 1600 &&
            !res.contains("clamped_from")) {
            clamp_note = fmt::format(
                "[Scroll Note: step clamped from {}px to 1600px so intermediate sections are not skipped.]",
                std::abs(raw_pixels));
        }
        return format_snapshot_result("Browser Scrolled", res, want_shot, false, clamp_note);
    }

    if (action_name == "browser_find") {
        const std::string query = args.at("query").get<std::string>();
        const int match_index = args.value("match_index", 1);
        const bool want_shot = args.value("screenshot", true);
        Json params = Json::object({
            {"query", query},
            {"match_index", match_index},
            {"max_chars", static_cast<int>(max_output_chars_)},
        });
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }
        std::string code, msg;
        const Json res = call_worker("find", params, code, msg);
        if (!code.empty()) {
            return make_err(code, msg);
        }

        const int matches_found = res.value("matches_found", 0);
        const int active_match = res.value("match_index", 0);
        const std::string snippet = res.value("context_snippet", "");
        const int scroll_y = res.value("scroll_y", 0);
        const int total_height = res.value("total_height", 0);

        ActionResult ar;
        ar.success = true;
        if (want_shot && res.value("screenshot_ok", false)) {
            const std::string shot = res.value("screenshot_path", std::string{});
            std::error_code ec;
            if (!shot.empty() && fs::exists(shot, ec)) {
                prune_old_screenshots(shot);
                ar.images.push_back(shot);
            }
        }

        std::string out;
        if (matches_found > 0) {
            out = fmt::format(
                "Browser Find: Found {} match(es) for '{}'. Jumped to match {}/{} (scroll: {}px / {}px).\n\n"
                "Context Snippet:\n\"{}\"\n",
                matches_found, query, active_match, matches_found, scroll_y, total_height, snippet);
        } else {
            out = fmt::format(
                "Browser Find: No matches found for '{}' on the current page ({}).\n",
                query, current_url_.empty() ? "empty page" : current_url_);
        }
        ar.llm_facing_output = out;
        return ar;
    }

    if (action_name == "browser_login") {
        std::string domain = args.value("domain", "");
        if (domain.empty()) {
            domain = CredentialStore::normalize_domain(current_url_);
        }
        if (domain.empty()) {
            return make_err("missing_domain", "No domain specified and no active webpage loaded to infer domain");
        }

        auto cred_opt = CredentialStore::default_store().get(domain);
        if (!cred_opt) {
            return make_err("no_credentials_found",
                            fmt::format("No credentials stored for domain '{}'. Use CLI 'aquila credentials set {} ...' to save credentials.",
                                        domain, domain));
        }

        const bool submit = args.value("submit", true);
        const bool want_shot = args.value("screenshot", true);
        Json params = Json::object({
            {"username", cred_opt->username},
            {"password", cred_opt->password},
            {"submit", submit},
        });
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }

        std::string code, msg;
        const Json res = call_worker("login", params, code, msg);
        if (!code.empty()) {
            return make_err(code, msg);
        }

        const std::string status = res.value("status", "unknown");
        const bool is_2fa = res.value("two_factor_detected", false);

        ActionResult ar;
        ar.success = true;
        if (want_shot && res.value("screenshot_ok", false)) {
            const std::string shot = res.value("screenshot_path", std::string{});
            std::error_code ec;
            if (!shot.empty() && fs::exists(shot, ec)) {
                prune_old_screenshots(shot);
                ar.images.push_back(shot);
            }
        }

        // Never echo the raw password in the output!
        ar.llm_facing_output = fmt::format(
            "Browser Login Attempt on '{}' (user: {}):\n"
            "- Status: {}\n"
            "- 2FA Prompt Detected: {}\n"
            "- Current URL: {}\n"
            "- Page Title: {}\n"
            "{}",
            domain, cred_opt->username, status, is_2fa ? "YES (Phone/Authenticator approval required)" : "No",
            res.value("url", ""), res.value("title", ""),
            is_2fa ? "[NOTE: A 2-Factor Authentication prompt was detected. If phone approval / Duo push is required, approve it on your phone or use 'aquila browser --login <url>' for interactive login.]" : "");
        return ar;
    }

    if (action_name == "browser_extract_text") {
        const bool want_shot = args.value("screenshot", false);
        Json params = Json::object({
            {"max_chars", args.value("max_chars", static_cast<int>(max_output_chars_))},
        });
        if (args.contains("selector") && args["selector"].is_string()) {
            params["selector"] = args["selector"].get<std::string>();
        }
        if (want_shot) {
            params["screenshot_path"] = next_screenshot_path();
        }
        std::string code, msg;
        const Json res = call_worker("extract_text", params, code, msg);
        if (!code.empty()) {
            return make_err(code, msg);
        }
        return format_snapshot_result("Browser Extracted Text", res, want_shot);
    }

    if (action_name == "browser_screenshot") {
        const Json params = Json::object({
            {"screenshot_path", next_screenshot_path()},
        });
        std::string code, msg;
        const Json res = call_worker("screenshot", params, code, msg);
        if (!code.empty()) {
            return make_err(code, msg);
        }
        return format_snapshot_result("Browser Screenshot", res, true);
    }

    return make_err("unknown_action", "Unknown BrowserModule action: " + action_name);
}

} // namespace aquila::knowledge

