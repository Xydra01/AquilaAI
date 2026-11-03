#include "aquila/inference/ollama_backend.hpp"

#include "aquila/inference/ollama_wire.hpp"

#include <httplib.h>

#include <algorithm>
#include <cstdlib>
#include <stdexcept>

namespace aquila {

namespace {

constexpr std::size_t kErrorBodyCap = 400;

struct HttpTarget {
    std::string host;
    int port = 80;
    std::string prefix;  // path prefix without trailing '/'
};

std::optional<std::string> env(const char* name) {
    const char* v = std::getenv(name);
    if (v == nullptr) return std::nullopt;
    std::string s(v);
    const auto b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return std::nullopt;
    const auto e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

// Accepts http://host[:port][/prefix]. TLS is not built in (M0), so https is rejected.
std::optional<HttpTarget> parse_http_url(const std::string& url, std::string& why) {
    constexpr std::string_view scheme = "http://";
    if (url.rfind(scheme, 0) != 0) {
        why = "only http:// URLs are supported, got '" + url + "'";
        return std::nullopt;
    }
    const auto rest = url.substr(scheme.size());
    const auto slash = rest.find('/');
    const auto authority = rest.substr(0, slash);
    HttpTarget t;
    if (slash != std::string::npos) t.prefix = rest.substr(slash);
    while (!t.prefix.empty() && t.prefix.back() == '/') t.prefix.pop_back();

    std::size_t port_sep = std::string::npos;
    if (!authority.empty() && authority.front() == '[') {
        const auto close = authority.find(']');
        if (close == std::string::npos) {
            why = "malformed IPv6 host in '" + url + "'";
            return std::nullopt;
        }
        t.host = authority.substr(1, close - 1);
        if (close + 1 < authority.size() && authority[close + 1] == ':') port_sep = close + 1;
    } else {
        port_sep = authority.rfind(':');
        t.host = authority.substr(0, port_sep);
    }
    if (port_sep != std::string::npos) {
        const auto port_text = authority.substr(port_sep + 1);
        char* end = nullptr;
        const long port = std::strtol(port_text.c_str(), &end, 10);
        if (port_text.empty() || *end != '\0' || port <= 0 || port > 65535) {
            why = "bad port in '" + url + "'";
            return std::nullopt;
        }
        t.port = static_cast<int>(port);
    }
    if (t.host.empty()) {
        why = "missing host in '" + url + "'";
        return std::nullopt;
    }
    return t;
}

void set_timeouts(httplib::Client& cli, double connect_s, double read_s) {
    const auto as_ms = [](double s) { return std::chrono::milliseconds(static_cast<long long>(s * 1000.0)); };
    cli.set_connection_timeout(as_ms(connect_s));
    cli.set_read_timeout(as_ms(read_s));
    cli.set_write_timeout(as_ms(read_s));
}

GenerationResult failure(std::string code, std::string detail) {
    GenerationResult r;
    r.error_code = std::move(code);
    r.error_detail = std::move(detail);
    return r;
}

GenerationResult transport_failure(httplib::Error err, bool stream_started) {
    const auto detail = httplib::to_string(err);
    switch (err) {
        case httplib::Error::Connection:
        case httplib::Error::ConnectionTimeout:
            return failure("unreachable", detail);
        case httplib::Error::Timeout:
        case httplib::Error::Read:
            return failure(stream_started ? "stream_stalled" : "timeout", detail);
        case httplib::Error::Canceled:
            return failure("cancelled", detail);
        default:
            return failure("transport_error", detail);
    }
}

GenerationResult http_failure(int status, const std::string& body) {
    std::string detail = "HTTP " + std::to_string(status);
    if (!body.empty()) detail += ": " + body.substr(0, kErrorBodyCap);
    return failure("http_error", detail);
}

}  // namespace

OllamaConfig OllamaConfig::from_env() {
    OllamaConfig c;
    if (auto v = env("OLLAMA_BASE_URL")) c.base_url = *v;
    if (auto v = env("OLLAMA_MODEL")) c.model = *v;
    if (auto v = env("OLLAMA_NUM_CTX")) {
        char* end = nullptr;
        const long n = std::strtol(v->c_str(), &end, 10);
        if (*end == '\0' && n > 0) c.num_ctx = static_cast<std::uint32_t>(n);
    }
    if (auto v = env("OLLAMA_KEEP_ALIVE")) c.keep_alive = *v;
    return c;
}

OllamaHttpBackend::OllamaHttpBackend(OllamaConfig config) : config_(std::move(config)) {}

void OllamaHttpBackend::append(const Message& message) {
    messages_.push_back(message);
}

std::size_t OllamaHttpBackend::mark_checkpoint() const {
    return messages_.size();
}

void OllamaHttpBackend::rollback_to(std::size_t checkpoint) {
    if (checkpoint > messages_.size()) {
        throw std::out_of_range("rollback_to(" + std::to_string(checkpoint) + ") past context end " +
                                std::to_string(messages_.size()));
    }
    messages_.resize(checkpoint);
}

ComputeProfile OllamaHttpBackend::active_profile() const noexcept {
    return config_.profile;
}

std::optional<std::string> OllamaHttpBackend::probe(double timeout_s) const {
    std::string why;
    const auto target = parse_http_url(config_.base_url, why);
    if (!target) return std::nullopt;
    httplib::Client cli(target->host, target->port);
    set_timeouts(cli, timeout_s, timeout_s);
    const auto res = cli.Get(target->prefix + "/api/version");
    if (!res || res->status != 200) return std::nullopt;
    try {
        const auto doc = json_io::parse_text(res->body);
        if (doc.is_object() && doc.contains("version") && doc["version"].is_string()) {
            return doc["version"].get<std::string>();
        }
    } catch (const SchemaError&) {
    }
    return std::nullopt;
}

GenerationResult OllamaHttpBackend::generate(const GenerationParams& in, const TokenCallback& on_token) {
    std::string why;
    const auto target = parse_http_url(config_.base_url, why);
    if (!target) return failure("unsupported_url", why);

    GenerationParams params = in;
    if (!params.num_ctx) params.num_ctx = config_.num_ctx;
    if (!params.keep_alive) params.keep_alive = config_.keep_alive;

    const bool stream = static_cast<bool>(on_token);
    std::string body;
    try {
        body = ollama::build_chat_payload(config_.model, messages_, params, stream)
                   .dump(-1, ' ', false, Json::error_handler_t::strict);
    } catch (const Json::type_error& e) {
        return failure("invalid_request", e.what());
    }

    httplib::Client cli(target->host, target->port);
    set_timeouts(cli, config_.connect_timeout_s, params.timeout_s);
    const auto path = target->prefix + "/api/chat";

    if (!stream) {
        const auto res = cli.Post(path, body, "application/json");
        if (!res) return transport_failure(res.error(), false);
        if (res->status != 200) return http_failure(res->status, res->body);
        return ollama::parse_chat_response(res->body);
    }

    GenerationResult result;
    int status = 0;
    bool started = false;
    bool done = false;
    std::string pending;     // bytes after the last newline
    std::string error_body;  // body of a non-200 response

    httplib::Request req;
    req.method = "POST";
    req.path = path;
    req.body = body;
    req.set_header("Content-Type", "application/json");
    req.response_handler = [&](const httplib::Response& r) {
        status = r.status;
        return true;
    };
    req.content_receiver = [&](const char* data, std::size_t len, std::size_t, std::size_t) {
        started = true;
        if (status != 200) {
            error_body.append(data, std::min(len, kErrorBodyCap - std::min(kErrorBodyCap, error_body.size())));
            return true;
        }
        pending.append(data, len);
        std::size_t nl = 0;
        while ((nl = pending.find('\n')) != std::string::npos) {
            const std::string line = pending.substr(0, nl);
            pending.erase(0, nl + 1);
            std::optional<ollama::StreamChunk> chunk;
            try {
                chunk = ollama::parse_stream_line(line);
            } catch (const SchemaError& e) {
                result.error_code = "bad_response";
                result.error_detail = e.what();
                return false;
            }
            if (!chunk) continue;
            if (!chunk->error.empty()) {
                result.error_code = "server_error";
                result.error_detail = chunk->error;
                return false;
            }
            if (!chunk->content.empty() || !chunk->thinking.empty()) {
                result.content += chunk->content;
                result.thinking += chunk->thinking;
                if (!on_token(chunk->content, chunk->thinking)) {
                    result.error_code = "cancelled";
                    result.error_detail = "stopped by token callback";
                    return false;
                }
            }
            if (chunk->done) {
                done = true;
                result.done_reason = chunk->done_reason;
                result.prompt_tokens = chunk->prompt_tokens;
                result.completion_tokens = chunk->completion_tokens;
            }
        }
        return true;
    };

    const auto res = cli.send(req);
    if (!result.error_code.empty()) return result;  // set by the receiver (keeps partial output)
    if (!res) {
        auto f = transport_failure(res.error(), started);
        f.content = std::move(result.content);
        f.thinking = std::move(result.thinking);
        return f;
    }
    if (status != 200) return http_failure(status, error_body);
    if (!pending.empty()) {
        try {
            if (const auto chunk = ollama::parse_stream_line(pending); chunk && chunk->done) {
                done = true;
                result.content += chunk->content;
                result.thinking += chunk->thinking;
                result.done_reason = chunk->done_reason;
                result.prompt_tokens = chunk->prompt_tokens;
                result.completion_tokens = chunk->completion_tokens;
            }
        } catch (const SchemaError&) {
        }
    }
    if (!done) {
        result.error_code = "stream_truncated";
        result.error_detail = "stream ended without a done marker";
        return result;
    }
    result.ok = true;
    return result;
}

}  // namespace aquila
