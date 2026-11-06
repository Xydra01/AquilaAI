#include "aquila/plugins/script_module.hpp"
#include "aquila/exec/process.hpp"

#include <fstream>
#include <stdexcept>

namespace aquila::plugins {

ScriptModule::ScriptModule(std::filesystem::path plugin_dir)
    : plugin_dir_(std::move(plugin_dir)) {
    load_manifest();
}

void ScriptModule::load_manifest() {
    const auto manifest_file = plugin_dir_ / "manifest.json";
    std::ifstream in(manifest_file, std::ios::binary);
    if (!in.is_open()) {
        throw std::runtime_error("ScriptModule: cannot open manifest at " + manifest_file.generic_string());
    }
    Json j;
    in >> j;
    if (!j.is_object()) {
        throw std::runtime_error("ScriptModule: manifest.json must be a JSON object");
    }
    module_id_ = j.value("module_id", "");
    if (module_id_.empty()) {
        throw std::runtime_error("ScriptModule: manifest missing required 'module_id'");
    }
    description_ = j.value("description", "");

    actions_.clear();
    if (j.contains("actions") && j["actions"].is_array()) {
        for (const auto& a : j["actions"]) {
            if (!a.is_object()) continue;
            ScriptActionDef def;
            def.name = a.value("name", "");
            if (def.name.empty()) continue;
            def.description = a.value("description", "");
            def.parameters_schema = a.value("parameters_json_schema", Json::object({{"type", "object"}}));
            if (a.contains("command") && a["command"].is_array()) {
                for (const auto& cmd : a["command"]) {
                    if (cmd.is_string()) {
                        def.command.push_back(cmd.get<std::string>());
                    }
                }
            }
            def.timeout_s = a.value("timeout_s", 30.0);
            actions_[def.name] = std::move(def);
        }
    }
}

std::vector<ActionSchema> ScriptModule::get_actions() const {
    std::vector<ActionSchema> out;
    out.reserve(actions_.size());
    for (const auto& [name, def] : actions_) {
        out.push_back(ActionSchema{def.name, def.description, def.parameters_schema});
    }
    return out;
}

void ScriptModule::configure(const Json& /*initial_state*/) {}

Json ScriptModule::export_state_snapshot() const {
    return Json::object({
        {"module_id", module_id_},
        {"plugin_dir", plugin_dir_.generic_string()}
    });
}

void ScriptModule::restore_state_snapshot(const Json& /*snapshot*/) {}

ActionResult ScriptModule::run(const std::string& action_name, const Json& args) {
    const auto it = actions_.find(action_name);
    if (it == actions_.end()) {
        return fail("unknown_action", "ScriptModule '" + module_id_ + "': unknown action " + action_name);
    }
    const auto& def = it->second;
    if (def.command.empty()) {
        return fail("invalid_manifest", "ScriptModule action '" + action_name + "' has empty command");
    }

    exec::RunOptions opt;
    opt.argv = def.command;
    opt.cwd = plugin_dir_;
    opt.stdin_data = args.dump() + "\n";
    opt.timeout_s = def.timeout_s;
    opt.max_output_bytes = 1 << 20;

    const auto res = exec::run(opt);
    if (!res.started) {
        return fail("plugin_spawn_error", "Failed to start plugin executable: " + res.error);
    }
    if (res.timed_out) {
        return fail("plugin_timeout", "Plugin action '" + action_name + "' timed out after " +
                                           std::to_string(def.timeout_s) + "s");
    }
    if (res.exit_code != 0) {
        return fail("plugin_error", "Plugin exited with code " + std::to_string(res.exit_code) +
                                        ": " + res.output);
    }

    std::string text = res.output;
    while (!text.empty() && (text.back() == '\r' || text.back() == '\n')) {
        text.pop_back();
    }
    return ok(text);
}

}  // namespace aquila::plugins

