#include "aquila/knowledge/page_cache.hpp"

#include "aquila/knowledge/sha256.hpp"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <vector>

namespace aquila::knowledge {

namespace {

struct QueryParam {
    std::string key;
    std::string val;

    bool operator<(const QueryParam& other) const noexcept {
        if (key != other.key) return key < other.key;
        return val < other.val;
    }
};

std::string normalize_query(std::string_view q) {
    if (q.empty()) return {};
    std::vector<QueryParam> params;

    std::size_t start = 0;
    while (start < q.size()) {
        auto amp = q.find('&', start);
        auto token = (amp == std::string_view::npos) ? q.substr(start) : q.substr(start, amp - start);
        start = (amp == std::string_view::npos) ? q.size() : amp + 1;

        if (token.empty()) continue;
        auto eq = token.find('=');
        if (eq == std::string_view::npos) {
            params.push_back(QueryParam{std::string(token), ""});
        } else {
            params.push_back(QueryParam{std::string(token.substr(0, eq)), std::string(token.substr(eq + 1))});
        }
    }

    std::sort(params.begin(), params.end());

    std::string out;
    for (std::size_t i = 0; i < params.size(); ++i) {
        if (i > 0) out.push_back('&');
        out.append(params[i].key);
        if (!params[i].val.empty()) {
            out.push_back('=');
            out.append(params[i].val);
        }
    }
    return out;
}

} // namespace

PageCache::PageCache(storage::SqliteDb& db, std::shared_ptr<WebFetcher> fetcher)
    : db_(db), fetcher_(std::move(fetcher)) {
    if (!fetcher_) {
        fetcher_ = std::make_shared<WebFetcher>();
    }
    init_tables();
}

void PageCache::init_tables() {
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS page_cache (
            url_hash TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            clean_text TEXT NOT NULL,
            title TEXT,
            content_hash TEXT NOT NULL,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status_code INTEGER NOT NULL
        );
    )");
}

std::string PageCache::canonicalize_url(std::string_view url) {
    if (url.empty()) return {};

    // 1. Strip fragment '#'
    auto hash_pos = url.find('#');
    std::string_view no_frag = (hash_pos == std::string_view::npos) ? url : url.substr(0, hash_pos);

    // 2. Extract scheme
    auto scheme_end = no_frag.find("://");
    if (scheme_end == std::string_view::npos) {
        return std::string(no_frag);
    }

    std::string scheme;
    scheme.reserve(scheme_end);
    for (std::size_t i = 0; i < scheme_end; ++i) {
        scheme.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(no_frag[i]))));
    }

    auto rest = no_frag.substr(scheme_end + 3);

    // 3. Extract query
    auto q_pos = rest.find('?');
    std::string_view authority_path = (q_pos == std::string_view::npos) ? rest : rest.substr(0, q_pos);
    std::string_view query_raw = (q_pos == std::string_view::npos) ? std::string_view{} : rest.substr(q_pos + 1);

    // 4. Split authority and path
    auto slash = authority_path.find('/');
    std::string_view authority = (slash == std::string_view::npos) ? authority_path : authority_path.substr(0, slash);
    std::string path = (slash == std::string_view::npos) ? "/" : std::string(authority_path.substr(slash));
    if (path.empty()) path = "/";

    // 5. Parse host and port
    std::string host;
    std::string port_str;
    auto colon = authority.find(':');
    if (colon != std::string_view::npos) {
        host = std::string(authority.substr(0, colon));
        port_str = std::string(authority.substr(colon + 1));
    } else {
        host = std::string(authority);
    }

    for (char& c : host) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }

    // Strip default ports
    bool include_port = false;
    if (!port_str.empty()) {
        if ((scheme == "http" && port_str == "80") || (scheme == "https" && port_str == "443")) {
            include_port = false;
        } else {
            include_port = true;
        }
    }

    // 6. Normalize query
    std::string query_norm = normalize_query(query_raw);

    // 7. Assemble canonical URL
    std::string canonical = scheme + "://" + host;
    if (include_port) {
        canonical.push_back(':');
        canonical.append(port_str);
    }
    canonical.append(path);
    if (!query_norm.empty()) {
        canonical.push_back('?');
        canonical.append(query_norm);
    }
    return canonical;
}

std::string PageCache::compute_url_hash(std::string_view canonical_url) {
    return Sha256::hash_hex(canonical_url);
}

bool PageCache::has_cached(std::string_view url) const {
    const auto can_url = canonicalize_url(url);
    const auto hash = compute_url_hash(can_url);

    auto stmt = db_.prepare("SELECT 1 FROM page_cache WHERE url_hash = ?");
    stmt.bind(1, hash);
    return stmt.step();
}

std::size_t PageCache::size() const {
    auto stmt = db_.prepare("SELECT count(*) FROM page_cache");
    if (stmt.step()) {
        return static_cast<std::size_t>(stmt.column_int64(0));
    }
    return 0;
}

void PageCache::clear() {
    db_.execute("DELETE FROM page_cache;");
}

CleanedPage PageCache::fetch_and_clean(std::string_view url, bool bypass_cache) {
    const auto canonical_url = canonicalize_url(url);
    const auto url_hash = compute_url_hash(canonical_url);

    if (!bypass_cache) {
        auto stmt = db_.prepare(
            "SELECT url, clean_text, title, status_code FROM page_cache WHERE url_hash = ?"
        );
        stmt.bind(1, url_hash);
        if (stmt.step()) {
            return CleanedPage{
                .url = std::string(stmt.column_text(0)),
                .clean_text = std::string(stmt.column_text(1)),
                .title = std::string(stmt.column_text(2)),
                .status_code = stmt.column_int(3),
                .from_cache = true
            };
        }
    }

    // Cache miss or bypass: fetch and clean
    auto response = fetcher_->fetch(url);
    auto cleaned = HtmlCleaner::clean(response.body);
    const auto content_hash = Sha256::hash_hex(cleaned.text);

    auto insert_stmt = db_.prepare(R"(
        INSERT INTO page_cache (url_hash, url, clean_text, title, content_hash, status_code, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(url_hash) DO UPDATE SET
            url = excluded.url,
            clean_text = excluded.clean_text,
            title = excluded.title,
            content_hash = excluded.content_hash,
            status_code = excluded.status_code,
            fetched_at = CURRENT_TIMESTAMP
    )");

    insert_stmt.bind(1, url_hash);
    insert_stmt.bind(2, canonical_url);
    insert_stmt.bind(3, cleaned.text);
    insert_stmt.bind(4, cleaned.title);
    insert_stmt.bind(5, content_hash);
    insert_stmt.bind(6, response.status_code);
    insert_stmt.step();

    return CleanedPage{
        .url = canonical_url,
        .clean_text = std::move(cleaned.text),
        .title = std::move(cleaned.title),
        .status_code = response.status_code,
        .from_cache = false
    };
}

} // namespace aquila::knowledge

