#include "aquila/exec/process.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>

namespace aquila::exec {

std::vector<std::string> split_command(std::string_view cmd) {
    std::vector<std::string> out;
    std::string cur;
    bool in_token = false;
    char quote = 0;
    for (std::size_t i = 0; i < cmd.size(); ++i) {
        const char c = cmd[i];
        if (quote == '\'') {
            if (c == '\'') quote = 0;
            else cur += c;
            continue;
        }
        if (quote == '"') {
            if (c == '\\' && i + 1 < cmd.size() && (cmd[i + 1] == '"' || cmd[i + 1] == '\\')) {
                cur += cmd[++i];
            } else if (c == '"') {
                quote = 0;
            } else {
                cur += c;
            }
            continue;
        }
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
            if (in_token) {
                out.push_back(std::move(cur));
                cur.clear();
                in_token = false;
            }
            continue;
        }
        in_token = true;
        if (c == '"' || c == '\'') quote = c;
        else cur += c;
    }
    if (quote != 0) throw std::invalid_argument("unterminated quote in command: " + std::string(cmd));
    if (in_token) out.push_back(std::move(cur));
    if (out.empty()) throw std::invalid_argument("empty command");
    return out;
}

bool is_secret_env_name(std::string_view name) noexcept {
    std::string n(name);
    std::transform(n.begin(), n.end(), n.begin(), [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    for (const auto* marker : {"TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "ACCESS_KEY",
                               "PRIVATE_KEY", "CREDENTIAL"}) {
        if (n.find(marker) != std::string::npos) return true;
    }
    return false;
}

}  // namespace aquila::exec
