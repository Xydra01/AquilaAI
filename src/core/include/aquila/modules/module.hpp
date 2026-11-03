#pragma once

#include "aquila/json.hpp"
#include "aquila/types/action.hpp"

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

namespace aquila {

struct ModuleContext {
    std::filesystem::path workspace_root;  // every path a module touches stays under it
    std::size_t max_output_chars = 4500;    // R16 GPU-tier default; M4 sets it per tier
};

// A coarse-grained, stateful module (R9-R10).
class IAgentModule {
public:
    virtual ~IAgentModule() = default;

    [[nodiscard]] virtual std::string module_id() const = 0;
    [[nodiscard]] virtual std::vector<ActionSchema> get_actions() const = 0;

    // Applies a recipe's initial_state. Throws SchemaError (path relative to
    // initial_state) for unknown keys or bad values.
    virtual void configure(const Json& initial_state) = 0;

    // Never throws for bad LLM input: unknown actions and invalid args come back
    // as failed ActionResults (unknown_action, invalid_args).
    virtual ActionResult execute_action(const std::string& action_name, const Json& args) = 0;

    [[nodiscard]] virtual Json export_state_snapshot() const = 0;
    // Throws SchemaError for a malformed snapshot.
    virtual void restore_state_snapshot(const Json& snapshot) = 0;
};

// Shared plumbing: argument validation against get_actions() and result helpers.
class ModuleBase : public IAgentModule {
public:
    ActionResult execute_action(const std::string& action_name, const Json& args) final;

protected:
    // Called with args already validated against the action's schema.
    virtual ActionResult run(const std::string& action_name, const Json& args) = 0;

    [[nodiscard]] static ActionResult ok(std::string text);
    [[nodiscard]] static ActionResult fail(std::string code, std::string text);
};

// ceil(chars / 4): the design doc's fast estimate (D:L190-192).
std::uint64_t estimate_tokens(std::string_view text) noexcept;

}  // namespace aquila
