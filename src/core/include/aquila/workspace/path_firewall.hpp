#pragma once

#include <filesystem>
#include <stdexcept>
#include <string>
#include <string_view>

namespace aquila {

enum class Access { read, write };

// UTF-8 <-> filesystem path (std::string paths would use the ANSI code page on Windows).
std::filesystem::path path_from_utf8(std::string_view utf8);
std::string path_to_utf8(const std::filesystem::path& p);

// Thrown when a path is refused. code(): path_invalid, path_outside_root, path_blocked.
class PathDenied : public std::runtime_error {
public:
    PathDenied(std::string code, const std::string& detail)
        : std::runtime_error(detail), code_(std::move(code)) {}
    [[nodiscard]] const std::string& code() const noexcept { return code_; }

private:
    std::string code_;
};

struct ResolvedPath {
    std::filesystem::path absolute;  // symlinks/junctions resolved where the path exists
    std::string relative;            // '/'-separated, relative to the root
};

// Confines every path to one workspace root (Python's is_safe_path only checked
// names; containment is checked here, after resolving links).
//   - relative paths resolve under the root; absolute ones must already be inside it
//   - '..' escapes, drive-relative (C:foo), device (\\?\) and outside-root UNC paths are refused
//   - containment is case-insensitive on Windows
//   - always blocked: .env*, *.pem, *.key, *.p12, *.pfx, id_rsa*, id_ed25519*, *.db,
//     *.sqlite, *.sqlite3, and anything under .git/
//   - write-blocked: generated/IDE dirs (build, dist, node_modules, venv, .venv,
//     __pycache__, tool caches, *.egg-info, .idea, .vscode, .cursor)
class PathFirewall {
public:
    // Throws std::invalid_argument if `root` is not an existing directory.
    explicit PathFirewall(const std::filesystem::path& root);

    [[nodiscard]] const std::filesystem::path& root() const noexcept { return root_; }
    [[nodiscard]] ResolvedPath resolve(std::string_view input, Access access) const;

    // True for directories the outline skips (the write-blocked generated dirs).
    [[nodiscard]] static bool is_generated_dir(std::string_view name) noexcept;

private:
    std::filesystem::path root_;
};

}  // namespace aquila
