#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::exec {

struct Diagnostic {
    std::string tool;      // msvc, clang, cmake, pytest, python
    std::string file;
    std::size_t line = 0;  // 0 = no location
    std::size_t col = 0;
    std::string severity;  // error, warning, failure
    std::string code;      // C2065, LNK2019, -Wunused, FileNotFoundError, ...
    std::string message;
    std::size_t count = 1;               // identical diagnostics folded into this one
    std::vector<std::string> context;    // following note / caret lines (capped)
};

struct TestCounts {
    bool found = false;
    std::size_t passed = 0, failed = 0, errors = 0, skipped = 0, xfailed = 0, xpassed = 0;
};

struct Diagnosis {
    std::vector<Diagnostic> blocks;  // deduplicated; errors, then failures, then warnings
    std::size_t errors = 0;          // before deduplication
    std::size_t warnings = 0;
    std::vector<std::string> failed_targets;  // ninja "FAILED:" lines
    TestCounts tests;                         // pytest summary
};

// Parses MSVC, clang/gcc, CMake, ninja, pytest and Python traceback output.
// Diagnostics with the same file, line, code and message (quoted names and
// template arguments ignored) are folded into one block with a count.
Diagnosis diagnose(std::string_view log);

// Compact text for the LLM: a summary line, at most `max_blocks` blocks,
// failed targets and test counts, capped at `max_chars`.
std::string render(const Diagnosis& d, std::size_t max_blocks = 5, std::size_t max_chars = 4500);

}  // namespace aquila::exec
