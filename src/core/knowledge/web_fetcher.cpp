#include "aquila/knowledge/web_fetcher.hpp"

#include <httplib.h>

#include <algorithm>
#include <cctype>
#include <sstream>

#ifdef _WIN32
#include <windows.h>
#include <winhttp.h>
#pragma comment(lib, "winhttp.lib")
#endif

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
    return lower.starts_with("text/") || lower == "application/xhtml+xml" || lower == "application/json";
}

#ifdef _WIN32
std::wstring to_wstring(std::string_view str) {
    if (str.empty()) return {};
    int sz = MultiByteToWideChar(CP_UTF8, 0, str.data(), static_cast<int>(str.size()), NULL, 0);
    std::wstring w(sz, 0);
    MultiByteToWideChar(CP_UTF8, 0, str.data(), static_cast<int>(str.size()), &w[0], sz);
    return w;
}

std::string from_wstring(const std::wstring& w) {
    if (w.empty()) return {};
    int sz = WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), NULL, 0, NULL, NULL);
    std::string s(sz, 0);
    WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), &s[0], sz, NULL, NULL);
    return s;
}

FetchResponse execute_http_win(std::string_view initial_url, const FetchOptions& options) {
    std::string current_url = std::string(initial_url);
    int redirects_remaining = options.max_redirects;

    HINTERNET hSession = WinHttpOpen(to_wstring(options.user_agent).c_str(),
                                    WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                    WINHTTP_NO_PROXY_NAME,
                                    WINHTTP_NO_PROXY_BYPASS,
                                    0);
    if (!hSession) {
        throw FetchError("Failed to initialize WinHttp session");
    }

    struct SessionGuard {
        HINTERNET s;
        ~SessionGuard() { if (s) WinHttpCloseHandle(s); }
    } session_guard{hSession};

    while (true) {
        ParsedUrl parsed = parse_url(current_url);
        HINTERNET hConnect = WinHttpConnect(hSession,
                                           to_wstring(parsed.host).c_str(),
                                           static_cast<INTERNET_PORT>(parsed.port),
                                           0);
        if (!hConnect) {
            throw FetchError("WinHttpConnect failed for host: " + parsed.host);
        }

        struct ConnectGuard {
            HINTERNET c;
            ~ConnectGuard() { if (c) WinHttpCloseHandle(c); }
        } connect_guard{hConnect};

        DWORD flags = (parsed.scheme == "https") ? WINHTTP_FLAG_SECURE : 0;
        std::wstring method_w = to_wstring(options.method.empty() ? "GET" : options.method);
        std::wstring path_w = to_wstring(parsed.path);

        HINTERNET hRequest = WinHttpOpenRequest(hConnect,
                                               method_w.c_str(),
                                               path_w.c_str(),
                                               NULL,
                                               WINHTTP_NO_REFERER,
                                               WINHTTP_DEFAULT_ACCEPT_TYPES,
                                               flags);
        if (!hRequest) {
            throw FetchError("WinHttpOpenRequest failed for path: " + parsed.path);
        }

        struct RequestGuard {
            HINTERNET r;
            ~RequestGuard() { if (r) WinHttpCloseHandle(r); }
        } request_guard{hRequest};

        int timeout_ms = options.timeout_seconds > 0 ? options.timeout_seconds * 1000 : 10000;
        WinHttpSetTimeouts(hRequest, timeout_ms, timeout_ms, timeout_ms, timeout_ms);

        std::wstring headers_w = L"Accept: text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8\r\n";
        if (!options.content_type.empty()) {
            headers_w += L"Content-Type: " + to_wstring(options.content_type) + L"\r\n";
        }

        BOOL send_ok = FALSE;
        if (options.method == "POST" && !options.post_body.empty()) {
            send_ok = WinHttpSendRequest(hRequest,
                                         headers_w.c_str(),
                                         static_cast<DWORD>(headers_w.size()),
                                         (LPVOID)options.post_body.data(),
                                         static_cast<DWORD>(options.post_body.size()),
                                         static_cast<DWORD>(options.post_body.size()),
                                         0);
        } else {
            send_ok = WinHttpSendRequest(hRequest,
                                         headers_w.c_str(),
                                         static_cast<DWORD>(headers_w.size()),
                                         NULL,
                                         0,
                                         0,
                                         0);
        }

        if (!send_ok) {
            DWORD err = GetLastError();
            throw FetchError("WinHttpSendRequest failed with error: " + std::to_string(err));
        }

        if (!WinHttpReceiveResponse(hRequest, NULL)) {
            DWORD err = GetLastError();
            throw FetchError("WinHttpReceiveResponse failed with error: " + std::to_string(err));
        }

        DWORD status_code = 0;
        DWORD status_size = sizeof(status_code);
        WinHttpQueryHeaders(hRequest,
                            WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                            WINHTTP_HEADER_NAME_BY_INDEX,
                            &status_code,
                            &status_size,
                            WINHTTP_NO_HEADER_INDEX);

        // Handle redirects (301, 302, 303, 307, 308)
        if (status_code == 301 || status_code == 302 || status_code == 303 ||
            status_code == 307 || status_code == 308) {
            if (redirects_remaining <= 0) {
                throw FetchError("Exceeded maximum redirects (" + std::to_string(options.max_redirects) + ")", status_code);
            }
            --redirects_remaining;
            wchar_t loc_buf[2048] = {0};
            DWORD loc_size = sizeof(loc_buf);
            if (WinHttpQueryHeaders(hRequest,
                                    WINHTTP_QUERY_LOCATION,
                                    WINHTTP_HEADER_NAME_BY_INDEX,
                                    loc_buf,
                                    &loc_size,
                                    WINHTTP_NO_HEADER_INDEX)) {
                std::string loc = from_wstring(loc_buf);
                current_url = resolve_redirect(parsed, loc);
                continue;
            }
            throw FetchError("Redirect response missing Location header", status_code);
        }

        wchar_t ct_buf[512] = {0};
        DWORD ct_size = sizeof(ct_buf);
        std::string content_type;
        if (WinHttpQueryHeaders(hRequest,
                                WINHTTP_QUERY_CONTENT_TYPE,
                                WINHTTP_HEADER_NAME_BY_INDEX,
                                ct_buf,
                                &ct_size,
                                WINHTTP_NO_HEADER_INDEX)) {
            content_type = from_wstring(ct_buf);
        }

        std::string body;
        DWORD bytes_avail = 0;
        while (WinHttpQueryDataAvailable(hRequest, &bytes_avail) && bytes_avail > 0) {
            if (body.size() + bytes_avail > options.max_body_bytes) {
                throw FetchError("Response body exceeded size limit (" +
                                 std::to_string(options.max_body_bytes) + " bytes)", status_code);
            }
            std::string chunk(bytes_avail, '\0');
            DWORD bytes_read = 0;
            if (WinHttpReadData(hRequest, &chunk[0], bytes_avail, &bytes_read)) {
                chunk.resize(bytes_read);
                body.append(chunk);
            } else {
                break;
            }
        }

        return FetchResponse{
            .status_code = static_cast<int>(status_code),
            .content_type = std::move(content_type),
            .body = std::move(body),
            .final_url = std::move(current_url)
        };
    }
}
#endif

