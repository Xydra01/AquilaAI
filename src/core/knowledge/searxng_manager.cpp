#include "aquila/knowledge/searxng_manager.hpp"

#include <httplib.h>

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <vector>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace aquila::knowledge {

namespace fs = std::filesystem;

namespace {

bool autostart_disabled_by_env() {
    if (const char* v = std::getenv("AQUILA_DISABLE_SEARXNG_AUTOSTART")) {
        const std::string_view sv(v);
        return sv == "1" || sv == "true" || sv == "TRUE" || sv == "yes";
    }
    return false;
}

fs::path current_executable_dir() {
#ifdef _WIN32
    wchar_t buf[MAX_PATH]{};
    const DWORD n = GetModuleFileNameW(nullptr, buf, MAX_PATH);
    if (n > 0 && n < MAX_PATH) {
        return fs::path(buf).parent_path();
    }
#else
    char buf[4096]{};
    const ssize_t n = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
    if (n > 0) {
        buf[n] = '\0';
        return fs::path(buf).parent_path();
    }
#endif
    return {};
}

#ifdef _WIN32
std::wstring utf8_to_wide(const std::string& s) {
    if (s.empty()) return {};
    const int len = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
    if (len <= 0) return {};
    std::wstring out(static_cast<std::size_t>(len), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), len);
    return out;
}

std::wstring quote_win_arg(const std::wstring& arg) {
    if (arg.find_first_of(L" \t\"") == std::wstring::npos) {
        return arg;
    }
    std::wstring q = L"\"";
    for (wchar_t c : arg) {
        if (c == L'"') q += L"\\\"";
        else q += c;
    }
    q += L"\"";
    return q;
}
#endif

} // namespace

struct SearxngManager::ChildProcess {
#ifdef _WIN32
    HANDLE proc_handle = nullptr;
    HANDLE job_handle = nullptr;
#else
    pid_t pid = -1;
#endif

    ~ChildProcess() { stop(); }

    bool is_alive() const {
#ifdef _WIN32
        if (!proc_handle) return false;
        DWORD code = 0;
        if (!GetExitCodeProcess(proc_handle, &code)) return false;
        return code == STILL_ACTIVE;
#else
        if (pid <= 0) return false;
        int status = 0;
        const pid_t r = waitpid(pid, &status, WNOHANG);
        return r == 0;
#endif
    }

    bool start(const std::string& script_path, const std::string& host, int port) {
        stop();
#ifdef _WIN32
        const std::vector<std::wstring> py_candidates = {L"python", L"py"};
        const std::wstring wscript = utf8_to_wide(script_path);
        const std::wstring whost = utf8_to_wide(host);
        const std::wstring wport = std::to_wstring(port);

        SECURITY_ATTRIBUTES sa{};
        sa.nLength = sizeof(sa);
        sa.bInheritHandle = TRUE;

        HANDLE nul_in = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                    &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        HANDLE nul_out = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                     &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);

        for (const auto& py : py_candidates) {
            std::wstring cmd = py;
            if (py == L"py") {
                cmd += L" -3";
            }
            cmd += L" " + quote_win_arg(wscript) + L" --host " + whost + L" --port " + wport;

            STARTUPINFOW si{};
            si.cb = sizeof(si);
            si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
            si.wShowWindow = SW_HIDE;
            si.hStdInput = (nul_in != INVALID_HANDLE_VALUE) ? nul_in : GetStdHandle(STD_INPUT_HANDLE);
            si.hStdOutput = (nul_out != INVALID_HANDLE_VALUE) ? nul_out : GetStdHandle(STD_OUTPUT_HANDLE);
            si.hStdError = (nul_out != INVALID_HANDLE_VALUE) ? nul_out : GetStdHandle(STD_ERROR_HANDLE);

            PROCESS_INFORMATION pi{};
            std::vector<wchar_t> cmd_mut(cmd.begin(), cmd.end());
            cmd_mut.push_back(L'\0');

            const DWORD flags = CREATE_NO_WINDOW | CREATE_SUSPENDED;
            if (!CreateProcessW(nullptr, cmd_mut.data(), nullptr, nullptr, TRUE, flags,
                                nullptr, nullptr, &si, &pi)) {
                continue;
            }

            job_handle = CreateJobObjectW(nullptr, nullptr);
            if (job_handle) {
                JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli{};
                jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                SetInformationJobObject(job_handle, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));
                AssignProcessToJobObject(job_handle, pi.hProcess);
            }
            ResumeThread(pi.hThread);
            CloseHandle(pi.hThread);
            proc_handle = pi.hProcess;

