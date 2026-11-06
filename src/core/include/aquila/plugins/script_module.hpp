#pragma once

#include "aquila/modules/module.hpp"

#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace aquila::plugins {

struct ScriptActionDef {
    std::string name;
    std::string description;
    Json parameters_schema;
    std::vector<std::string> command;
    double timeout_s = 30.0;
};

// ScriptModule (D5 Plugin Architecture over manifest.json):
// Dynamic adapter implementing IAgentModule over any external script/binary.
// Communicates by piping JSON arguments over stdin and reading stdout.
class ScriptModule final : public ModuleBase {
public:
    explicit ScriptModule(std::filesystem::path plugin_dir);

    [[nodiscard]] std::string module_id() const override { return module_id_; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    [[nodiscard]] const std::filesystem::path& plugin_dir() const noexcept { return plugin_dir_; }

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    void load_manifest();

    std::filesystem::path plugin_dir_;
    std::string module_id_;
    std::string description_;
    std::map<std::string, ScriptActionDef> actions_;
};

}  // namespace aquila::plugins

