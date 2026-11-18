#include "aquila/knowledge/web_search.hpp"
#include "aquila/knowledge/html_cleaner.hpp"
#include "aquila/knowledge/searxng_manager.hpp"
#include "aquila/knowledge/web_fetcher.hpp"

#include <httplib.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <chrono>
#include <iomanip>
#include <regex>
#include <sstream>
#include <thread>

namespace aquila::knowledge {

namespace {

using Json = nlohmann::json;

std::string url_encode(std::string_view value) {
    std::ostringstream escaped;
    escaped.fill('0');
    escaped << std::hex;

    for (unsigned char c : value) {
        if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            escaped << c;
        } else if (c == ' ') {
            escaped << '+';
        } else {
            escaped << '%' << std::uppercase << std::setw(2) << int(c) << std::nouppercase;
        }
    }
    return escaped.str();
}

std::string url_decode(std::string_view in) {
    std::string out;
    out.reserve(in.size());
    for (std::size_t i = 0; i < in.size(); ++i) {
        if (in[i] == '%' && i + 2 < in.size()) {
            int value = 0;
            std::istringstream is(std::string(in.substr(i + 1, 2)));
            if (is >> std::hex >> value) {
                out.push_back(static_cast<char>(value));
                i += 2;
                continue;
            }
        } else if (in[i] == '+') {
            out.push_back(' ');
            continue;
        }
        out.push_back(in[i]);
    }
    return out;
}

std::string strip_html_tags(std::string_view html) {
    static const std::regex tag_re(R"(<[^>]+>)");
    std::string text = std::regex_replace(std::string(html), tag_re, " ");
    std::string decoded = HtmlCleaner::decode_entities(text);
    static const std::regex ws_re(R"(\s+)");
    std::string normalized = std::regex_replace(decoded, ws_re, " ");
    auto start = normalized.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    auto end = normalized.find_last_not_of(" \t\r\n");
    return normalized.substr(start, end - start + 1);
}

std::string simplify_keywords_for_fallback(std::string_view query, std::size_t max_terms = 4) {
    static const std::vector<std::string_view> kStops = {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "guide", "how", "in", "into", "is", "it", "of", "on",
        "or", "that", "the", "this", "to", "tutorial", "using", "vs", "what",
        "when", "where", "which", "who", "why", "with", "comprehensive",
        "overview", "methods", "research", "tools", "best"
    };
    std::vector<std::string> kept;
    std::string cur;
    auto flush = [&]() {
        if (cur.size() < 2) { cur.clear(); return; }
        std::string low = cur;
        std::transform(low.begin(), low.end(), low.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        // Skip 4-digit years like 2023/2024/2025/2026
        const bool is_year = low.size() == 4 &&
                             std::all_of(low.begin(), low.end(), [](unsigned char c) { return std::isdigit(c); }) &&
                             (low.starts_with("19") || low.starts_with("20"));
        const bool is_stop = std::find(kStops.begin(), kStops.end(), low) != kStops.end();
        if (!is_year && !is_stop) {
            if (std::find(kept.begin(), kept.end(), cur) == kept.end()) {
                kept.push_back(cur);
            }
        }
        cur.clear();
    };
    for (unsigned char c : query) {
        if (std::isalnum(c) || c == '_' || c == '+' || c == '#') {
            cur.push_back(static_cast<char>(c));
        } else {
            flush();
            if (kept.size() >= max_terms) break;
        }
    }
    if (kept.size() < max_terms) flush();
    std::string out;
    for (std::size_t i = 0; i < kept.size() && i < max_terms; ++i) {
        if (i > 0) out += ' ';
        out += kept[i];
    }
    return out;
}

} // namespace

std::string_view to_string(SearchProvider provider) noexcept {
    switch (provider) {
        case SearchProvider::duckduckgo: return "duckduckgo";
        case SearchProvider::searxng: return "searxng";
        case SearchProvider::wikipedia: return "wikipedia";
        case SearchProvider::auto_detect: return "auto";
    }
    return "duckduckgo";
}

SearchProvider search_provider_from_string(std::string_view s) noexcept {
    if (s == "searxng") return SearchProvider::searxng;
    if (s == "wikipedia" || s == "wiki") return SearchProvider::wikipedia;
    if (s == "auto" || s == "auto_detect") return SearchProvider::auto_detect;
    return SearchProvider::duckduckgo;
}

WebSearchEngine::WebSearchEngine(SearchOptions options)
    : options_(std::move(options)) {}

void WebSearchEngine::set_mock_handler(MockHandler handler) {
    mock_handler_ = std::move(handler);
}

std::string clean_query_string(std::string_view query) {
    std::string q(query);
    while (!q.empty() && (q.front() == '"' || q.front() == '\'' || std::isspace(static_cast<unsigned char>(q.front())))) {
        q.erase(q.begin());
    }
    while (!q.empty() && (q.back() == '"' || q.back() == '\'' || std::isspace(static_cast<unsigned char>(q.back())))) {
        q.pop_back();
    }
    return q;
}

std::vector<SearchResult> WebSearchEngine::search_duckduckgo_lite(
    std::string_view query,
    int max_results
) const {
    std::vector<SearchResult> results;
    const std::string clean_query = clean_query_string(query);
    if (clean_query.empty() || max_results <= 0) {
        return results;
    }

    FetchOptions fetch_opts;
    fetch_opts.method = "POST";
    fetch_opts.post_body = "q=" + url_encode(clean_query);
    fetch_opts.content_type = "application/x-www-form-urlencoded";
    fetch_opts.user_agent = options_.user_agent;
    fetch_opts.timeout_seconds = options_.timeout_seconds;

    FetchResponse res;
    bool fetched = false;
    last_ddg_status_ = 200;
    // Retry at most once only for transient network/TLS drops (status_code() == 0);
    // never retry or bypass non-200 anti-bot/rate-limit HTTP status responses.
    for (int attempt = 0; attempt < 2; ++attempt) {
        try {
            res = execute_http("https://lite.duckduckgo.com/lite/", fetch_opts);
            last_ddg_status_ = res.status_code;
            fetched = true;
            break;
        } catch (const FetchError& e) {
            last_ddg_status_ = e.status_code();
            if (e.status_code() != 0 || attempt == 1) {
                return results;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(300));
        } catch (...) {
            last_ddg_status_ = 0;
            return results;
        }
    }

    if (!fetched || res.status_code != 200 || res.body.empty()) {
        return results;
    }

    const std::string& html = res.body;

    // Regex matching both attribute orders for result-link:
    // 1: href before class
    // 2: class before href
    static const std::regex link_re(
        R"(<a\s+[^>]*href=['"]([^'"]+)['"][^>]*class=['"]result-link['"][^>]*>(.*?)</a>|<a\s+[^>]*class=['"]result-link['"][^>]*href=['"]([^'"]+)['"][^>]*>(.*?)</a>)",
        std::regex_constants::icase
    );
    static const std::regex snippet_re(
        R"(<td\s+[^>]*class=['"]result-snippet['"][^>]*>([\s\S]*?)</td>)",
        std::regex_constants::icase
    );