            if (nul_in != INVALID_HANDLE_VALUE) CloseHandle(nul_in);
            if (nul_out != INVALID_HANDLE_VALUE) CloseHandle(nul_out);
            return true;
        }

        if (nul_in != INVALID_HANDLE_VALUE) CloseHandle(nul_in);
        if (nul_out != INVALID_HANDLE_VALUE) CloseHandle(nul_out);
        return false;
#else
        pid_t child = fork();
        if (child < 0) return false;
        if (child == 0) {
            const int devnull = open("/dev/null", O_RDWR);
            if (devnull >= 0) {
                dup2(devnull, STDIN_FILENO);
                dup2(devnull, STDOUT_FILENO);
                dup2(devnull, STDERR_FILENO);
                if (devnull > 2) close(devnull);
            }
            const std::string port_str = std::to_string(port);
            execlp("python3", "python3", script_path.c_str(),
                   "--host", host.c_str(), "--port", port_str.c_str(),
                   static_cast<char*>(nullptr));
            execlp("python", "python", script_path.c_str(),
                   "--host", host.c_str(), "--port", port_str.c_str(),
                   static_cast<char*>(nullptr));
            _exit(127);
        }
        pid = child;
        return true;
#endif
    }

    void stop() {
#ifdef _WIN32
        if (job_handle) {
            // TerminateJobObject kills both the Python launcher shim and the real python.exe grandchild.
            TerminateJobObject(job_handle, 0);
        }
        if (proc_handle) {
            WaitForSingleObject(proc_handle, 1500);
            CloseHandle(proc_handle);
            proc_handle = nullptr;
        }
        if (job_handle) {
            CloseHandle(job_handle);
            job_handle = nullptr;
        }
#else
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
    }
};

SearxngManager& SearxngManager::instance() {
    static SearxngManager mgr;
    return mgr;
}

SearxngManager::SearxngManager() = default;

SearxngManager::~SearxngManager() {
    shutdown();
}

bool SearxngManager::parse_endpoint(std::string_view endpoint,
                                    std::string& host_out,
                                    int& port_out) {
    host_out = "127.0.0.1";
    port_out = 8888;
    std::string ep(endpoint);
    while (!ep.empty() && std::isspace(static_cast<unsigned char>(ep.front()))) ep.erase(ep.begin());
    while (!ep.empty() && std::isspace(static_cast<unsigned char>(ep.back()))) ep.pop_back();
    if (ep.empty()) {
        return true;
    }
    bool is_https = false;
    if (ep.starts_with("http://")) {
        ep = ep.substr(7);
    } else if (ep.starts_with("https://")) {
        ep = ep.substr(8);
        is_https = true;
    }
    if (const auto slash = ep.find('/'); slash != std::string::npos) {
        ep = ep.substr(0, slash);
    }
    if (ep.empty()) {
        return false;
    }
    if (const auto colon = ep.find(':'); colon != std::string::npos) {
        host_out = ep.substr(0, colon);
        try {
            port_out = std::stoi(ep.substr(colon + 1));
        } catch (...) {
            return false;
        }
    } else {
        host_out = ep;
        port_out = is_https ? 443 : 80;
    }
    return !host_out.empty() && port_out > 0 && port_out <= 65535;
}

