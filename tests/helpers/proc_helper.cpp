// Test helper for aquila::exec::run. Modes:
//   sleep MS | print N | exit K | env NAME | stderr | cwd | args A B ... | cat PATH CODE
//   spawn-grandchild MS   start "sleep MS" as a child, print its pid, then sleep MS
//   orphan MS             start "sleep MS" as a child, print its pid, then exit at once
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
#include <thread>

#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <sys/types.h>
#include <unistd.h>
#endif

namespace {

void sleep_ms(long ms) {
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

// Starts this executable with "sleep MS"; the child inherits stdout/stderr.
long spawn_sleeper(const char* self, const char* ms) {
#ifdef _WIN32
    (void)self;
    wchar_t exe[MAX_PATH];
    GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring cmd = L"\"" + std::wstring(exe) + L"\" sleep ";
    for (const char* p = ms; *p; ++p) cmd += static_cast<wchar_t>(*p);
    STARTUPINFOW si{};
    si.cb = sizeof si;
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    si.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    si.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION pi{};
    if (!CreateProcessW(exe, cmd.data(), nullptr, nullptr, TRUE, 0, nullptr, nullptr, &si, &pi)) return -1;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return static_cast<long>(pi.dwProcessId);
#else
    const pid_t pid = fork();
    if (pid == 0) {
        execl(self, self, "sleep", ms, static_cast<char*>(nullptr));
        _exit(127);
    }
    return static_cast<long>(pid);
#endif
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    const std::string mode = argv[1];
    const char* arg = argc > 2 ? argv[2] : "0";
    if (mode == "sleep") {
        sleep_ms(std::atol(arg));
        return 0;
    }
    if (mode == "print") {
        for (long i = 0; i < std::atol(arg); ++i) std::printf("line %ld\n", i);
        return 0;
    }
    if (mode == "exit") return std::atoi(arg);
    if (mode == "env") {
        const char* v = std::getenv(arg);
        std::printf("%s=%s\n", arg, v ? v : "<unset>");
        return 0;
    }
    if (mode == "stderr") {
        std::fprintf(stdout, "to stdout\n");
        std::fflush(stdout);
        std::fprintf(stderr, "to stderr\n");
        return 3;
    }
    if (mode == "cwd") {
        const auto u = std::filesystem::current_path().generic_u8string();
        std::printf("%s\n", reinterpret_cast<const char*>(u.c_str()));
        return 0;
    }
    if (mode == "cat") {  // cat PATH CODE: replay a captured tool log, exit with CODE
        if (FILE* f = std::fopen(arg, "rb")) {
            char buf[4096];
            std::size_t n = 0;
            while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) std::fwrite(buf, 1, n, stdout);
            std::fclose(f);
        }
        return argc > 3 ? std::atoi(argv[3]) : 0;
    }
    if (mode == "args") {
        for (int i = 2; i < argc; ++i) std::printf("[%s]\n", argv[i]);
        return 0;
    }
    if (mode == "echo-stdin") {
        char buf[4096];
        std::size_t n = 0;
        while ((n = std::fread(buf, 1, sizeof buf, stdin)) > 0) std::fwrite(buf, 1, n, stdout);
        return 0;
    }
    if (mode == "spawn-grandchild" || mode == "orphan") {
        const long pid = spawn_sleeper(argv[0], arg);
        std::printf("grandchild %ld\n", pid);
        std::fflush(stdout);
        if (mode == "spawn-grandchild") sleep_ms(std::atol(arg));
        return 0;
    }
    return 2;
}
