#ifdef _WIN32

#include "aquila/exec/process.hpp"

#include "capture.hpp"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <algorithm>
#include <chrono>
#include <cwctype>
#include <memory>
#include <system_error>

namespace aquila::exec {

namespace fs = std::filesystem;

namespace {

std::wstring widen(std::string_view s) {
    if (s.empty()) return {};
    const int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
    std::wstring w(static_cast<std::size_t>(n), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), w.data(), n);
    return w;
}

std::string narrow(std::wstring_view w) {
    if (w.empty()) return {};
    const int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), nullptr, 0, nullptr, nullptr);
    std::string s(static_cast<std::size_t>(n), '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), s.data(), n, nullptr, nullptr);
    return s;
}

std::string last_error_text() {
    const DWORD code = GetLastError();
    return std::system_category().message(static_cast<int>(code)) + " (" + std::to_string(code) + ")";
}

std::wstring lower(std::wstring s) {
    std::transform(s.begin(), s.end(), s.begin(), [](wchar_t c) { return static_cast<wchar_t>(std::towlower(c)); });
    return s;
}

// Quoting that CommandLineToArgvW / the MSVC CRT parse back to the same argv.
void append_quoted(std::wstring& cmd, const std::wstring& arg) {
    if (!arg.empty() && arg.find_first_of(L" \t\n\v\"") == std::wstring::npos) {
        cmd += arg;
        return;
    }
    cmd += L'"';
    for (auto it = arg.begin();; ++it) {
        std::size_t slashes = 0;
        while (it != arg.end() && *it == L'\\') {
            ++it;
            ++slashes;
        }
        if (it == arg.end()) {
            cmd.append(slashes * 2, L'\\');
            break;
        }
        if (*it == L'"') {
            cmd.append(slashes * 2 + 1, L'\\');
        } else {
            cmd.append(slashes, L'\\');
        }
        cmd += *it;
    }
    cmd += L'"';
}

struct Handle {
    HANDLE h = nullptr;
    Handle() = default;
    explicit Handle(HANDLE v) : h(v) {}
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    ~Handle() { reset(); }
    void reset(HANDLE v = nullptr) {
        if (h != nullptr && h != INVALID_HANDLE_VALUE) CloseHandle(h);
        h = v;
    }
    [[nodiscard]] bool valid() const { return h != nullptr && h != INVALID_HANDLE_VALUE; }
};

// Current environment minus secrets, plus overrides, sorted case-insensitively
// (CreateProcessW requires a sorted block).
std::wstring environment_block(const std::map<std::string, std::string>& overrides) {
    std::vector<std::pair<std::wstring, std::wstring>> vars;
    if (wchar_t* block = GetEnvironmentStringsW()) {
        for (const wchar_t* p = block; *p != L'\0'; p += wcslen(p) + 1) {
            const std::wstring entry(p);
            const auto eq = entry.find(L'=', 1);  // entries like "=C:=C:\x" start with '='
            if (eq == std::wstring::npos) continue;
            const auto name = entry.substr(0, eq);
            if (is_secret_env_name(narrow(name))) continue;
            vars.emplace_back(name, entry.substr(eq + 1));
        }
        FreeEnvironmentStringsW(block);
    }
    for (const auto& [k, v] : overrides) {
        const auto wk = widen(k);
        const auto it = std::find_if(vars.begin(), vars.end(), [&](const auto& e) { return lower(e.first) == lower(wk); });
        if (it != vars.end()) it->second = widen(v);
        else vars.emplace_back(wk, widen(v));
    }
    std::sort(vars.begin(), vars.end(), [](const auto& a, const auto& b) { return lower(a.first) < lower(b.first); });
    std::wstring out;
    for (const auto& [k, v] : vars) {
        out += k;
        out += L'=';
        out += v;
        out += L'\0';
    }
    out += L'\0';
    return out;
}

}  // namespace