bool SearxngManager::is_loopback_endpoint(std::string_view endpoint) {
    std::string host;
    int port = 0;
    if (!parse_endpoint(endpoint, host, port)) {
        return false;
    }
    std::transform(host.begin(), host.end(), host.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return host == "127.0.0.1" || host == "localhost" || host == "::1";
}

std::string SearxngManager::resolve_script_path(std::string_view explicit_override) {
    std::error_code ec;
    auto check_file = [&](const fs::path& p) -> std::string {
        if (!p.empty() && fs::exists(p, ec) && fs::is_regular_file(p, ec)) {
            return fs::weakly_canonical(p, ec).string();
        }
        return {};
    };

    if (!explicit_override.empty()) {
        if (auto found = check_file(fs::path(explicit_override)); !found.empty()) return found;
    }
    if (const char* env_p = std::getenv("AQUILA_SEARXNG_SCRIPT")) {
        if (auto found = check_file(fs::path(env_p)); !found.empty()) return found;
    }
#ifdef AQUILA_DEFAULT_SEARXNG_SCRIPT
    if (auto found = check_file(fs::path(AQUILA_DEFAULT_SEARXNG_SCRIPT)); !found.empty()) {
        return found;
    }
#endif
    const fs::path exe_dir = current_executable_dir();
    if (!exe_dir.empty()) {
        fs::path probe = exe_dir;
        for (int depth = 0; depth < 6; ++depth) {
            if (auto found = check_file(probe / "scripts" / "run_searxng.py"); !found.empty()) {
                return found;
            }
            if (!probe.has_parent_path() || probe == probe.parent_path()) break;
            probe = probe.parent_path();
        }
    }
    if (auto found = check_file(fs::current_path(ec) / "scripts" / "run_searxng.py"); !found.empty()) {
        return found;
    }
    return {};
}

bool SearxngManager::is_healthy(std::string_view endpoint, int timeout_ms) const {
    std::string host;
    int port = 8888;
    if (!parse_endpoint(endpoint, host, port)) {
        return false;
    }
    httplib::Client cli(host, port);
    const int sec = std::max(0, timeout_ms / 1000);
    const int usec = std::max(1000, (timeout_ms % 1000) * 1000);
    cli.set_connection_timeout(sec, usec);
    cli.set_read_timeout(sec, usec);
    auto res = cli.Get("/health");
    return res && res->status == 200;
}

bool SearxngManager::ensure_running(std::string_view endpoint, int wait_ready_ms) {
    if (shutting_down_.load()) {
        return false;
    }
    const std::string ep = endpoint.empty() ? std::string("http://127.0.0.1:8888") : std::string(endpoint);

    // Fast path: already serving (either our managed child or an external SearXNG instance).
    if (is_healthy(ep, 250)) {
        return true;
    }

    if (autostart_disabled_by_env() || !is_loopback_endpoint(ep)) {
        return false;
    }

    std::lock_guard<std::mutex> lk(mu_);
    if (shutting_down_.load()) {
        return false;
    }
    // Re-check under lock in case another thread just started it.
    if (is_healthy(ep, 250)) {
        return true;
    }

    std::string host;
    int port = 8888;
    if (!parse_endpoint(ep, host, port)) {
        return false;
    }
    if (host == "localhost") {
        host = "127.0.0.1";
    }

    const std::string script = resolve_script_path();
    if (script.empty()) {
        return false;
    }

    if (!child_ || !child_->is_alive() || managed_endpoint_ != ep) {
        auto proc = std::make_unique<ChildProcess>();
        if (!proc->start(script, host, port)) {
            return false;
        }
        child_ = std::move(proc);
        managed_endpoint_ = ep;
    }

    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(std::max(250, wait_ready_ms));
    while (!shutting_down_.load() && std::chrono::steady_clock::now() < deadline) {
        if (is_healthy(ep, 200)) {
            return true;
        }
        if (child_ && !child_->is_alive()) {
            child_.reset();
            return false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return is_healthy(ep, 250);
}

void SearxngManager::ensure_running_async(std::string endpoint) {
    if (shutting_down_.load() || autostart_disabled_by_env() || !is_loopback_endpoint(endpoint)) {
        return;
    }
    std::lock_guard<std::mutex> tlk(thread_mu_);
    if (warmup_thread_.joinable()) {
        warmup_thread_.join();
    }
    warmup_thread_ = std::thread([this, ep = std::move(endpoint)]() {
        (void)ensure_running(ep, 3500);
    });
}

void SearxngManager::shutdown() {
    shutting_down_.store(true);
    {
        std::lock_guard<std::mutex> tlk(thread_mu_);
        if (warmup_thread_.joinable()) {
            warmup_thread_.join();
        }
    }
    std::lock_guard<std::mutex> lk(mu_);
    if (child_) {
        child_->stop();
        child_.reset();
    }
    managed_endpoint_.clear();
}

bool SearxngManager::owns_process() const noexcept {
    std::lock_guard<std::mutex> lk(mu_);
    return child_ != nullptr && child_->is_alive();
}

} // namespace aquila::knowledge

