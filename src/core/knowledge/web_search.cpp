#include "aquila/knowledge/web_search.hpp"
#include "aquila/knowledge/html_cleaner.hpp"
#include "aquila/knowledge/web_fetcher.hpp"

#include <httplib.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <iomanip>
#include <regex>
#include <sstream>

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
    return HtmlCleaner::decode_entities(text);
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

std::vector<SearchResult> WebSearchEngine::search_duckduckgo_lite(
    std::string_view query,
    int max_results
) const {
    std::vector<SearchResult> results;
    if (query.empty() || max_results <= 0) {
        return results;
    }

    FetchOptions fetch_opts;
    fetch_opts.method = "POST";
    fetch_opts.post_body = "q=" + url_encode(query);
    fetch_opts.content_type = "application/x-www-form-urlencoded";
    fetch_opts.user_agent = options_.user_agent;
    fetch_opts.timeout_seconds = options_.timeout_seconds;

    FetchResponse res;
    try {
        res = execute_http("https://lite.duckduckgo.com/lite/", fetch_opts);
    } catch (...) {
        return results;
    }

    if (res.status_code != 200 || res.body.empty()) {
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
        R"(<td\s+[^>]*class=['"]result-snippet['"][^>]*>(.*?)</td>)",
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
    if (query.empty() || max_results <= 0) {
        return results;
    }

    // Parse endpoint host and port
    std::string host = "127.0.0.1";
    int port = 8888;
    std::string endpoint = options_.searxng_endpoint;
    if (endpoint.starts_with("http://")) {
        endpoint = endpoint.substr(7);
    } else if (endpoint.starts_with("https://")) {
        endpoint = endpoint.substr(8);
    }
    auto slash = endpoint.find('/');
    if (slash != std::string::npos) {
        endpoint = endpoint.substr(0, slash);
    }
    auto colon = endpoint.find(':');
    if (colon != std::string::npos) {
        host = endpoint.substr(0, colon);
        try {
            port = std::stoi(endpoint.substr(colon + 1));
        } catch (...) {
            port = 8888;
        }
    } else {
        host = endpoint;
        port = 80;
    }

    httplib::Client cli(host, port);
    cli.set_connection_timeout(options_.timeout_seconds, 0);
    cli.set_read_timeout(options_.timeout_seconds, 0);

    const std::string path = "/search?q=" + url_encode(query) + "&format=json";
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
                    sr.score = PageScorer::score_url(sr.url, query, sr.title, sr.snippet);
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
    if (query.empty() || max_results <= 0) {
        return results;
    }

    FetchOptions fetch_opts;
    fetch_opts.method = "GET";
    fetch_opts.user_agent = options_.user_agent;
    fetch_opts.timeout_seconds = options_.timeout_seconds;

    const std::string path = "/w/api.php?action=opensearch&search=" +
                             url_encode(query) +
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
                    sr.score = PageScorer::score_url(sr.url, query, sr.title, sr.snippet);
                    results.push_back(std::move(sr));
                }
            }
        }
    } catch (...) {}

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

