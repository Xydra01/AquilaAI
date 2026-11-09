#pragma once

#include <cstddef>
#include <functional>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>

namespace aquila::knowledge {

class FetchError : public std::runtime_error {
public:
    explicit FetchError(std::string message, int status_code = 0)
        : std::runtime_error(std::move(message)), status_code_(status_code) {}

    [[nodiscard]] int status_code() const noexcept { return status_code_; }

private:
    int status_code_{0};
};

struct FetchOptions {
    std::string method{"GET"};
    std::string post_body;
    std::string content_type;
    int timeout_seconds{10};
    std::size_t max_body_bytes{2 * 1024 * 1024}; // 2 MB
    int max_redirects{5};
    std::string user_agent{"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"};
};

struct FetchResponse {
    int status_code{200};
    std::string content_type;
    std::string body;
    std::string final_url;
};

[[nodiscard]] FetchResponse execute_http(std::string_view url, const FetchOptions& options);

class WebFetcher {
public:
    using MockHandler = std::function<std::optional<FetchResponse>(std::string_view url)>;

    explicit WebFetcher(FetchOptions options = {});

    void set_mock_handler(MockHandler handler);

    [[nodiscard]] FetchResponse fetch(std::string_view url) const;

    [[nodiscard]] const FetchOptions& options() const noexcept { return options_; }

private:
    FetchOptions options_;
    MockHandler mock_handler_;
};

} // namespace aquila::knowledge