fs::path find_program(const std::string& program) {
    if (program.find_first_of("/\\") != std::string::npos) return fs::path(widen(program));
    std::vector<std::wstring> exts;
    {
        wchar_t buf[4096];
        const DWORD n = GetEnvironmentVariableW(L"PATHEXT", buf, 4096);
        const std::wstring pathext = (n > 0 && n < 4096) ? std::wstring(buf, n) : L".COM;.EXE;.BAT;.CMD";
        std::size_t start = 0;
        while (start <= pathext.size()) {
            const auto semi = pathext.find(L';', start);
            const auto e = pathext.substr(start, semi == std::wstring::npos ? std::wstring::npos : semi - start);
            if (!e.empty()) exts.push_back(lower(e));
            if (semi == std::wstring::npos) break;
            start = semi + 1;
        }
    }
    const auto wprog = widen(program);
    const auto prog_ext = lower(fs::path(wprog).extension().wstring());
    const bool has_ext = !prog_ext.empty() && std::find(exts.begin(), exts.end(), prog_ext) != exts.end();

    std::wstring path_var;
    if (const DWORD n = GetEnvironmentVariableW(L"PATH", nullptr, 0); n > 0) {
        path_var.resize(n);
        path_var.resize(GetEnvironmentVariableW(L"PATH", path_var.data(), n));
    }
    std::size_t start = 0;
    while (start <= path_var.size()) {
        const auto semi = path_var.find(L';', start);
        std::wstring dir = path_var.substr(start, semi == std::wstring::npos ? std::wstring::npos : semi - start);
        dir.erase(std::remove(dir.begin(), dir.end(), L'"'), dir.end());
        if (!dir.empty()) {
            std::error_code ec;
            if (has_ext) {
                const auto p = fs::path(dir) / wprog;
                if (fs::is_regular_file(p, ec)) return p;
            }
            for (const auto& e : exts) {
                const auto p = fs::path(dir) / (wprog + e);
                if (fs::is_regular_file(p, ec)) return p;
            }
        }
        if (semi == std::wstring::npos) break;
        start = semi + 1;
    }
    return {};
}

