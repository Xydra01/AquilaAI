#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>

namespace aquila::knowledge {

// Manages the local zero-Docker Python SearXNG metasearch process (scripts/run_searxng.py).
// Option A lifecycle:
//   - Reuses any already-healthy server on the target loopback endpoint without taking ownership.
//   - Spawns a hidden child process tied to this process's lifetime (Win32 Job Object with
//     JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE on Windows, SIGTERM on POSIX) when none is listening.
//   - Never spawns processes for non-loopback remote endpoints.
class SearxngManager final {
public:
    static SearxngManager& instance();

    SearxngManager(const SearxngManager&) = delete;
    SearxngManager& operator=(const SearxngManager&) = delete;
    ~SearxngManager();

    // Fast HTTP GET /health probe.
    [[nodiscard]] bool is_healthy(std::string_view endpoint = "http://127.0.0.1:8888",
                                  int timeout_ms = 250) const;

    // Ensures a local SearXNG server is healthy at `endpoint`. If loopback and not yet running,
    // spawns scripts/run_searxng.py and polls /health up to `wait_ready_ms`.
    bool ensure_running(std::string_view endpoint = "http://127.0.0.1:8888",
                        int wait_ready_ms = 5000);

    // Non-blocking background warm-up (e.g. from GUI startup).
    void ensure_running_async(std::string endpoint = "http://127.0.0.1:8888");

    // Terminates the managed child process if owned by this process.
    void shutdown();

    [[nodiscard]] bool owns_process() const noexcept;

    [[nodiscard]] static bool is_loopback_endpoint(std::string_view endpoint);
    [[nodiscard]] static bool parse_endpoint(std::string_view endpoint,
                                             std::string& host_out,
                                             int& port_out);
    [[nodiscard]] static std::string resolve_script_path(std::string_view explicit_override = {});

private:
    SearxngManager();

    struct ChildProcess;

    mutable std::mutex mu_;
    std::unique_ptr<ChildProcess> child_;
    std::string managed_endpoint_;
    std::atomic<bool> shutting_down_{false};
    std::mutex thread_mu_;
    std::thread warmup_thread_;
};

} // namespace aquila::knowledge

