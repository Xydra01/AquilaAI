#pragma once

#include "fixtures.hpp"
#include "temp_dir.hpp"

#include <cstdlib>
#include <optional>
#include <string>

namespace aquila::test {

// Applies `patch` to a file holding `old_bytes` with `git apply` (outside any
// repository) and returns the resulting bytes, or nullopt if git refused.
inline std::optional<std::string> git_apply(const std::string& file_name, const std::string& old_bytes,
                                            const std::string& patch, bool new_file = false) {
    TempDir dir;
    if (!new_file) dir.write(file_name, old_bytes);
    dir.write("change.diff", patch);
    const std::string d = dir.path().string();
    // Neutral line-ending config: a user's core.autocrlf would rewrite the output.
    const std::string cmd = "git -c core.autocrlf=false -c core.eol=lf -C \"" + d +
                            "\" apply --whitespace=nowarn change.diff";
    if (std::system(cmd.c_str()) != 0) return std::nullopt;
    return read_bytes(dir.path() / file_name);
}

}  // namespace aquila::test