FetchResponse execute_http_httplib(std::string_view initial_url, const FetchOptions& options) {
    std::string current_url = std::string(initial_url);
    int redirects_remaining = options.max_redirects;

    while (true) {
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

        client->set_connection_timeout(options.timeout_seconds, 0);
        client->set_read_timeout(options.timeout_seconds, 0);
        client->set_follow_location(false);

        httplib::Headers headers = {
            {"User-Agent", options.user_agent},
            {"Accept", "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8"}
        };
        if (!options.content_type.empty()) {
            headers.emplace("Content-Type", options.content_type);
        }

        std::string body;
        bool limit_exceeded = false;

        httplib::Result res;
        if (options.method == "POST") {
            res = client->Post(parsed.path, headers, options.post_body, options.content_type.empty() ? "text/plain" : options.content_type);
            if (res) body = res->body;
        } else {
            res = client->Get(parsed.path, headers, [&](const char* data, std::size_t len) {
                if (body.size() + len > options.max_body_bytes) {
                    limit_exceeded = true;
                    return false;
                }
                body.append(data, len);
                return true;
            });
        }

        if (!res) {
            auto err = res.error();
            throw FetchError("Network request failed: " + httplib::to_string(err));
        }

        if (limit_exceeded || body.size() > options.max_body_bytes) {
            throw FetchError("Response body exceeded size limit (" +
                             std::to_string(options.max_body_bytes) + " bytes)", res->status);
        }

        if (res->status == 301 || res->status == 302 || res->status == 303 ||
            res->status == 307 || res->status == 308) {
            if (redirects_remaining <= 0) {
                throw FetchError("Exceeded maximum redirects (" + std::to_string(options.max_redirects) + ")", res->status);
            }
            --redirects_remaining;
            std::string loc = res->get_header_value("Location");
            if (loc.empty()) {
                throw FetchError("Redirect response missing Location header", res->status);
            }
            current_url = resolve_redirect(parsed, loc);
            continue;
        }

        return FetchResponse{
            .status_code = res->status,
            .content_type = res->get_header_value("Content-Type"),
            .body = std::move(body),
            .final_url = std::move(current_url)
        };
    }
}

} // namespace

FetchResponse execute_http(std::string_view url, const FetchOptions& options) {
#ifdef _WIN32
    return execute_http_win(url, options);
#else
    return execute_http_httplib(url, options);
#endif
}

WebFetcher::WebFetcher(FetchOptions options) : options_(std::move(options)) {}

void WebFetcher::set_mock_handler(MockHandler handler) {
    mock_handler_ = std::move(handler);
}

FetchResponse WebFetcher::fetch(std::string_view url) const {
    if (mock_handler_) {
        auto mocked = mock_handler_(url);
        if (mocked) {
            if (mocked->status_code < 200 || mocked->status_code >= 300) {
                throw FetchError("HTTP " + std::to_string(mocked->status_code) + " error fetching " + std::string(url),
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
                mocked->final_url = std::string(url);
            }
            return *mocked;
        }
    }

    auto resp = execute_http(url, options_);
    if (resp.status_code < 200 || resp.status_code >= 300) {
        throw FetchError("HTTP " + std::to_string(resp.status_code) + " error fetching " + std::string(url), resp.status_code);
    }
    if (!is_supported_content_type(resp.content_type)) {
        throw FetchError("Unsupported Content-Type: " + resp.content_type, resp.status_code);
    }
    return resp;
}

} // namespace aquila::knowledge

