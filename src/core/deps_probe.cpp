#include "aquila/core.hpp"

#include <fmt/format.h>
#include <httplib.h>
#include <inja/inja.hpp>
#include <nlohmann/json.hpp>
#include <spdlog/sinks/ostream_sink.h>
#include <spdlog/spdlog.h>

#include <memory>
#include <sstream>

namespace aquila::deps_probe {

int json_int(std::string_view json_text, const std::string& key) {
    const auto doc = nlohmann::json::parse(json_text);
    return doc.at(key).get<int>();
}

std::string inja_render(std::string_view tmpl, std::string_view data_json) {
    inja::Environment env;
    return env.render(tmpl, nlohmann::json::parse(data_json));
}

std::string fmt_tokens(long long n) {
    return fmt::format("{:>6} tokens", n);
}

std::string spdlog_line(std::string_view message) {
    std::ostringstream out;
    auto sink = std::make_shared<spdlog::sinks::ostream_sink_st>(out);
    spdlog::logger logger("probe", sink);
    logger.set_pattern("[%l] %v");
    logger.info("{}", message);
    logger.flush();
    return out.str();
}

std::string http_reason(int status) {
    return httplib::status_message(status);
}

bool http_server_constructs() {
    httplib::Server server;
    return server.is_valid();
}

}  // namespace aquila::deps_probe
