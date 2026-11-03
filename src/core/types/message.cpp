#include "aquila/types/message.hpp"

namespace aquila {

using namespace json_io;

std::string_view to_string(Role role) noexcept {
    switch (role) {
        case Role::system: return "system";
        case Role::user: return "user";
        case Role::assistant: return "assistant";
        case Role::tool: return "tool";
    }
    return "user";
}

namespace {

Role read_role(const Json& value, const std::string& path) {
    const auto text = read_string(value, path);
    for (const Role r : {Role::system, Role::user, Role::assistant, Role::tool}) {
        if (text == to_string(r)) return r;
    }
    throw SchemaError(path, "unknown role '" + text + "' (expected system|user|assistant|tool)");
}

}  // namespace

void to_json(Json& j, const Message& m) {
    j = Json::object();
    j["role"] = to_string(m.role);
    j["content"] = m.content;
    if (!m.images.empty()) {
        j["images"] = m.images;
    }
}

void from_json(const Json& j, Message& m, const std::string& path) {
    expect_object(j, path);
    reject_unknown(j, path, {"role", "content", "images"});
    m.role = read_role(require(j, path, "role"), child_path(path, "role"));
    m.content = read_string(require(j, path, "content"), child_path(path, "content"));
    m.images.clear();
    if (const auto it = j.find("images"); it != j.end()) {
        m.images = read_string_array(*it, child_path(path, "images"));
    }
}

}  // namespace aquila
