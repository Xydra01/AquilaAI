#pragma once

#include <optional>
#include <string>
#include <string_view>

namespace aquila::diff {

// Unified diff (git/GNU format) of two texts, line by line (Myers' algorithm).
// Lines are split on '\n'; any '\r' stays part of the line, so CRLF files diff
// in their on-disk form. Missing final newlines get "\ No newline at end of file".
// An empty `old_text` with old_label "/dev/null" describes a new file.
// Returns "" when the texts are equal.
std::string unified(std::string_view old_text, std::string_view new_text, std::string_view old_label,
                    std::string_view new_label, int context = 3);

// Applies a unified diff to `text`. Hunks must match their context and removed
// lines exactly; later hunks are shifted by the line delta of earlier ones.
// Returns nullopt and sets `error` on any mismatch.
std::optional<std::string> apply(std::string_view text, std::string_view patch, std::string& error);

}  // namespace aquila::diff
