#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::knowledge {

enum class PageQuality {
    full,
    thin,
    paywall,
    challenge_blocked,
    error
};

[[nodiscard]] std::string_view to_string(PageQuality quality) noexcept;

struct PageAnalysis {
    PageQuality quality{PageQuality::full};
    std::string usable_excerpt;
    std::string log_summary;
    int paywall_score{0};
    std::size_t substantive_chars{0};
    bool is_challenge{false};
    std::string sanitized_text;

    [[nodiscard]] bool is_usable_for_context() const noexcept {
        return quality == PageQuality::full || quality == PageQuality::thin;
    }
};

class PageScorer {
public:
    // Scores URL relevancy and domain authority/reliability.
    // Higher score = higher priority for agent retrieval.
    static double score_url(
        std::string_view url,
        std::string_view query = "",
        std::string_view title = "",
        std::string_view snippet = ""
    );

    // Analyzes scraped page content, intercepts paywalls and anti-bot challenge traps,
    // detects thin pages, and sanitizes prompt injection delimiters.
    static PageAnalysis analyze_page(
        std::string_view url,
        std::string_view markdown_or_text,
        std::string_view raw_html = ""
    );

    // Formats tool output string depending on quality (withholds paywall/thin bodies).
    static std::string format_tool_result_for_quality(
        std::string_view url,
        std::string_view full_body,
        const PageAnalysis& analysis
    );

    // Strips prompt injections, LLM control tokens, and HTML comments from scraped web text.
    static std::string sanitize_untrusted_text(std::string_view text);
};

} // namespace aquila::knowledge