    std::vector<std::pair<std::string, std::string>> found_links;
    auto link_begin = std::sregex_iterator(html.begin(), html.end(), link_re);
    auto link_end = std::sregex_iterator();
    for (auto it = link_begin; it != link_end && static_cast<int>(found_links.size()) < max_results; ++it) {
        std::smatch m = *it;
        std::string raw_url = m[1].matched ? m[1].str() : (m[3].matched ? m[3].str() : "");
        std::string raw_title = m[2].matched ? m[2].str() : (m[4].matched ? m[4].str() : "");

        if (raw_url.find("uddg=") != std::string::npos) {
            auto pos = raw_url.find("uddg=");
            auto end = raw_url.find('&', pos);
            std::string encoded = (end == std::string::npos) ? raw_url.substr(pos + 5) : raw_url.substr(pos + 5, end - (pos + 5));
            raw_url = url_decode(encoded);
        }

        std::string title = strip_html_tags(raw_title);
        if (raw_url.starts_with("http://") || raw_url.starts_with("https://")) {
            found_links.emplace_back(std::move(raw_url), std::move(title));
        }
    }

    std::vector<std::string> snippets;
    auto snip_begin = std::sregex_iterator(html.begin(), html.end(), snippet_re);
    auto snip_end = std::sregex_iterator();
    for (auto it = snip_begin; it != snip_end && snippets.size() < found_links.size(); ++it) {
        snippets.push_back(strip_html_tags((*it)[1].str()));
    }

