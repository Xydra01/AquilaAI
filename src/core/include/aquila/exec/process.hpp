#pragma once

#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::exec {

// Splits a command string into argv without a shell: whitespace separates
// arguments, "double" and 'single' quotes group them, and inside double quotes
// \" and \\ are escapes (other backslashes, e.g. in Windows paths, are literal).
// Throws std::invalid_argument for an unterminated quote or an empty command.
std::vector<std::string> split_command(std::string_view command);

// Environment variable names treated as secrets and removed from children
// (case-insensitive: *TOKEN*, *SECRET*, *PASSWORD*, *PASSWD*, *API_KEY*,
// *APIKEY*, *ACCESS_KEY*, *PRIVATE_KEY*, *CREDENTIAL*).
bool is_secret_env_name(std::string_view name) noexcept;

// Absolute path of `program` found on PATH (and PATHEXT on Windows), or "" if
// not found. A name containing a directory separator is returned as given.
std::filesystem::path find_program(const std::string& program);

struct RunOptions {
    std::vector<std::string> argv;  // argv[0] is resolved with find_program
    std::filesystem::path cwd;
    std::map<std::string, std::string> env;  // added after secrets are removed
    double timeout_s = 120.0;                // whole-run limit; kills the process tree
    std::size_t max_output_bytes = 1 << 20;  // head and tail are kept beyond this
    std::string stdin_data;                  // input piped to child process's stdin (empty => NUL / dev/null)
};

struct RunResult {
    bool started = false;
    std::string error;  // why the process could not start
    int exit_code = -1;
    bool timed_out = false;
    double duration_s = 0.0;
    std::string output;  // stdout and stderr, interleaved as written
    bool truncated = false;
    std::size_t total_bytes = 0;
};

// Runs a program without a shell. Children run in their own Windows Job Object
// or POSIX process group, so a timeout (or the main process exiting) also ends
// any processes it started. .bat/.cmd targets run through cmd.exe and refuse
// arguments containing cmd metacharacters.
RunResult run(const RunOptions& options);

}  // namespace aquila::exec
