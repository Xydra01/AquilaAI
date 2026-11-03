#include "aquila/types/action.hpp"

namespace aquila {

using namespace json_io;

void to_json(Json& j, const ActionCall& v) {
    j = Json::object();
    j["thought"] = v.thought;
    j["module"] = v.module;
    j["action"] = v.action;
    j["args"] = v.args;
}

void from_json(const Json& j, ActionCall& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"thought", "module", "action", "args"});
    v.thought = read_string(require(j, path, "thought"), child_path(path, "thought"));
    v.module = read_string(require(j, path, "module"), child_path(path, "module"));
    v.action = read_string(require(j, path, "action"), child_path(path, "action"));
    v.args = read_object(require(j, path, "args"), child_path(path, "args"));
}

void to_json(Json& j, const ActionSchema& v) {
    j = Json::object();
    j["action_name"] = v.action_name;
    j["description"] = v.description;
    j["parameters_json_schema"] = v.parameters_json_schema;
}

void from_json(const Json& j, ActionSchema& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"action_name", "description", "parameters_json_schema"});
    v.action_name = read_string(require(j, path, "action_name"), child_path(path, "action_name"));
    v.description = read_string(require(j, path, "description"), child_path(path, "description"));
    v.parameters_json_schema = read_object(require(j, path, "parameters_json_schema"),
                                           child_path(path, "parameters_json_schema"));
}

bool is_valid_error_code(std::string_view code) noexcept {
    if (code.empty() || code.front() < 'a' || code.front() > 'z') return false;
    for (const char c : code) {
        const bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_';
        if (!ok) return false;
    }
    return true;
}

void to_json(Json& j, const ActionResult& v) {
    j = Json::object();
    j["success"] = v.success;
    j["error_code"] = v.error_code;
    j["llm_facing_output"] = v.llm_facing_output;
    j["token_estimate"] = v.token_estimate;
}

void from_json(const Json& j, ActionResult& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"success", "error_code", "llm_facing_output", "token_estimate"});
    v.success = read_bool(require(j, path, "success"), child_path(path, "success"));

    const auto code_path = child_path(path, "error_code");
    v.error_code = read_string(require(j, path, "error_code"), code_path);
    if (v.success && !v.error_code.empty()) {
        throw SchemaError(code_path, "must be empty when success is true");
    }
    if (!v.success && v.error_code.empty()) {
        throw SchemaError(code_path, "must be set when success is false");
    }
    if (!v.success && !is_valid_error_code(v.error_code)) {
        throw SchemaError(code_path, "must be snake_case ([a-z][a-z0-9_]*), got '" + v.error_code + "'");
    }

    v.llm_facing_output =
        read_string(require(j, path, "llm_facing_output"), child_path(path, "llm_facing_output"));
    v.token_estimate = read_u64(require(j, path, "token_estimate"), child_path(path, "token_estimate"));
}

}  // namespace aquila
