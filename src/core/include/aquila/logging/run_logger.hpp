#pragma once

#include "aquila/json.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace aquila::logging {

class RunLogger {
public:
    RunLogger() = default;
    ~RunLogger();

    // Non-copyable, movable
    RunLogger(const RunLogger&) = delete;
    RunLogger& operator=(const RunLogger&) = delete;
    RunLogger(RunLogger&&) noexcept;
    RunLogger& operator=(RunLogger&&) noexcept;

    // Start a new session in <workspace_root>/Agent-Logs/
    bool start_session(const std::string& recipe_id,
                       const std::string& mode,
                       const std::string& instance_id,
                       const std::string& goal,
                       const std::filesystem::path& workspace_root = ".");

    void log_turn_start(std::uint64_t turn_index);

    // Records the full un-truncated thinking trace
    void log_thinking(std::uint64_t turn_index,
                      const std::string& thinking_text,
                      const std::string& surface = "turn");

    void log_llm_response(std::uint64_t turn_index,
                          const std::string& raw_content,
                          bool parsed,
                          const std::string& thought);

    void log_action_call(std::uint64_t turn_index,
                         const std::string& module,
                         const std::string& action,
                         const Json& args);

    void log_action_result(std::uint64_t turn_index,
                           const std::string& module,
                           const std::string& action,
                           bool success,
                           const std::string& output,
                           const std::string& error_code = "");

    void log_guidance(std::uint64_t turn_index,
                      const std::string& message);

    void log_exit_gate(const std::string& hook_module,
                       const std::string& hook_action,
                       bool success,
                       const std::string& output,
                       const std::string& error_code = "");

    void log_session_end(bool success,
                         const std::string& outcome,
                         const std::string& completion_output,
                         std::uint64_t total_turns);

    void flush();

    [[nodiscard]] bool is_active() const;
    [[nodiscard]] std::filesystem::path log_path() const;
    [[nodiscard]] std::filesystem::path jsonl_path() const;
    [[nodiscard]] std::string recipe_id() const;

private:
    void write_log_line(const std::string& line);
    void write_jsonl_record(const std::string& event_type, const Json& data);

    mutable std::mutex mutex_;
    bool active_ = false;
    std::string recipe_id_;
    std::string mode_;
    std::string instance_id_;
    std::filesystem::path log_path_;
    std::filesystem::path jsonl_path_;
    std::ofstream log_stream_;
    std::ofstream jsonl_stream_;
    std::chrono::system_clock::time_point session_start_time_;
};

}  // namespace aquila::logging
