#include "aquila/knowledge/page_scorer.hpp"

#include <algorithm>
#include <cctype>
#include <regex>
#include <sstream>
#include <string>

namespace aquila::knowledge {

namespace {

std::string to_lower_ascii(std::string_view s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

constexpr std::string_view kPaywallPhrases[] = {
    "preview of subscription",
    "log in via an institution",
    "log in via institution",
    "subscribe to read",
    "subscription content",
    "institutional access",
    "access this chapter",
    "buy ebook",
    "buy e-book",
    "purchase access",
    "sign in to access",
    "create an account to read",
    "this content is available to subscribers",
    "you have full access through",
    "check access",
};

constexpr std::string_view kPaywallDomains[] = {
    "springer.com",
    "link.springer.com",
    "sciencedirect.com",
    "elsevier.com",
    "tandfonline.com",
    "wiley.com",
    "onlinelibrary.wiley.com",
    "jstor.org",
    "nature.com",
    "academic.oup.com",
    "wayf.springernature.com",
};

constexpr std::string_view kChallengePhrases[] = {
    "cloudflare",
    "turnstile",
    "hcaptcha",
    "ddos protection",
    "just a moment...",
    "challenge-platform",
    "verify you are human",
    "checking your browser",
    "enable javascript and cookies to continue",
};

constexpr std::size_t kThinMinSubstantiveChars = 350;
constexpr std::size_t kExcerptMax = 800;

std::string substantive_text(std::string_view markdown) {
    std::string text(markdown);
    // Remove markdown links [title](url) -> title
    static const std::regex link_re(R"(\[([^\]]+)\]\([^)]+\))");
    text = std::regex_replace(text, link_re, "$1");
    // Remove images ![alt](url) -> space
    static const std::regex img_re(R"(!\[[^\]]*\]\([^)]+\))");
    text = std::regex_replace(text, img_re, " ");
    // Remove markdown symbols
    static const std::regex sym_re(R"([#*_>`|])");
    text = std::regex_replace(text, sym_re, " ");
    // Collapse whitespace
    static const std::regex ws_re(R"(\s+)");
    text = std::regex_replace(text, ws_re, " ");

    while (!text.empty() && std::isspace(static_cast<unsigned char>(text.front()))) {
        text.erase(text.begin());
    }
    while (!text.empty() && std::isspace(static_cast<unsigned char>(text.back()))) {
        text.pop_back();
    }
    return text;
}

std::vector<std::string> split_words(std::string_view str) {
    std::vector<std::string> words;
    std::string current;
    for (char c : str) {
        if (std::isalnum(static_cast<unsigned char>(c))) {
            current.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        } else if (!current.empty()) {
            if (current.size() >= 3) {
                words.push_back(std::move(current));
            }
            current.clear();
        }
    }
    if (current.size() >= 3) {
        words.push_back(std::move(current));
    }
    return words;
}

} // namespace

std::string_view to_string(PageQuality quality) noexcept {
    switch (quality) {
        case PageQuality::full: return "full";
        case PageQuality::thin: return "thin";
        case PageQuality::paywall: return "paywall";
        case PageQuality::challenge_blocked: return "challenge_blocked";
        case PageQuality::error: return "error";
    }
    return "unknown";
}

double PageScorer::score_url(
    std::string_view url,
    std::string_view query,
    std::string_view title,
    std::string_view snippet
) {
    double score = 0.0;
    const std::string url_lower = to_lower_ascii(url);
    const std::string title_lower = to_lower_ascii(title);
    const std::string snippet_lower = to_lower_ascii(snippet);

    // 1. Relevance: match query words against title, url, snippet
    if (!query.empty()) {
        const auto query_words = split_words(query);
        for (const auto& w : query_words) {
            if (title_lower.find(w) != std::string::npos) {
                score += 15.0;
            }
            if (url_lower.find(w) != std::string::npos) {
                score += 8.0;
            }
            if (snippet_lower.find(w) != std::string::npos) {
                score += 5.0;
            }
        }
    }

    // 2. Domain Authority & Trust (+60 to -80)
    if (url_lower.find(".edu") != std::string::npos || url_lower.find(".gov") != std::string::npos) {
        score += 60.0;
    }

    // Official docs / authoritative standards
    if (url_lower.find("cppreference.com") != std::string::npos ||
        url_lower.find("isocpp.org") != std::string::npos ||
        url_lower.find("python.org") != std::string::npos ||
        url_lower.find("learn.microsoft.com") != std::string::npos ||
        url_lower.find("developer.mozilla.org") != std::string::npos ||
        url_lower.find("/docs/") != std::string::npos ||
        url_lower.find("docs.") != std::string::npos) {
        score += 50.0;
    }

    // Arxiv / GitHub / Wikipedia
    if (url_lower.find("arxiv.org") != std::string::npos ||
        url_lower.find("wikipedia.org") != std::string::npos) {
        score += 35.0;
    }
    if (url_lower.find("github.com") != std::string::npos) {
        if (url_lower.find("/issues/") != std::string::npos) {
            score += 5.0; // issues are less authoritative
        } else {
            score += 30.0;
        }
    }

    // HTTPS preference
    if (url_lower.starts_with("https://")) {
        score += 2.0;
    }

    // Noise hosts / forums (-30)
    if (url_lower.find("reddit.com") != std::string::npos ||
        url_lower.find("quora.com") != std::string::npos) {
        score -= 30.0;
    }

    // Content farms / spam / login pages (-50)
    if (url_lower.find("pinterest.com") != std::string::npos ||
        url_lower.find("/login") != std::string::npos ||
        url_lower.find("/signup") != std::string::npos ||
        url_lower.find("/cart") != std::string::npos) {
        score -= 50.0;
    }

    // Academic paywall domains (-80)
    for (const auto& domain : kPaywallDomains) {
        if (url_lower.find(domain) != std::string::npos) {
            score -= 80.0;
            break;
        }
    }

    return score;
}

std::string PageScorer::sanitize_untrusted_text(std::string_view text) {
    std::string out(text);

    // 1. Remove HTML comments <!-- ... -->
    static const std::regex comment_re(R"(<!--[\s\S]*?-->)");
    out = std::regex_replace(out, comment_re, " ");

    // 2. Remove LLM control tokens / prompt delimiters
    constexpr std::string_view kControlTokens[] = {
        "<|im_start|>", "<|im_end|>",
        "<|begin_of_text|>", "<|end_of_text|>",
        "<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>",
        "[INST]", "[/INST]",
        "<<SYS>>", "<</SYS>>",
        "<|user|>", "<|assistant|>", "<|system|>"
    };

    for (const auto& token : kControlTokens) {
        std::size_t pos = 0;
        while ((pos = out.find(token, pos)) != std::string::npos) {
            out.replace(pos, token.size(), "[FILTERED_TOKEN]");
            pos += 16;
        }
    }

    return out;
}

PageAnalysis PageScorer::analyze_page(
    std::string_view url,
    std::string_view markdown_or_text,
    std::string_view raw_html
) {
    PageAnalysis analysis;
    if (markdown_or_text.empty()) {
        analysis.quality = PageQuality::error;
        analysis.log_summary = "empty content";
        return analysis;
    }

    if (markdown_or_text.starts_with("❌") || markdown_or_text.find("❌ Error") != std::string::npos) {
        analysis.quality = PageQuality::error;
        analysis.usable_excerpt = std::string(markdown_or_text.substr(0, kExcerptMax));
        analysis.log_summary = "fetch error";
        return analysis;
    }

    const std::string lower = to_lower_ascii(markdown_or_text);
    const std::string url_lower = to_lower_ascii(url);
    const std::string raw_lower = to_lower_ascii(raw_html);

    // 1. Anti-Bot / Challenge Trap Interceptor
    for (const auto& phrase : kChallengePhrases) {
        if (lower.find(phrase) != std::string::npos || (!raw_lower.empty() && raw_lower.find(phrase) != std::string::npos)) {
            // Check if this looks like a gate rather than a blog post discussing Cloudflare
            if (lower.find("verify you are human") != std::string::npos ||
                lower.find("just a moment...") != std::string::npos ||
                lower.find("ddos protection") != std::string::npos ||
                lower.find("turnstile") != std::string::npos ||
                lower.find("hcaptcha") != std::string::npos ||
                lower.find("checking your browser") != std::string::npos) {
                analysis.quality = PageQuality::challenge_blocked;
                analysis.is_challenge = true;
                analysis.log_summary = "anti-bot challenge intercepted (Cloudflare/Turnstile/hCaptcha)";
                analysis.usable_excerpt = "(Page protected by anti-bot verification challenge. Scraping blocked.)";
                return analysis;
            }
        }
    }

    // 2. Paywall Detection
    int paywall_score = 0;
    for (const auto& domain : kPaywallDomains) {
        if (url_lower.find(domain) != std::string::npos) {
            paywall_score += 4;
            break;
        }
    }
    if (url_lower.find("/login") != std::string::npos || url_lower.find("/subscribe") != std::string::npos) {
        paywall_score += 2;
    }

    int phrase_hits = 0;
    for (const auto& phrase : kPaywallPhrases) {
        if (lower.find(phrase) != std::string::npos) {
            ++phrase_hits;
            paywall_score += 2;
        }
    }

    if (lower.find("subscribe and save") != std::string::npos && lower.find("buy now") != std::string::npos) {
        paywall_score += 2;
    }
    if (lower.find("preview of subscription") != std::string::npos || lower.find("this is a preview") != std::string::npos) {
        paywall_score += 3;
    }

    // 3. Substantive text analysis
    const std::string sub_text = substantive_text(markdown_or_text);
    analysis.substantive_chars = sub_text.size();
    analysis.paywall_score = paywall_score;

    if (paywall_score >= 5) {
        analysis.quality = PageQuality::paywall;
        analysis.usable_excerpt = sub_text.empty() ? std::string(markdown_or_text.substr(0, kExcerptMax)) : sub_text.substr(0, kExcerptMax);
        analysis.log_summary = "paywall detected (score=" + std::to_string(paywall_score) + ")";
        return analysis;
    }

    // 4. Thin / JS-only page detection
    if (analysis.substantive_chars < kThinMinSubstantiveChars ||
        lower.find("enable javascript to run this app") != std::string::npos ||
        lower.find("please enable javascript") != std::string::npos ||
        lower.find("requires javascript to be enabled") != std::string::npos) {
        analysis.quality = PageQuality::thin;
        analysis.usable_excerpt = sub_text.substr(0, std::min(sub_text.size(), kExcerptMax));
        analysis.log_summary = "thin page (chars=" + std::to_string(analysis.substantive_chars) + ")";
        return analysis;
    }

    // 5. Full page -> Sanitize prompt injection delimiters
    analysis.quality = PageQuality::full;
    analysis.sanitized_text = sanitize_untrusted_text(markdown_or_text);
    analysis.usable_excerpt = sub_text.substr(0, std::min(sub_text.size(), kExcerptMax));
    analysis.log_summary = "full page (chars=" + std::to_string(analysis.substantive_chars) + ")";
    return analysis;
}

std::string PageScorer::format_tool_result_for_quality(
    std::string_view url,
    std::string_view full_body,
    const PageAnalysis& analysis
) {
    if (analysis.quality == PageQuality::full) {
        return "--- UNTRUSTED WEB CONTENT FROM " + std::string(url) + " ---\n" +
               (analysis.sanitized_text.empty() ? std::string(full_body) : analysis.sanitized_text) +
               "\n--- END UNTRUSTED WEB CONTENT ---";
    }

    if (analysis.quality == PageQuality::challenge_blocked) {
        return "⚠️ OS Anti-Trap Alert for " + std::string(url) + ":\n" +
               analysis.log_summary + "\n" +
               "Full body withheld. Do not attempt to solve challenges or loop on this URL. "
               "Query open documentation, official repos, or Wikipedia instead.";
    }

    if (analysis.quality == PageQuality::paywall) {
        std::string excerpt = analysis.usable_excerpt.empty() ? "(no substantive excerpt)" : analysis.usable_excerpt;
        return "(OS Note: Page " + std::string(url) + " classified as paywall — " + analysis.log_summary + ".\n" +
               "Full body withheld to prevent context poisoning. Teaser excerpt:\n\n" +
               excerpt + "\n\n" +
               "Use open-access sources, ArXiv preprints, or standard documentation instead.)";
    }

    if (analysis.quality == PageQuality::thin) {
        std::string excerpt = analysis.usable_excerpt.empty() ? "(empty or JS-rendered)" : analysis.usable_excerpt;
        return "(OS Note: Page " + std::string(url) + " classified as thin / JS-only (" +
               std::to_string(analysis.substantive_chars) + " substantive chars).\n" +
               "Excerpt: " + excerpt + "\n" +
               "Full body withheld.)";
    }

    return std::string(full_body);
}

} // namespace aquila::knowledge

