#include "aquila/knowledge/web_fetcher.hpp"

#include <httplib.h>

#include <algorithm>
#include <cctype>
#include <sstream>

namespace aquila::knowledge {

namespace {

struct ParsedUrl {
    std::string scheme;
    std::string host;
    int port{80};
    std::string path;
    std::string host_port;
};

ParsedUrl parse_url(std::string_view url) {
    ParsedUrl out;
    auto scheme_end = url.find("://");
    if (scheme_end == std::string_view::npos) {
        throw FetchError("Invalid URL, missing scheme: " + std::string(url));
    }

    out.scheme = std::string(url.substr(0, scheme_end));
    for (char& c : out.scheme) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }

    if (out.scheme != "http" && out.scheme != "https") {
        throw FetchError("Unsupported URL scheme: " + out.scheme);
    }

    out.port = (out.scheme == "https") ? 443 : 80;

    auto rest = url.substr(scheme_end + 3);
    auto slash = rest.find('/');
    if (slash == std::string_view::npos) {
        out.host_port = std::string(rest);
        out.path = "/";
    } else {
        out.host_port = std::string(rest.substr(0, slash));
        out.path = std::string(rest.substr(slash));
    }

    auto colon = out.host_port.find(':');
    if (colon != std::string::npos) {
        out.host = out.host_port.substr(0, colon);
        try {
            out.port = std::stoi(out.host_port.substr(colon + 1));
        } catch (...) {
            throw FetchError("Invalid port in URL: " + std::string(url));
        }
    } else {
        out.host = out.host_port;
    }

    return out;
}

std::string resolve_redirect(const ParsedUrl& current, std::string_view location) {
    if (location.starts_with("http://") || location.starts_with("https://")) {
        return std::string(location);
    }
    if (location.starts_with("/")) {
        return current.scheme + "://" + current.host_port + std::string(location);
    }
    // Relative to directory
    auto last_slash = current.path.rfind('/');
    std::string dir = (last_slash == std::string::npos) ? "/" : current.path.substr(0, last_slash + 1);
    return current.scheme + "://" + current.host_port + dir + std::string(location);
}

bool is_supported_content_type(std::string_view ct) {
    if (ct.empty()) {
        return true; // permissive if server omitted Content-Type
    }
    std::string lower;
    lower.reserve(ct.size());
    for (char c : ct) {
        lower.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    auto semi = lower.find(';');
    if (semi != std::string::npos) {
        lower = lower.substr(0, semi);
    }
    while (!lower.empty() && std::isspace(static_cast<unsigned char>(lower.front()))) {
        lower.erase(lower.begin());
    }
    while (!lower.empty() && std::isspace(static_cast<unsigned char>(lower.back()))) {
        lower.pop_back();
    }
    return lower.starts_with("text/") || lower == "application/xhtml+xml";
}

} // namespace

WebFetcher::WebFetcher(FetchOptions options) : options_(std::move(options)) {}

void WebFetcher::set_mock_handler(MockHandler handler) {
    mock_handler_ = std::move(handler);
}

FetchResponse WebFetcher::fetch(std::string_view url) const {
    std::string current_url = std::string(url);
    int redirects_remaining = options_.max_redirects;

    while (true) {
        if (mock_handler_) {
            auto mocked = mock_handler_(current_url);
            if (mocked) {
                if (mocked->status_code < 200 || mocked->status_code >= 300) {
                    throw FetchError("HTTP " + std::to_string(mocked->status_code) + " error fetching " + current_url,
                                     mocked->status_code);
                }
                if (!is_supported_content_type(mocked->content_type)) {
                    throw FetchError("Unsupported Content-Type: " + mocked->content_type, mocked->status_code);
                }
                if (mocked->body.size() > options_.max_body_bytes) {
                    throw FetchError("Response body exceeded size limit (" +
                                     std::to_string(options_.max_body_bytes) + " bytes)", mocked->status_code);
                }
                if (mocked->final_url.empty()) {
                    mocked->final_url = current_url;
                }
                return *mocked;
            }
        }

        ParsedUrl parsed = parse_url(current_url);

        std::unique_ptr<httplib::Client> client;
        if (parsed.scheme == "https") {
            #ifdef CPPHTTPLIB_OPENSSL_SUPPORT
            client = std::make_unique<httplib::SSLClient>(parsed.host, parsed.port);
            #else
            client = std::make_unique<httplib::Client>(parsed.scheme + "://" + parsed.host_port);
            #endif
        } else {
            client = std::make_unique<httplib::Client>(parsed.host, parsed.port);
        }

        client->set_connection_timeout(options_.timeout_seconds, 0);
        client->set_read_timeout(options_.timeout_seconds, 0);
        client->set_follow_location(false);

        httplib::Headers headers = {
            {"User-Agent", options_.user_agent},
            {"Accept", "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8"}
        };

        std::string body;
        bool limit_exceeded = false;

        auto res = client->Get(parsed.path, headers, [&](const char* data, std::size_t len) {
            if (body.size() + len > options_.max_body_bytes) {
                limit_exceeded = true;
                return false; // abort download
            }
            body.append(data, len);
            return true;
        });

        if (!res) {
            auto err = res.error();
            throw FetchError("Network request failed: " + httplib::to_string(err));
        }

        if (limit_exceeded || body.size() > options_.max_body_bytes) {
            throw FetchError("Response body exceeded size limit (" +
                             std::to_string(options_.max_body_bytes) + " bytes)", res->status);
        }

        // Handle redirects (301, 302, 303, 307, 308)
        if (res->status == 301 || res->status == 302 || res->status == 303 ||
            res->status == 307 || res->status == 308) {
            if (redirects_remaining <= 0) {
                throw FetchError("Exceeded maximum redirects (" + std::to_string(options_.max_redirects) + ")", res->status);
            }
            --redirects_remaining;
            std::string loc = res->get_header_value("Location");
            if (loc.empty()) {
                throw FetchError("Redirect response missing Location header", res->status);
            }
            current_url = resolve_redirect(parsed, loc);
            continue;
        }

        if (res->status < 200 || res->status >= 300) {
            throw FetchError("HTTP " + std::to_string(res->status) + " error fetching " + current_url, res->status);
        }

        std::string ct = res->get_header_value("Content-Type");
        if (!is_supported_content_type(ct)) {
            throw FetchError("Unsupported Content-Type: " + ct, res->status);
        }

        return FetchResponse{
            .status_code = res->status,
            .content_type = std::move(ct),
            .body = std::move(body),
            .final_url = std::move(current_url)
        };
    }
}

} // namespace aquila::knowledge

