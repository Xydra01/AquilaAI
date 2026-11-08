#include "aquila/persona/persona_module.hpp"

#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <regex>
#include <sstream>

namespace aquila::persona {

namespace {

std::string now_iso() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm tm_buf{};
#ifdef _WIN32
    gmtime_s(&tm_buf, &t);
#else
    gmtime_r(&t, &tm_buf);
#endif
    std::ostringstream ss;
    ss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
    return ss.str();
}

}  // namespace

Json Persona::to_json() const {
    Json j = Json::object();
    j["id"] = id;
    j["display_name"] = display_name;
    j["tagline"] = tagline;
    j["description"] = description;
    j["greeting"] = greeting;
    j["avatar_relpath"] = avatar_relpath;
    j["created_at"] = created_at;
    j["last_chat_at"] = last_chat_at;
    j["build_complete"] = build_complete;
    return j;
}

Persona Persona::from_json(const Json& j) {
    Persona p;
    if (j.is_object()) {
        p.id = j.value("id", "");
        p.display_name = j.value("display_name", "Character");
        p.tagline = j.value("tagline", "");
        p.description = j.value("description", "");
        p.greeting = j.value("greeting", "Hello.");
        p.avatar_relpath = j.value("avatar_relpath", "");
        p.created_at = j.value("created_at", "");
        p.last_chat_at = j.value("last_chat_at", "");
        p.build_complete = j.value("build_complete", false);
    }
    return p;
}

Json ChatTurn::to_json() const {
    return Json::object({
        {"role", role},
        {"content", content},
        {"timestamp", timestamp}
    });
}

ChatTurn ChatTurn::from_json(const Json& j) {
    ChatTurn t;
    if (j.is_object()) {
        t.role = j.value("role", "");
        t.content = j.value("content", "");
        t.timestamp = j.value("timestamp", "");
    }
    return t;
}

PersonaModule::PersonaModule() : PersonaModule(ModuleContext{}) {}

PersonaModule::PersonaModule(ModuleContext ctx) : ctx_(std::move(ctx)) {}

std::filesystem::path PersonaModule::persona_dir() const {
    return ctx_.workspace_root / "Agent-Personas" / instance_id_ / "personas" / active_persona_id_;
}

std::filesystem::path PersonaModule::initialization_file() const {
    return persona_dir() / "initialization.md";
}

std::filesystem::path PersonaModule::preferences_file() const {
    return persona_dir() / "user_preferences.md";
}

std::filesystem::path PersonaModule::chat_history_file() const {
    return persona_dir() / "chat_history.json";
}

std::vector<ActionSchema> PersonaModule::get_actions() const {
    return {
        ActionSchema{
            "load_persona",
            "Loads a persona by ID and instance ID into the module session.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"persona_id", Json::object({{"type", "string"}, {"description", "Unique persona identifier"}})},
                    {"instance_id", Json::object({{"type", "string"}, {"description", "Instance ID (defaults to 'default')"}})},
                    {"display_name", Json::object({{"type", "string"}, {"description", "Initial display name if creating new"}})}
                })},
                {"required", Json::array({"persona_id"})}
            })
        },
        ActionSchema{
            "write_initialization",
            "Writes the initialization.md persona bible (must be at least 800 characters).",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"file_path", Json::object({{"type", "string"}, {"description", "Must be 'initialization.md'"}})},
                    {"content", Json::object({{"type", "string"}, {"description", "Persona initialization bible (voice, scene, backstory)"}})}
                })},
                {"required", Json::array({"file_path", "content"})}
            })
        },
        ActionSchema{
            "finalize_persona",
            "Marks persona build complete and writes final persona.json metadata.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"greeting", Json::object({{"type", "string"}, {"description", "Character opening greeting"}})},
                    {"tagline", Json::object({{"type", "string"}, {"description", "Short tagline or subtitle"}})},
                    {"display_name", Json::object({{"type", "string"}, {"description", "Updated display name"}})}
                })},
                {"required", Json::array({"greeting"})}
            })
        },
        ActionSchema{
            "update_preferences",
            "Updates user interaction preferences for the persona in user_preferences.md.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"preferences", Json::object({{"type", "string"}, {"description", "User preferences and chat guidelines"}})}
                })},
                {"required", Json::array({"preferences"})}
            })
        },
        ActionSchema{
            "chat_as_persona",
            "Records a chat turn and updates last_chat_at in persona history.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"user_message", Json::object({{"type", "string"}, {"description", "User input message"}})},
                    {"assistant_reply", Json::object({{"type", "string"}, {"description", "Optional assistant reply to append"}})}
                })},
                {"required", Json::array({"user_message"})}
            })
        },
        ActionSchema{
            "get_persona_info",
            "Returns JSON metadata for the currently active persona.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object()}
            })
        },
        ActionSchema{
            "verify_persona_quality",
            "Verifies persona profile utility: asserts initialization bible length (>= 800 chars), structured lore sections, absence of assistant leakage, and finalized greeting.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"min_chars", Json::object({{"type", "integer"}, {"description", "Minimum characters for initialization.md (default 800)"}})},
                    {"require_finalized", Json::object({{"type", "boolean"}, {"description", "Whether persona build must be finalized (default true)"}})}
                })}
            })
        }
    };
}

