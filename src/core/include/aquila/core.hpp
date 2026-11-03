#pragma once

#include <string>
#include <string_view>

namespace aquila {

std::string_view version() noexcept;

// Each probe exercises one third-party dependency so a link or ABI problem
// shows up in M0 instead of in the milestone that first needs the library.
namespace deps_probe {

// nlohmann/json: parses `json_text` and returns the integer at `key`.
int json_int(std::string_view json_text, const std::string& key);

// inja (+ nlohmann/json): renders `tmpl` with `data_json` as the context.
std::string inja_render(std::string_view tmpl, std::string_view data_json);

// fmt: "<n> tokens", with n right-aligned to width 6.
std::string fmt_tokens(long long n);

// spdlog: logs one info line through an ostringstream sink and returns it.
std::string spdlog_line(std::string_view message);

// cpp-httplib: reason phrase for an HTTP status code.
std::string http_reason(int status);

// cpp-httplib: constructs (does not start) a server and reports validity.
bool http_server_constructs();

}  // namespace deps_probe
}  // namespace aquila