RunResult run(const RunOptions& opt) {
    RunResult r;
    if (opt.argv.empty()) {
        r.error = "empty argv";
        return r;
    }
    const auto program = find_program(opt.argv[0]);
    std::error_code ec;
    if (program.empty() || !fs::is_regular_file(program, ec)) {
        r.error = "program not found: " + opt.argv[0];
        return r;
    }

    std::wstring app = program.wstring();
    std::wstring cmd;
    const auto ext = lower(program.extension().wstring());
    if (ext == L".bat" || ext == L".cmd") {
        // Batch files need cmd.exe, which re-parses the line: refuse its metacharacters.
        for (std::size_t i = 1; i < opt.argv.size(); ++i) {
            if (opt.argv[i].find_first_of("&|<>^%!\"\r\n") != std::string::npos) {
                r.error = "argument " + std::to_string(i) + " contains characters cmd.exe would interpret: " + opt.argv[i];
                return r;
            }
        }
        wchar_t sys[MAX_PATH];
        GetSystemDirectoryW(sys, MAX_PATH);
        const std::wstring comspec = std::wstring(sys) + L"\\cmd.exe";
        std::wstring inner;
        append_quoted(inner, app);
        for (std::size_t i = 1; i < opt.argv.size(); ++i) {
            inner += L' ';
            append_quoted(inner, widen(opt.argv[i]));
        }
        cmd = L"\"" + comspec + L"\" /d /s /c \"" + inner + L"\"";
        app = comspec;
    } else {
        append_quoted(cmd, app);
        for (std::size_t i = 1; i < opt.argv.size(); ++i) {
            cmd += L' ';
            append_quoted(cmd, widen(opt.argv[i]));
        }
    }

    SECURITY_ATTRIBUTES sa{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    HANDLE rd_raw = nullptr;
    HANDLE wr_raw = nullptr;
    if (!CreatePipe(&rd_raw, &wr_raw, &sa, 0)) {
        r.error = "CreatePipe failed: " + last_error_text();
        return r;
    }
    Handle rd(rd_raw);
    Handle wr(wr_raw);
    SetHandleInformation(rd.h, HANDLE_FLAG_INHERIT, 0);

    Handle nul;
    Handle in_rd;
    Handle in_wr;
    if (!opt.stdin_data.empty()) {
        HANDLE in_rd_raw = nullptr;
        HANDLE in_wr_raw = nullptr;
        if (!CreatePipe(&in_rd_raw, &in_wr_raw, &sa, 0)) {
            r.error = "CreatePipe (stdin) failed: " + last_error_text();
            return r;
        }
        in_rd.reset(in_rd_raw);
        in_wr.reset(in_wr_raw);
        SetHandleInformation(in_wr.h, HANDLE_FLAG_INHERIT, 0);
    } else {
        nul.reset(CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, nullptr));
    }

    // Only the designated pipe ends are inherited, never other handles of this process.
    SIZE_T attr_size = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &attr_size);
    std::vector<char> attr_buf(attr_size);
    auto* attrs = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attr_buf.data());
    InitializeProcThreadAttributeList(attrs, 1, 0, &attr_size);
    HANDLE inherit[2] = {wr.h, in_rd.valid() ? in_rd.h : nul.h};
    UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherit, sizeof(inherit), nullptr, nullptr);

    STARTUPINFOEXW si{};
    si.StartupInfo.cb = sizeof(si);
    si.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    si.StartupInfo.hStdInput = in_rd.valid() ? in_rd.h : nul.h;
    si.StartupInfo.hStdOutput = wr.h;
    si.StartupInfo.hStdError = wr.h;
    si.lpAttributeList = attrs;

    Handle job(CreateJobObjectW(nullptr, nullptr));
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    SetInformationJobObject(job.h, JobObjectExtendedLimitInformation, &limits, sizeof(limits));

    auto env = environment_block(opt.env);
    const std::wstring cwd = opt.cwd.empty() ? std::wstring() : opt.cwd.wstring();
    PROCESS_INFORMATION pi{};
    const auto start = std::chrono::steady_clock::now();
    const BOOL created = CreateProcessW(app.c_str(), cmd.data(), nullptr, nullptr, TRUE,
                                        EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT |
                                            CREATE_NO_WINDOW,
                                        env.data(), cwd.empty() ? nullptr : cwd.c_str(), &si.StartupInfo, &pi);
    DeleteProcThreadAttributeList(attrs);
    if (!created) {
        r.error = "cannot start " + opt.argv[0] + ": " + last_error_text();
        return r;
    }
    Handle proc(pi.hProcess);
    Handle thread(pi.hThread);
    AssignProcessToJobObject(job.h, proc.h);

    if (in_wr.valid()) {
        DWORD written = 0;
        WriteFile(in_wr.h, opt.stdin_data.data(), static_cast<DWORD>(opt.stdin_data.size()), &written, nullptr);
        in_wr.reset();
    }
    in_rd.reset();

    ResumeThread(thread.h);
    wr.reset();
    nul.reset();
    r.started = true;

    detail::Capture cap(opt.max_output_bytes);
    char buf[8192];
    bool exited = false;
    std::chrono::steady_clock::time_point exit_time;
    const auto elapsed = [&] { return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count(); };
    for (;;) {
        DWORD avail = 0;
        const BOOL peek = PeekNamedPipe(rd.h, nullptr, 0, nullptr, &avail, nullptr);
        if (peek && avail > 0) {
            DWORD got = 0;
            if (ReadFile(rd.h, buf, std::min<DWORD>(avail, sizeof(buf)), &got, nullptr) && got > 0) cap.add(buf, got);
            continue;
        }
        if (!peek && exited) break;  // every writer closed and the process is gone
        if (!exited && WaitForSingleObject(proc.h, 10) == WAIT_OBJECT_0) {
            exited = true;
            exit_time = std::chrono::steady_clock::now();
            continue;
        }
        if (!exited && opt.check_cancelled && opt.check_cancelled()) {
            TerminateJobObject(job.h, 1);
            r.cancelled = true;
            r.timed_out = false;
            r.error = "process terminated: cancelled by user";
            WaitForSingleObject(proc.h, 1000);
            exited = true;
            exit_time = std::chrono::steady_clock::now();
            continue;
        }
        if (!exited && elapsed() > opt.timeout_s) {
            TerminateJobObject(job.h, 1);
            r.timed_out = true;
            WaitForSingleObject(proc.h, 5000);
            exited = true;
            exit_time = std::chrono::steady_clock::now();
            continue;
        }
        if (exited) {
            // Leftover children still hold the pipe: give them a moment, then end the job.
            if (std::chrono::steady_clock::now() - exit_time > std::chrono::milliseconds(500)) {
                TerminateJobObject(job.h, 1);
            }
            Sleep(10);
        }
    }
    DWORD code = 0;
    GetExitCodeProcess(proc.h, &code);
    r.exit_code = static_cast<int>(code);
    r.duration_s = elapsed();
    r.output = cap.str();
    r.truncated = cap.truncated();
    r.total_bytes = cap.total();
    return r;
}

}  // namespace aquila::exec

#endif  // _WIN32
