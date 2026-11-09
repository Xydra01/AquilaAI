// src/core/logging/run_logger.cpp
#include "aquila/logging/run_logger.hpp"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

namespace aquila::logging {

namespace {

std::string format_time_iso(const std::chrono::system_clock::time_point& tp) {
    const std::time_t t = std::chrono::system_clock::to_time_t(tp);
    std::tm tm_buf{};
#if defined(_WIN32)
    localtime_s(&tm_buf, &t);
#else
    localtime_r(&t, &tm_buf);
#endif
    std::ostringstream ss;
    ss << std::put_time(&tm_buf, "%Y-%m-%d %H:%M:%S");
    return ss.str();
}

std::string format_timestamp_slug(const std::chrono::system_clock::time_point& tp) {
    const std::time_t t = std::chrono::system_clock::to_time_t(tp);
    std::tm tm_buf{};
#if defined(_WIN32)
    localtime_s(&tm_buf, &t);
#else
    localtime_r(&t, &tm_buf);
#endif
    std::ostringstream ss;
    ss << std::put_time(&tm_buf, "%Y%m%d_%H%M%S");
    return ss.str();
}

std::string sanitize_filename(const std::string& input) {
    std::string out;
    for (char c : input) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-') {
            out.push_back(c);
        } else {
            out.push_back('_');
        }
    }
    return out.empty() ? "session" : out;
}

}  // namespace

RunLogger::~RunLogger() {
    flush();
    if (log_stream_.is_open()) log_stream_.close();
    if (jsonl_stream_.is_open()) jsonl_stream_.close();
}

RunLogger::RunLogger(RunLogger&& other) noexcept {
    std::lock_guard<std::mutex> lock(other.mutex_);
    active_ = other.active_;
    recipe_id_ = std::move(other.recipe_id_);
    mode_ = std::move(other.mode_);
    instance_id_ = std::move(other.instance_id_);
    log_path_ = std::move(other.log_path_);
    jsonl_path_ = std::move(other.jsonl_path_);
    log_stream_ = std::move(other.log_stream_);
    jsonl_stream_ = std::move(other.jsonl_stream_);
    session_start_time_ = other.session_start_time_;
    other.active_ = false;
}

RunLogger& RunLogger::operator=(RunLogger&& other) noexcept {
    if (this != &other) {
        std::scoped_lock lock(mutex_, other.mutex_);
        flush();
        active_ = other.active_;
        recipe_id_ = std::move(other.recipe_id_);
        mode_ = std::move(other.mode_);
        instance_id_ = std::move(other.instance_id_);
        log_path_ = std::move(other.log_path_);
        jsonl_path_ = std::move(other.jsonl_path_);
        log_stream_ = std::move(other.log_stream_);
        jsonl_stream_ = std::move(other.jsonl_stream_);
        session_start_time_ = other.session_start_time_;
        other.active_ = false;
    }
    return *this;
}

bool RunLogger::start_session(const std::string& recipe_id,
                              const std::string& mode,
                              const std::string& instance_id,
                              const std::string& goal,
                              const std::filesystem::path& workspace_root) {
    std::lock_guard<std::mutex> lock(mutex_);
    flush();
    if (log_stream_.is_open()) log_stream_.close();
    if (jsonl_stream_.is_open()) jsonl_stream_.close();

    session_start_time_ = std::chrono::system_clock::now();
    recipe_id_ = recipe_id.empty() ? "recipe" : recipe_id;
    mode_ = mode.empty() ? "task" : mode;
    instance_id_ = instance_id.empty() ? "default" : instance_id;

    std::error_code ec;
    const std::filesystem::path logs_dir = (workspace_root.empty() ? std::filesystem::current_path() : workspace_root) / "Agent-Logs";
    std::filesystem::create_directories(logs_dir, ec);
    if (ec) {
        active_ = false;
        return false;
    }

    const std::string stamp = format_timestamp_slug(session_start_time_);
    const std::string base_name = sanitize_filename(recipe_id_) + "_" + stamp;
    log_path_ = logs_dir / (base_name + ".log");
    jsonl_path_ = logs_dir / (base_name + ".jsonl");

    log_stream_.open(log_path_, std::ios::out | std::ios::trunc);
    jsonl_stream_.open(jsonl_path_, std::ios::out | std::ios::trunc);

    active_ = log_stream_.is_open();

    const std::string time_str = format_time_iso(session_start_time_);
    std::ostringstream banner;
    banner << "============================================================\n"
           << "AQUILA AI FRAMEWORK - AGENT SESSION LOG\n"
           << "Session Start: " << time_str << "\n"
           << "Recipe ID:     " << recipe_id_ << "\n"
           << "Mode:          " << mode_ << "\n"
           << "Instance ID:   " << instance_id_ << "\n"
           << "Goal / Prompt: " << goal << "\n"
           << "============================================================\n\n";

    write_log_line(banner.str());

    Json meta = Json::object();
    meta["recipe_id"] = recipe_id_;
    meta["mode"] = mode_;
    meta["instance_id"] = instance_id_;
    meta["goal"] = goal;
    meta["log_file"] = log_path_.string();
    write_jsonl_record("session_start", meta);

    return active_;
}

void RunLogger::log_turn_start(std::uint64_t turn_index) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return;

    std::ostringstream ss;
    ss << "------------------------------------------------------------\n"
       << ">>> TURN " << turn_index << " START\n"
       << "------------------------------------------------------------\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["turn"] = turn_index;
    write_jsonl_record("turn_start", data);
}

