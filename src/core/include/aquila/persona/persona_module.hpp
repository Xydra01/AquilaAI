#pragma once

#include "aquila/modules/module.hpp"

#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::persona {

inline constexpr std::size_t kInitDocMinChars = 800;
inline constexpr std::size_t kMaxChatTurns = 40;
inline constexpr std::size_t kMaxChatChars = 120'000;

struct Persona {
    std::string id;
    std::string display_name = "Character";
    std::string tagline;
    std::string description;
    std::string greeting = "Hello.";
    std::string avatar_relpath;
    std::string created_at;
    std::string last_chat_at;
    bool build_complete = false;

    [[nodiscard]] Json to_json() const;
    static Persona from_json(const Json& j);
};

struct ChatTurn {
    std::string role;  // "user" or "assistant"
    std::string content;
    std::string timestamp;

    [[nodiscard]] Json to_json() const;
    static ChatTurn from_json(const Json& j);
};

// PersonaModule (Character AI domain, 5.2):
// Owns persona bibles, character initialization, user preferences, and rolling chat history.
class PersonaModule final : public ModuleBase {
public:
    PersonaModule();
    explicit PersonaModule(ModuleContext ctx);

    [[nodiscard]] std::string module_id() const override { return "PersonaModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    // Direct accessors for tests & embedding
    [[nodiscard]] bool has_active_persona() const noexcept { return !active_persona_id_.empty(); }
    [[nodiscard]] const Persona& persona() const noexcept { return persona_; }
    [[nodiscard]] const std::string& instance_id() const noexcept { return instance_id_; }
    [[nodiscard]] std::filesystem::path persona_dir() const;
    [[nodiscard]] std::filesystem::path initialization_file() const;
    [[nodiscard]] std::filesystem::path preferences_file() const;
    [[nodiscard]] std::filesystem::path chat_history_file() const;

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    void save_persona_record();
    bool load_persona_record(const std::string& persona_id, const std::string& instance_id);
    void save_chat_history();
    void load_chat_history();

    ModuleContext ctx_;
    std::string instance_id_ = "default";
    std::string active_persona_id_;
    Persona persona_;
    bool init_written_ = false;
    std::vector<ChatTurn> chat_history_;
};

}  // namespace aquila::persona

