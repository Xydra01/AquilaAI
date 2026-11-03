#include "aquila/types/tool_interaction.hpp"

namespace aquila {

using namespace json_io;

void to_json(Json& j, const ToolInteraction& v) {
    j = Json::object();
    j["id"] = v.id;
    j["module"] = v.module;
    j["action"] = v.action;
    j["args"] = v.args;
    Json result;
    to_json(result, v.result);
    j["result"] = std::move(result);
}

void from_json(const Json& j, ToolInteraction& v, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"id", "module", "action", "args", "result"});
    v.id = read_string(require(j, path, "id"), child_path(path, "id"));
    v.module = read_string(require(j, path, "module"), child_path(path, "module"));
    v.action = read_string(require(j, path, "action"), child_path(path, "action"));
    v.args = read_object(require(j, path, "args"), child_path(path, "args"));
    from_json(require(j, path, "result"), v.result, child_path(path, "result"));
}

}  // namespace aquila
