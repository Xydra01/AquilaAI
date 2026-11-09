#ifndef _WIN32

#include "aquila/exec/process.hpp"

#include "capture.hpp"

#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;

namespace aquila::exec {

namespace fs = std::filesystem;

fs::path find_program(const std::string& program) {
    if (program.find('/') != std::string::npos) return fs::path(program);
    const char* path = std::getenv("PATH");
    std::string dirs = path ? path : "/usr/bin:/bin";
    std::size_t start = 0;
    while (start <= dirs.size()) {
        const auto colon = dirs.find(':', start);
        const auto dir = dirs.substr(start, colon == std::string::npos ? std::string::npos : colon - start);
        if (!dir.empty()) {
            const auto p = fs::path(dir) / program;
            if (::access(p.c_str(), X_OK) == 0) {
                struct stat st {};
                if (::stat(p.c_str(), &st) == 0 && S_ISREG(st.st_mode)) return p;
            }
        }
        if (colon == std::string::npos) break;
        start = colon + 1;
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
    if (program.empty() || ::access(program.c_str(), X_OK) != 0) {
        r.error = "program not found: " + opt.argv[0];
        return r;
    }

    // Everything the child needs is built before fork (only async-signal-safe calls after).
    std::vector<std::string> env_strings;
    for (char** e = environ; e != nullptr && *e != nullptr; ++e) {
        const std::string entry(*e);
        const auto eq = entry.find('=');
        const auto name = entry.substr(0, eq);
        if (is_secret_env_name(name) || opt.env.count(name) != 0) continue;
        env_strings.push_back(entry);
    }
    for (const auto& [k, v] : opt.env) env_strings.push_back(k + "=" + v);
    std::vector<char*> envp;
    for (auto& s : env_strings) envp.push_back(s.data());
    envp.push_back(nullptr);
    std::vector<std::string> args = opt.argv;
    std::vector<char*> argv;
    for (auto& a : args) argv.push_back(a.data());
    argv.push_back(nullptr);
    const std::string path = program.string();
    const std::string cwd = opt.cwd.string();

    int out[2];
    int status_pipe[2];
    int in_pipe[2] = {-1, -1};
    if (::pipe(out) != 0 || ::pipe(status_pipe) != 0) {
        r.error = std::string("pipe failed: ") + std::strerror(errno);
        return r;
    }
    if (!opt.stdin_data.empty()) {
        if (::pipe(in_pipe) != 0) {
            ::close(out[0]);
            ::close(out[1]);
            ::close(status_pipe[0]);
            ::close(status_pipe[1]);
            r.error = std::string("stdin pipe failed: ") + std::strerror(errno);
            return r;
        }
        ::fcntl(in_pipe[1], F_SETFD, FD_CLOEXEC);
    }
    ::fcntl(out[0], F_SETFD, FD_CLOEXEC);
    ::fcntl(status_pipe[0], F_SETFD, FD_CLOEXEC);
    ::fcntl(status_pipe[1], F_SETFD, FD_CLOEXEC);

    const auto start = std::chrono::steady_clock::now();
    const pid_t pid = ::fork();
    if (pid < 0) {
        if (in_pipe[0] >= 0) { ::close(in_pipe[0]); ::close(in_pipe[1]); }
        r.error = std::string("fork failed: ") + std::strerror(errno);
        return r;
    }
    if (pid == 0) {
        ::setpgid(0, 0);
        if (in_pipe[0] >= 0) {
            ::dup2(in_pipe[0], 0);
            ::close(in_pipe[0]);
            ::close(in_pipe[1]);
        } else {
            const int devnull = ::open("/dev/null", O_RDONLY);
            if (devnull >= 0) ::dup2(devnull, 0);
        }
        ::dup2(out[1], 1);
        ::dup2(out[1], 2);
        int err = 0;
        if (!cwd.empty() && ::chdir(cwd.c_str()) != 0) {
            err = errno;
        } else {
            ::execve(path.c_str(), argv.data(), envp.data());
            err = errno;
        }
        (void)!::write(status_pipe[1], &err, sizeof err);
        ::_exit(127);
    }
    ::setpgid(pid, pid);  // also from the parent, to win the race with the child
    ::close(out[1]);
    ::close(status_pipe[1]);
    if (in_pipe[0] >= 0) ::close(in_pipe[0]);
    if (in_pipe[1] >= 0) {
        if (!opt.stdin_data.empty()) {
            (void)!::write(in_pipe[1], opt.stdin_data.data(), opt.stdin_data.size());
        }
        ::close(in_pipe[1]);
    }
    int child_err = 0;
    const auto n = ::read(status_pipe[0], &child_err, sizeof child_err);
    ::close(status_pipe[0]);
    if (n == static_cast<ssize_t>(sizeof child_err)) {
        int ignored = 0;
        ::waitpid(pid, &ignored, 0);
        ::close(out[0]);
        r.error = "cannot start " + opt.argv[0] + ": " + std::strerror(child_err);
        return r;
    }
    r.started = true;

    detail::Capture cap(opt.max_output_bytes);
    char buf[8192];
    bool exited = false;
    bool eof = false;
    int status = 0;
    std::chrono::steady_clock::time_point exit_time;
    const auto elapsed = [&] { return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count(); };
    while (!(exited && eof)) {
        if (!eof) {
            pollfd p{out[0], POLLIN, 0};
            if (::poll(&p, 1, 10) > 0) {
                const auto got = ::read(out[0], buf, sizeof buf);
                if (got > 0) cap.add(buf, static_cast<std::size_t>(got));
                else if (got == 0 || (errno != EINTR && errno != EAGAIN)) eof = true;
            }
        }
        if (!exited && ::waitpid(pid, &status, WNOHANG) == pid) {
            exited = true;
            exit_time = std::chrono::steady_clock::now();
        }
        if (!exited && opt.check_cancelled && opt.check_cancelled()) {
            ::killpg(pid, SIGKILL);
            r.cancelled = true;
            r.timed_out = false;
            r.error = "process terminated: cancelled by user";
            ::waitpid(pid, &status, 0);
            exited = true;
            exit_time = std::chrono::steady_clock::now();
        }
        if (!exited && elapsed() > opt.timeout_s) {
            ::killpg(pid, SIGKILL);
            r.timed_out = true;
            ::waitpid(pid, &status, 0);
            exited = true;
            exit_time = std::chrono::steady_clock::now();
        }
        if (exited && !eof && std::chrono::steady_clock::now() - exit_time > std::chrono::milliseconds(500)) {
            ::killpg(pid, SIGKILL);  // leftover children still hold the pipe
        }
        if (eof && !exited) ::usleep(10000);
    }
    ::close(out[0]);
    ::killpg(pid, SIGKILL);  // nothing from this run outlives it
    r.exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : WIFSIGNALED(status) ? 128 + WTERMSIG(status) : -1;
    r.duration_s = elapsed();
    r.output = cap.str();
    r.truncated = cap.truncated();
    r.total_bytes = cap.total();
    return r;
}

}  // namespace aquila::exec

#endif  // !_WIN32
