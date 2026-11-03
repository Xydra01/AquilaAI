#pragma once

#include "aquila/json.hpp"

#include <string>
#include <string_view>
#include <vector>

namespace aquila {

enum class Role { system, user, assistant, tool };

std::string_view to_string(Role role) noexcept;

// Ollama native /api/chat message: {"role", "content", "images"?}.
// `images` (base64, no data: prefix) is emitted only when non-empty.
struct Message {
    Role role = Role::user;
    std::string content;
    std::vector<std::string> images;

    bool operator==(const Message&) const = default;
};

void to_json(Json& j, const Message& m);
void from_json(const Json& j, Message& m, const std::string& path);

}  // namespace aquila
