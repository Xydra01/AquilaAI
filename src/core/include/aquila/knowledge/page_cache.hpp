#pragma once

#include "aquila/knowledge/html_cleaner.hpp"
#include "aquila/knowledge/web_fetcher.hpp"
#include "aquila/storage/sqlite_db.hpp"

#include <memory>
#include <string>
#include <string_view>

namespace aquila::knowledge {

struct CleanedPage {
    std::string url;
    std::string clean_text;
    std::string title;
    int status_code{200};
    bool from_cache{false};
};

class PageCache {
public:
    explicit PageCache(storage::SqliteDb& db, std::shared_ptr<WebFetcher> fetcher = nullptr);

    void init_tables();

    [[nodiscard]] CleanedPage fetch_and_clean(std::string_view url, bool bypass_cache = false);

    [[nodiscard]] bool has_cached(std::string_view url) const;
    [[nodiscard]] std::size_t size() const;
    void clear();

    [[nodiscard]] static std::string canonicalize_url(std::string_view url);
    [[nodiscard]] static std::string compute_url_hash(std::string_view canonical_url);

    WebFetcher& fetcher() noexcept { return *fetcher_; }

private:
    storage::SqliteDb& db_;
    std::shared_ptr<WebFetcher> fetcher_;
};

} // namespace aquila::knowledge