void RunLogger::log_thinking(std::uint64_t turn_index,
                             const std::string& thinking_text,
                             const std::string& surface) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_ || thinking_text.empty()) return;

    std::ostringstream ss;
    ss << "[THINKING (" << (surface.empty() ? "turn" : surface) << ")]\n"
       << thinking_text << "\n\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["turn"] = turn_index;
    data["surface"] = surface;
    data["thinking"] = thinking_text;
    data["thinking_chars"] = thinking_text.size();
    write_jsonl_record("thinking_trace", data);
}

void RunLogger::log_llm_response(std::uint64_t turn_index,
                                 const std::string& raw_content,
                                 bool parsed,
                                 const std::string& thought) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return;

    std::ostringstream ss;
    ss << "[LLM RESPONSE] (parsed=" << (parsed ? "true" : "false") << ")\n";
    if (!thought.empty()) {
        ss << "Thought: " << thought << "\n";
    }
    ss << "Raw Reply:\n" << raw_content << "\n\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["turn"] = turn_index;
    data["parsed"] = parsed;
    data["thought"] = thought;
    data["raw_content"] = raw_content;
    write_jsonl_record("llm_response", data);
}

void RunLogger::log_action_call(std::uint64_t turn_index,
                                const std::string& module,
                                const std::string& action,
                                const Json& args) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return;

    std::ostringstream ss;
    ss << ">>> DISPATCH ACTION: " << module << "::" << action << "\n"
       << "Arguments:\n" << args.dump(2) << "\n\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["turn"] = turn_index;
    data["module"] = module;
    data["action"] = action;
    data["args"] = args;
    write_jsonl_record("action_call", data);
}

void RunLogger::log_action_result(std::uint64_t turn_index,
                                  const std::string& module,
                                  const std::string& action,
                                  bool success,
                                  const std::string& output,
                                  const std::string& error_code) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return;

    std::ostringstream ss;
    ss << "<<< ACTION RESULT: " << module << "::" << action
       << " [" << (success ? "SUCCESS" : "FAILED") << "]";
    if (!error_code.empty()) {
        ss << " (error_code: " << error_code << ")";
    }
    ss << "\nOutput:\n" << output << "\n\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["turn"] = turn_index;
    data["module"] = module;
    data["action"] = action;
    data["success"] = success;
    if (!error_code.empty()) data["error_code"] = error_code;
    data["output"] = output;
    write_jsonl_record("action_result", data);
}

void RunLogger::log_guidance(std::uint64_t turn_index,
                             const std::string& message) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_ || message.empty()) return;

    std::ostringstream ss;
    ss << "[SYSTEM GUIDANCE / WARNING]:\n" << message << "\n\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["turn"] = turn_index;
    data["guidance"] = message;
    write_jsonl_record("system_guidance", data);
}

void RunLogger::log_exit_gate(const std::string& hook_module,
                              const std::string& hook_action,
                              bool success,
                              const std::string& output,
                              const std::string& error_code) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return;

    std::ostringstream ss;
    ss << "============================================================\n"
       << "RECIPE EXIT GATE: " << hook_module << "::" << hook_action
       << " [" << (success ? "PASSED" : "FAILED") << "]\n";
    if (!error_code.empty()) {
        ss << "Error Code: " << error_code << "\n";
    }
    ss << "Validation Details:\n" << output << "\n"
       << "============================================================\n\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["hook_module"] = hook_module;
    data["hook_action"] = hook_action;
    data["success"] = success;
    if (!error_code.empty()) data["error_code"] = error_code;
    data["output"] = output;
    write_jsonl_record("exit_gate", data);
}

void RunLogger::log_session_end(bool success,
                                const std::string& outcome,
                                const std::string& completion_output,
                                std::uint64_t total_turns) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!active_) return;

    const auto now = std::chrono::system_clock::now();
    const auto dur_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - session_start_time_).count();

    std::ostringstream ss;
    ss << "============================================================\n"
       << "SESSION FINISHED: [" << (success ? "SUCCEEDED" : "FAILED") << "]\n"
       << "Outcome:     " << outcome << "\n"
       << "Total Turns: " << total_turns << "\n"
       << "Duration:    " << (static_cast<double>(dur_ms) / 1000.0) << "s\n";
    if (!completion_output.empty()) {
        ss << "Completion Output:\n" << completion_output << "\n";
    }
    ss << "============================================================\n";
    write_log_line(ss.str());

    Json data = Json::object();
    data["success"] = success;
    data["outcome"] = outcome;
    data["total_turns"] = total_turns;
    data["duration_ms"] = dur_ms;
    data["completion_output"] = completion_output;
    write_jsonl_record("session_end", data);

    flush();
}

void RunLogger::flush() {
    if (log_stream_.is_open()) log_stream_.flush();
    if (jsonl_stream_.is_open()) jsonl_stream_.flush();
}

bool RunLogger::is_active() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return active_;
}

std::filesystem::path RunLogger::log_path() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return log_path_;
}

std::filesystem::path RunLogger::jsonl_path() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return jsonl_path_;
}

std::string RunLogger::recipe_id() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return recipe_id_;
}

void RunLogger::write_log_line(const std::string& line) {
    if (log_stream_.is_open()) {
        log_stream_ << line;
        log_stream_.flush();
    }
}

void RunLogger::write_jsonl_record(const std::string& event_type, const Json& data) {
    if (jsonl_stream_.is_open()) {
        const std::string now_str = format_time_iso(std::chrono::system_clock::now());
        Json record = Json::object();
        record["ts"] = now_str;
        record["event"] = event_type;
        record["recipe"] = recipe_id_;
        record["mode"] = mode_;
        record["instance_id"] = instance_id_;
        for (auto it = data.begin(); it != data.end(); ++it) {
            record[it.key()] = it.value();
        }
        jsonl_stream_ << record.dump() << "\n";
        jsonl_stream_.flush();
    }
}

}  // namespace aquila::logging