void PersonaModule::configure(const Json& initial_state) {
    if (!initial_state.is_object()) return;
    if (initial_state.contains("workspace_root")) {
        ctx_.workspace_root = initial_state["workspace_root"].get<std::string>();
    }
    if (initial_state.contains("instance_id")) {
        instance_id_ = initial_state["instance_id"].get<std::string>();
    }
    if (initial_state.contains("persona_id")) {
        const std::string pid = initial_state["persona_id"].get<std::string>();
        load_persona_record(pid, instance_id_);
    }
}

void PersonaModule::save_persona_record() {
    std::error_code ec;
    std::filesystem::create_directories(persona_dir(), ec);
    std::ofstream out(persona_dir() / "persona.json", std::ios::trunc | std::ios::binary);
    if (out.is_open()) {
        const auto text = persona_.to_json().dump(4);
        out.write(text.data(), static_cast<std::streamsize>(text.size()));
    }
}

bool PersonaModule::load_persona_record(const std::string& persona_id, const std::string& instance_id) {
    active_persona_id_ = persona_id;
    if (!instance_id.empty()) {
        instance_id_ = instance_id;
    }
    const auto file = persona_dir() / "persona.json";
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec)) {
        persona_ = Persona{};
        persona_.id = persona_id;
        persona_.created_at = now_iso();
        init_written_ = false;
        return false;
    }
    std::ifstream in(file, std::ios::binary);
    if (!in.is_open()) return false;
    try {
        Json j;
        in >> j;
        persona_ = Persona::from_json(j);
        init_written_ = false;
        load_chat_history();
        return true;
    } catch (...) {
        return false;
    }
}

void PersonaModule::save_chat_history() {
    std::error_code ec;
    std::filesystem::create_directories(persona_dir(), ec);
    std::ofstream out(chat_history_file(), std::ios::trunc | std::ios::binary);
    if (out.is_open()) {
        Json arr = Json::array();
        for (const auto& t : chat_history_) {
            arr.push_back(t.to_json());
        }
        const auto text = arr.dump(2);
        out.write(text.data(), static_cast<std::streamsize>(text.size()));
    }
}

void PersonaModule::load_chat_history() {
    chat_history_.clear();
    const auto file = chat_history_file();
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec)) return;
    std::ifstream in(file, std::ios::binary);
    if (!in.is_open()) return;
    try {
        Json j;
        in >> j;
        if (j.is_array()) {
            for (const auto& item : j) {
                chat_history_.push_back(ChatTurn::from_json(item));
            }
        }
    } catch (...) {
        chat_history_.clear();
    }
}

Json PersonaModule::export_state_snapshot() const {
    Json snap = Json::object();
    snap["has_active_persona"] = has_active_persona();
    if (has_active_persona()) {
        snap["persona_id"] = active_persona_id_;
        snap["instance_id"] = instance_id_;
        snap["display_name"] = persona_.display_name;
        snap["build_complete"] = persona_.build_complete;
        std::error_code ec;
        snap["init_doc_chars"] = std::filesystem::is_regular_file(initialization_file(), ec)
                                     ? std::filesystem::file_size(initialization_file(), ec)
                                     : 0;
        snap["chat_turns"] = chat_history_.size();
    }
    return snap;
}

void PersonaModule::restore_state_snapshot(const Json& snapshot) {
    if (!snapshot.is_object()) return;
    if (snapshot.value("has_active_persona", false)) {
        const std::string pid = snapshot.value("persona_id", "");
        const std::string iid = snapshot.value("instance_id", "default");
        load_persona_record(pid, iid);
    } else {
        active_persona_id_.clear();
        persona_ = Persona{};
        chat_history_.clear();
    }
}