    for (std::size_t i = 0; i < found_links.size(); ++i) {
        SearchResult sr;
        sr.url = found_links[i].first;
        sr.title = found_links[i].second;
        sr.snippet = (i < snippets.size()) ? snippets[i] : "";
        sr.engine = "duckduckgo";
        sr.score = PageScorer::score_url(sr.url, query, sr.title, sr.snippet);
        results.push_back(std::move(sr));
    }

    return results;
}

std::vector<SearchResult> WebSearchEngine::search_searxng(
    std::string_view query,
    int max_results
) const {
    std::vector<SearchResult> results;
    const std::string clean_query = clean_query_string(query);
    if (clean_query.empty() || max_results <= 0) {
        return results;
    }

    // Auto-start local SearXNG if configured on loopback and not yet serving.
    (void)SearxngManager::instance().ensure_running(options_.searxng_endpoint, 5000);

    // Parse endpoint host and port
    std::string host = "127.0.0.1";
    int port = 8888;
    if (!SearxngManager::parse_endpoint(options_.searxng_endpoint, host, port)) {
        return results;
    }

    httplib::Client cli(host, port);
    cli.set_connection_timeout(options_.timeout_seconds, 0);
    cli.set_read_timeout(options_.timeout_seconds, 0);

    const std::string path = "/search?q=" + url_encode(clean_query) +
                             "&format=json&limit=" + std::to_string(std::max(max_results, 10));
    auto res = cli.Get(path.c_str());
    if (!res || res->status != 200) {
        return results;
    }

    try {
        Json j = Json::parse(res->body);
        if (j.contains("results") && j["results"].is_array()) {
            for (const auto& item : j["results"]) {
                if (static_cast<int>(results.size()) >= max_results) {
                    break;
                }
                SearchResult sr;
                sr.title = item.value("title", "");
                sr.url = item.value("url", "");
                sr.snippet = item.value("content", "");
                sr.engine = item.value("engine", "searxng");
                if (!sr.url.empty()) {
                    sr.score = PageScorer::score_url(sr.url, clean_query, sr.title, sr.snippet);
                    results.push_back(std::move(sr));
                }
            }
        }
    } catch (...) {
        // Parsing failure
    }

    return results;
}

