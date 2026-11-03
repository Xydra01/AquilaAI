#include "aquila/workspace/path_firewall.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cwctype>
#include <system_error>

namespace aquila {

namespace fs = std::filesystem;

namespace {

std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

bool ends_with(std::string_view s, std::string_view suffix) {
    return s.size() >= suffix.size() && s.substr(s.size() - suffix.size()) == suffix;
}

bool starts_with(std::string_view s, std::string_view prefix) {
    return s.substr(0, prefix.size()) == prefix;
}

bool same_component(const fs::path& a, const fs::path& b) {
#ifdef _WIN32
    const auto& x = a.native();
    const auto& y = b.native();
    return x.size() == y.size() && std::equal(x.begin(), x.end(), y.begin(), [](wchar_t c, wchar_t d) {
               return std::towlower(c) == std::towlower(d);
           });
#else
    return a == b;
#endif
}

// `child` lies at or under `root` (both absolute and normalized).
bool within(const fs::path& child, const fs::path& root) {
    auto c = child.begin();
    for (auto r = root.begin(); r != root.end(); ++r, ++c) {
        if (r->empty()) continue;  // trailing separator
        if (c == child.end() || !same_component(*c, *r)) return false;
    }
    return true;
}

fs::path rest_after(const fs::path& child, const fs::path& root) {
    auto c = child.begin();
    for (auto r = root.begin(); r != root.end(); ++r) {
        if (!r->empty()) ++c;
    }
    fs::path out;
    for (; c != child.end(); ++c) {
        if (!c->empty()) out /= *c;
    }
    return out;
}

bool always_blocked(const std::string& name) {
    const auto n = lower(name);
    if (n == ".env" || starts_with(n, ".env.") || n == ".git") return true;
    if (starts_with(n, "id_rsa") || starts_with(n, "id_ed25519")) return true;
    for (const auto* ext : {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"}) {
        if (ends_with(n, ext)) return true;
    }
    return false;
}

}  // namespace

fs::path path_from_utf8(std::string_view utf8) {
    return fs::path(std::u8string(utf8.begin(), utf8.end()));
}

std::string path_to_utf8(const fs::path& p) {
    const auto u = p.generic_u8string();
    return std::string(u.begin(), u.end());
}

bool PathFirewall::is_generated_dir(std::string_view name) noexcept {
    static constexpr std::array<std::string_view, 17> kDirs = {
        "build", "dist", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".tox", ".nox", ".eggs", "htmlcov", "site-packages", ".idea", ".vscode", ".cursor"};
    std::string n(name);
    std::transform(n.begin(), n.end(), n.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return std::find(kDirs.begin(), kDirs.end(), n) != kDirs.end() || ends_with(n, ".egg-info");
}

PathFirewall::PathFirewall(const fs::path& root) {
    std::error_code ec;
    if (!fs::is_directory(root, ec)) throw std::invalid_argument("workspace root is not a directory: " + path_to_utf8(root));
    root_ = fs::canonical(root);
}

ResolvedPath PathFirewall::resolve(std::string_view input, Access access) const {
    if (input.empty()) throw PathDenied("path_invalid", "empty path");
    if (input.find('\0') != std::string_view::npos) throw PathDenied("path_invalid", "path contains NUL");

    std::string text(input);
    std::replace(text.begin(), text.end(), '\\', '/');
    if (starts_with(text, "//?/") || starts_with(text, "//./")) {
        throw PathDenied("path_invalid", "device paths are not allowed: " + std::string(input));
    }
    if (text.size() >= 2 && std::isalpha(static_cast<unsigned char>(text[0])) && text[1] == ':' &&
        (text.size() == 2 || text[2] != '/')) {
        throw PathDenied("path_invalid", "drive-relative paths are not allowed: " + std::string(input));
    }

    const fs::path given = path_from_utf8(text).make_preferred();
    const bool absolute = given.is_absolute() || given.has_root_name() || given.has_root_directory();
    const fs::path lexical = (absolute ? given : root_ / given).lexically_normal();
    if (!within(lexical, root_)) throw PathDenied("path_outside_root", "path is outside the workspace: " + std::string(input));

    std::error_code ec;
    const fs::path resolved = fs::weakly_canonical(lexical, ec);
    if (ec) throw PathDenied("path_invalid", "cannot resolve '" + std::string(input) + "': " + ec.message());
    if (!within(resolved, root_)) {
        throw PathDenied("path_outside_root", "path leaves the workspace through a link: " + std::string(input));
    }

    const fs::path rel = rest_after(resolved, root_);
    const std::string rel_text = path_to_utf8(rel);
    for (const auto& part : rel) {
        if (always_blocked(path_to_utf8(part))) throw PathDenied("path_blocked", "access to '" + rel_text + "' is blocked");
    }
    if (access == Access::write) {
        // The last component is the file itself; only its parent directories count.
        auto last = rel.end();
        if (last != rel.begin()) --last;
        for (auto it = rel.begin(); it != last; ++it) {
            const auto name = path_to_utf8(*it);
            if (is_generated_dir(name)) {
                throw PathDenied("path_blocked", "writing under '" + name + "/' is blocked: " + rel_text);
            }
        }
    }
    return {resolved, rel_text};
}

}  // namespace aquila