ActionResult PersonaModule::run(const std::string& action_name, const Json& args) {
    if (action_name == "load_persona") {
        const std::string pid = args.value("persona_id", "");
        if (pid.empty()) {
            return fail("missing_persona_id", "❌ Error: persona_id must not be empty.");
        }
        if (persona_.build_complete && pid == active_persona_id_) {
            return ok("✅ Persona '" + persona_.display_name + "' is already fully built and finalized. Now call OrchestratorModule.complete_recipe to finish the recipe.");
        }
        const std::string iid = args.value("instance_id", instance_id_);
        const bool found = load_persona_record(pid, iid);
        if (args.contains("display_name") && !args["display_name"].get<std::string>().empty()) {
            persona_.display_name = args["display_name"].get<std::string>();
        }
        save_persona_record();
        if (found) {
            return ok("✅ Loaded existing persona '" + persona_.display_name + "' (" + pid + ").");
        }
        return ok("✅ Initialized new persona record for '" + persona_.display_name + "' (" + pid + ").");
    }

    if (action_name == "write_initialization") {
        if (!has_active_persona()) {
            return fail("no_active_persona", "❌ Error: No active persona loaded. Use load_persona first.");
        }
        const std::string file_path = args.value("file_path", "initialization.md");
        if (!file_path.empty() && file_path != "initialization.md") {
            return fail("invalid_file_path", "❌ Error: file_path must be 'initialization.md'.");
        }
        const std::string content = args.value("content", "");
        if (content.size() < kInitDocMinChars) {
            return fail("init_doc_too_short",
                        "❌ initialization.md is only " + std::to_string(content.size()) +
                        " characters (need at least " + std::to_string(kInitDocMinChars) +
                        "). Add personality, voice, backstory, and scene.");
        }
        const bool overwrite = args.value("overwrite", false);
        if (init_written_ && !overwrite) {
            return fail("already_written",
                        "❌ OS BLOCK: initialization.md is already written. Do NOT call write_persona_file again. "
                        "Call finalize_persona(greeting=..., tagline=...) then call OrchestratorModule.complete_recipe.");
        }

        std::error_code ec;
        std::filesystem::create_directories(persona_dir(), ec);
        std::ofstream out(initialization_file(), std::ios::trunc | std::ios::binary);
        if (!out.is_open()) {
            return fail("write_failed", "❌ Error opening initialization.md for writing.");
        }
        out.write(content.data(), static_cast<std::streamsize>(content.size()));
        out.close();

        init_written_ = true;
        return ok("✅ Wrote " + std::to_string(content.size()) + " characters to initialization.md. "
                  "Do NOT rewrite — call finalize_persona(greeting=..., tagline=...) then call OrchestratorModule.complete_recipe.");
    }

    if (action_name == "finalize_persona") {
        if (persona_.build_complete) {
            return ok("✅ Persona '" + persona_.display_name + "' is already finalized and ready for chat. Now call OrchestratorModule.complete_recipe to finish the recipe.");
        }
        if (!has_active_persona()) {
            return fail("no_active_persona", "❌ Error: No active persona loaded. Use load_persona first.");
        }
        std::error_code ec;
        if (!std::filesystem::is_regular_file(initialization_file(), ec) ||
            std::filesystem::file_size(initialization_file(), ec) < kInitDocMinChars) {
            return fail("init_doc_missing",
                        "❌ Error: Write initialization.md first (at least " +
                        std::to_string(kInitDocMinChars) + " characters) via write_initialization.");
        }
        const std::string greeting = args.value("greeting", "Hello.");
        persona_.greeting = greeting;
        if (args.contains("tagline")) {
            persona_.tagline = args["tagline"].get<std::string>();
        }
        if (args.contains("display_name") && !args["display_name"].get<std::string>().empty()) {
            persona_.display_name = args["display_name"].get<std::string>();
        }
        persona_.build_complete = true;
        save_persona_record();
        return ok("✅ Persona '" + persona_.display_name + "' finalized and ready for chat. Now call OrchestratorModule.complete_recipe to finish the recipe.");
    }

    if (action_name == "update_preferences") {
        if (!has_active_persona()) {
            return fail("no_active_persona", "❌ Error: No active persona loaded. Use load_persona first.");
        }
        const std::string prefs = args.value("preferences", "");
        std::error_code ec;
        std::filesystem::create_directories(persona_dir(), ec);
        std::ofstream out(preferences_file(), std::ios::trunc | std::ios::binary);
        if (!out.is_open()) {
            return fail("write_failed", "❌ Error writing user_preferences.md.");
        }
        out.write(prefs.data(), static_cast<std::streamsize>(prefs.size()));
        out.close();
        return ok("✅ Updated user preferences for '" + persona_.display_name + "'.");
    }

    if (action_name == "chat_as_persona") {
        if (!has_active_persona()) {
            return fail("no_active_persona", "❌ Error: No active persona loaded. Use load_persona first.");
        }
        const std::string user_msg = args.value("user_message", "");
        const std::string ts = now_iso();
        chat_history_.push_back(ChatTurn{"user", user_msg, ts});

        if (args.contains("assistant_reply") && !args["assistant_reply"].get<std::string>().empty()) {
            chat_history_.push_back(ChatTurn{"assistant", args["assistant_reply"].get<std::string>(), ts});
        }

        // Sliding window cap
        while (chat_history_.size() > kMaxChatTurns) {
            chat_history_.erase(chat_history_.begin());
        }
        std::size_t total_chars = 0;
        for (const auto& t : chat_history_) {
            total_chars += t.content.size();
        }
        while (total_chars > kMaxChatChars && chat_history_.size() > 1) {
            total_chars -= chat_history_.front().content.size();
            chat_history_.erase(chat_history_.begin());
        }

        persona_.last_chat_at = ts;
        save_persona_record();
        save_chat_history();
        return ok("✅ Recorded turn in chat history (" + std::to_string(chat_history_.size()) + " turns saved).");
    }

    if (action_name == "get_persona_info") {
        if (!has_active_persona()) {
            return ok(Json::object({{"active", false}}).dump());
        }
        auto j = persona_.to_json();
        j["active"] = true;
        j["chat_turns"] = chat_history_.size();
        return ok(j.dump(2));
    }

    if (action_name == "verify_persona_quality") {
        if (!has_active_persona()) {
            return fail("no_active_persona", "❌ Error: No active persona loaded. Use load_persona first.");
        }

        const bool require_finalized = args.value("require_finalized", true);
        if (require_finalized && !persona_.build_complete) {
            return fail("persona_not_finalized", "❌ Persona build is not finalized. Call PersonaModule.finalize_persona(greeting='...', tagline='...') before completing.");
        }
        if (require_finalized && persona_.greeting.empty()) {
            return fail("missing_greeting", "❌ Persona greeting is empty. Provide an in-character opening greeting via PersonaModule.finalize_persona.");
        }

        const std::size_t min_chars = args.value("min_chars", static_cast<int>(kInitDocMinChars));
        const auto init_path = initialization_file();
        std::error_code ec;
        if (!std::filesystem::is_regular_file(init_path, ec)) {
            return fail("missing_initialization", "❌ Persona initialization file not found: " + init_path.generic_string());
        }

        std::ifstream in(init_path, std::ios::binary);
        if (!in.is_open()) {
            return fail("file_read_error", "❌ Could not open initialization file: " + init_path.generic_string());
        }
        std::stringstream ss;
        ss << in.rdbuf();
        const std::string content = ss.str();

        if (content.size() < min_chars) {
            return fail("shallow_initialization", "❌ initialization.md is only " + std::to_string(content.size()) +
                        " chars (minimum " + std::to_string(min_chars) + " required). Expand backstory, voice, and traits.");
        }

        // Section structure check: lines starting with '#'
        std::size_t heading_count = 0;
        std::istringstream lstream(content);
        std::string line;
        while (std::getline(lstream, line)) {
            const std::size_t first = line.find_first_not_of(" \t\r\n");
            if (first != std::string::npos && line[first] == '#') {
                ++heading_count;
            }
        }
        if (heading_count < 2) {
            return fail("unstructured_initialization", "❌ initialization.md lacks structured sections. Use markdown headings (# Identity, # Voice, # Dialogue, etc.).");
        }

        // Anti-assistant leakage check
        static const std::regex leakage_re(
            R"(\b(as an AI language model|as an AI assistant|I am an artificial intelligence|I am an AI|I do not have personal opinions|I do not have feelings|I cannot fulfill this request)\b)",
            std::regex::icase);
        std::smatch m;
        if (std::regex_search(content, m, leakage_re)) {
            return fail("assistant_leakage_detected", "❌ Persona initialization contains generic AI assistant phrasing ('" + m.str() + "'). Must maintain strict in-character immersion.");
        }

        Json report = Json::object({
            {"verified", true},
            {"persona_id", persona_.id},
            {"display_name", persona_.display_name},
            {"init_chars", content.size()},
            {"headings", heading_count},
            {"build_complete", persona_.build_complete}
        });
        return ok("✅ Persona profile verified successfully (" + std::to_string(content.size()) + " chars, " +
                  std::to_string(heading_count) + " sections for '" + persona_.display_name + "').\n" + report.dump(2));
    }

    return fail("unknown_action", "PersonaModule: unknown action " + action_name);
}

}  // namespace aquila::persona