std::vector<SearchResult> WebSearchEngine::search_wikipedia(
    std::string_view query,
    int max_results
) const {
    std::vector<SearchResult> results;
    const std::string clean_query = clean_query_string(query);
    if (clean_query.empty() || max_results <= 0) {
        return results;
    }

    FetchOptions fetch_opts;
    fetch_opts.method = "GET";
    fetch_opts.user_agent = options_.user_agent;
    fetch_opts.timeout_seconds = options_.timeout_seconds;

    const std::string path = "/w/api.php?action=opensearch&search=" +
                             url_encode(clean_query) +
                             "&limit=" + std::to_string(max_results) +
                             "&namespace=0&format=json";

    FetchResponse res;
    try {
        res = execute_http("https://en.wikipedia.org" + path, fetch_opts);
    } catch (...) {
        return results;
    }

    if (res.status_code != 200 || res.body.empty()) {
        return results;
    }

    try {
        Json j = Json::parse(res.body);
        if (j.is_array() && j.size() >= 4) {
            const auto& titles = j[1];
            const auto& snippets = j[2];
            const auto& urls = j[3];
            for (std::size_t i = 0; i < titles.size() && static_cast<int>(results.size()) < max_results; ++i) {
                SearchResult sr;
                sr.title = titles[i].is_string() ? titles[i].get<std::string>() : "";
                sr.snippet = (i < snippets.size() && snippets[i].is_string()) ? snippets[i].get<std::string>() : "";
                sr.url = (i < urls.size() && urls[i].is_string()) ? urls[i].get<std::string>() : "";
                sr.engine = "wikipedia";
                if (!sr.url.empty()) {
                    sr.score = PageScorer::score_url(sr.url, clean_query, sr.title, sr.snippet);
                    results.push_back(std::move(sr));
                }
            }
        }
    } catch (...) {}

    if (!results.empty()) {
        return results;
    }

    // OpenSearch only matches page title prefixes; fall back to Wikipedia full-text search
    // (retrying with simplified keywords if verbose queries with years/quotes yield 0 hits).
    const std::vector<std::string> fulltext_queries = {
        clean_query,
        simplify_keywords_for_fallback(clean_query, 4),
        simplify_keywords_for_fallback(clean_query, 2),
    };
    std::string last_tried;
    for (const std::string& ftq : fulltext_queries) {
        if (ftq.empty() || ftq == last_tried) continue;
        last_tried = ftq;
        const std::string search_path = "/w/api.php?action=query&list=search&srsearch=" +
                                        url_encode(ftq) +
                                        "&srlimit=" + std::to_string(max_results) +
                                        "&utf8=1&format=json";
        try {
            const FetchResponse full_res = execute_http("https://en.wikipedia.org" + search_path, fetch_opts);
            if (full_res.status_code == 200 && !full_res.body.empty()) {
                const Json j = Json::parse(full_res.body);
                if (j.contains("query") && j["query"].contains("search") && j["query"]["search"].is_array()) {
                    for (const auto& item : j["query"]["search"]) {
                        if (static_cast<int>(results.size()) >= max_results) {
                            break;
                        }
                        const std::string title = item.value("title", "");
                        if (title.empty()) continue;
                        std::string slug = title;
                        std::replace(slug.begin(), slug.end(), ' ', '_');
                        SearchResult sr;
                        sr.title = title;
                        sr.snippet = strip_html_tags(item.value("snippet", ""));
                        sr.url = "https://en.wikipedia.org/wiki/" + url_encode(slug);
                        sr.engine = "wikipedia";
                        sr.score = PageScorer::score_url(sr.url, clean_query, sr.title, sr.snippet);
                        results.push_back(std::move(sr));
                    }
                }
            }
        } catch (...) {}
        if (!results.empty()) {
            break;
        }
    }

    return results;
}

std::vector<SearchResult> WebSearchEngine::search(std::string_view query) const {
    const int kMax = options_.max_results > 0 ? options_.max_results : 5;
    std::vector<SearchResult> results;

    if (mock_handler_) {
        auto mocked = mock_handler_(query);
        if (mocked) {
            results = std::move(*mocked);
            std::sort(results.begin(), results.end(), [](const SearchResult& a, const SearchResult& b) {
                return a.score > b.score;
            });
            if (static_cast<int>(results.size()) > kMax) {
                results.resize(kMax);
            }
            return results;
        }
    }

    switch (options_.provider) {
        case SearchProvider::searxng:
            results = search_searxng(query, kMax);
            if (results.empty()) {
                results = search_duckduckgo_lite(query, kMax);
            }
            if (results.empty()) {
                results = search_wikipedia(query, kMax);
            }
            break;
        case SearchProvider::wikipedia:
            results = search_wikipedia(query, kMax);
            break;
        case SearchProvider::auto_detect: {
            results = search_searxng(query, kMax);
            if (results.empty()) {
                results = search_duckduckgo_lite(query, kMax);
            }
            if (results.empty()) {
                results = search_wikipedia(query, kMax);
            }
            break;
        }
        case SearchProvider::duckduckgo:
        default:
            results = search_duckduckgo_lite(query, kMax);
            if (results.empty()) {
                results = search_wikipedia(query, kMax);
            }
            break;
    }

    // Sort by relevance & authority score descending
    std::sort(results.begin(), results.end(), [](const SearchResult& a, const SearchResult& b) {
        return a.score > b.score;
    });

    if (static_cast<int>(results.size()) > kMax) {
        results.resize(kMax);
    }

    return results;
}

} // namespace aquila::knowledge

