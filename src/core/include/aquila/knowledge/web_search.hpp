#pragma once

#include "aquila/knowledge/page_scorer.hpp"

#include <cstddef>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::knowledge {

enum class SearchProvider {
    duckduckgo,
    searxng,
    wikipedia,
    auto_detect
};

[[nodiscard]] std::string_view to_string(SearchProvider provider) noexcept;
[[nodiscard]] SearchProvider search_provider_from_string(std::string_view s) noexcept;

struct SearchResult {
    std::string title;
    std::string url;
    std::string snippet;
    std::string engine{"duckduckgo"};
    double score{0.0};
};

struct SearchOptions {
    SearchProvider provider{SearchProvider::duckduckgo};
    std::string searxng_endpoint{"http://127.0.0.1:8888"};
    int max_results{5};
    int timeout_seconds{10};
    std::string user_agent{"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"};
};

class WebSearchEngine {
public:
    using MockHandler = std::function<std::optional<std::vector<SearchResult>>(std::string_view query)>;

    explicit WebSearchEngine(SearchOptions options = {});

    void set_mock_handler(MockHandler handler);

    [[nodiscard]] std::vector<SearchResult> search(std::string_view query) const;

    [[nodiscard]] std::vector<SearchResult> search_duckduckgo_lite(
        std::string_view query,
        int max_results
    ) const;

    [[nodiscard]] std::vector<SearchResult> search_searxng(
        std::string_view query,
        int max_results
    ) const;

    [[nodiscard]] std::vector<SearchResult> search_wikipedia(
        std::string_view query,
        int max_results
    ) const;

    [[nodiscard]] const SearchOptions& options() const noexcept { return options_; }
    void set_options(SearchOptions options) noexcept { options_ = std::move(options); }

private:
    SearchOptions options_;
    MockHandler mock_handler_;
};

} // namespace aquila::knowledge

