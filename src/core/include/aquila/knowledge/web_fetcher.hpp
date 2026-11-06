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
    int timeout_seconds{10};
    std::size_t max_body_bytes{2 * 1024 * 1024}; // 2 MB
    int max_redirects{5};
    std::string user_agent{"Aquila-Agent/1.0"};
};

struct FetchResponse {
    int status_code{200};
    std::string content_type;
    std::string body;
    std::string final_url;
};

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

