#include "aquila/knowledge/html_cleaner.hpp"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <string>
#include <unordered_set>
#include <vector>

namespace aquila::knowledge {

namespace {

void append_utf8(std::string& out, uint32_t cp) {
    if (cp == 0 || cp > 0x10FFFF) {
        return;
    }
    if (cp <= 0x7F) {
        out.push_back(static_cast<char>(cp));
    } else if (cp <= 0x7FF) {
        out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp <= 0xFFFF) {
        out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
}

std::string to_lower_ascii(std::string_view s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

const std::unordered_set<std::string> kIgnoredTags = {
    "script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"
};

const std::unordered_set<std::string> kBlockTags = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br",
    "article", "section", "blockquote", "hr", "pre"
};

} // namespace

std::string HtmlCleaner::decode_entities(std::string_view text) {
    std::string out;
    out.reserve(text.size());

    const std::size_t n = text.size();
    std::size_t i = 0;
    while (i < n) {
        if (text[i] != '&') {
            out.push_back(text[i++]);
            continue;
        }

        // Potential entity
        const std::size_t semi = text.find(';', i + 1);
        if (semi == std::string_view::npos || semi - i > 12) {
            out.push_back(text[i++]);
            continue;
        }

        const auto entity = text.substr(i + 1, semi - (i + 1));
        if (entity == "quot") {
            out.push_back('"');
            i = semi + 1;
        } else if (entity == "amp") {
            out.push_back('&');
            i = semi + 1;
        } else if (entity == "lt") {
            out.push_back('<');
            i = semi + 1;
        } else if (entity == "gt") {
            out.push_back('>');
            i = semi + 1;
        } else if (entity == "apos" || entity == "#39") {
            out.push_back('\'');
            i = semi + 1;
        } else if (entity == "nbsp") {
            out.push_back(' ');
            i = semi + 1;
        } else if (entity == "copy") {
            out.append("(c)");
            i = semi + 1;
        } else if (!entity.empty() && entity[0] == '#') {
            uint32_t cp = 0;
            bool ok = false;
            if (entity.size() > 1 && (entity[1] == 'x' || entity[1] == 'X')) {
                auto hex_part = entity.substr(2);
                auto res = std::from_chars(hex_part.data(), hex_part.data() + hex_part.size(), cp, 16);
                ok = (res.ec == std::errc{});
            } else {
                auto dec_part = entity.substr(1);
                auto res = std::from_chars(dec_part.data(), dec_part.data() + dec_part.size(), cp, 10);
                ok = (res.ec == std::errc{});
            }
            if (ok) {
                append_utf8(out, cp);
                i = semi + 1;
            } else {
                out.push_back(text[i++]);
            }
        } else {
            // Unknown entity, output as-is
            out.push_back(text[i++]);
        }
    }
    return out;
}

CleanedHtml HtmlCleaner::clean(std::string_view html) {
    CleanedHtml result;
    std::string text_raw;
    std::string title_raw;
    text_raw.reserve(html.size());

    std::vector<std::string> ignored_tag_stack;
    bool in_title = false;

    const std::size_t n = html.size();
    std::size_t i = 0;

    auto ensure_break = [&]() {
        if (!text_raw.empty() && text_raw.back() != '\n') {
            text_raw.push_back('\n');
        }
    };

    while (i < n) {
        // Comment check: <!-- ... -->
        if (i + 3 < n && html[i] == '<' && html[i + 1] == '!' && html[i + 2] == '-' && html[i + 3] == '-') {
            const auto end_comment = html.find("-->", i + 4);
            if (end_comment == std::string_view::npos) {
                break; // Unclosed comment, ignore rest of document
            }
            i = end_comment + 3;
            continue;
        }

        // Tag check: < ... >
        if (html[i] == '<') {
            // Scan tag name and attributes
            std::size_t tag_start = i + 1;
            bool is_closing = false;
            if (tag_start < n && html[tag_start] == '/') {
                is_closing = true;
                ++tag_start;
            }

            // Find tag name
            std::size_t name_end = tag_start;
            while (name_end < n && !std::isspace(static_cast<unsigned char>(html[name_end])) &&
                   html[name_end] != '>' && html[name_end] != '/') {
                ++name_end;
            }
            std::string tag_name = to_lower_ascii(html.substr(tag_start, name_end - tag_start));

            // Scan to matching '>' respecting quotes
            std::size_t tag_end = name_end;
            char in_quote = '\0';
            while (tag_end < n) {
                char c = html[tag_end];
                if (in_quote) {
                    if (c == in_quote) {
                        in_quote = '\0';
                    }
                } else {
                    if (c == '"' || c == '\'') {
                        in_quote = c;
                    } else if (c == '>') {
                        break;
                    }
                }
                ++tag_end;
            }

            if (tag_end >= n) {
                // Unclosed tag at end of file
                break;
            }

            // Process tag semantics
            if (tag_name == "title") {
                if (is_closing) {
                    in_title = false;
                } else {
                    in_title = true;
                }
            } else if (kIgnoredTags.contains(tag_name)) {
                if (is_closing) {
                    auto it = std::find(ignored_tag_stack.rbegin(), ignored_tag_stack.rend(), tag_name);
                    if (it != ignored_tag_stack.rend()) {
                        ignored_tag_stack.erase(std::next(it).base());
                    }
                } else {
                    ignored_tag_stack.push_back(tag_name);
                }
            } else if (ignored_tag_stack.empty() && kBlockTags.contains(tag_name)) {
                ensure_break();
            }

            i = tag_end + 1;
            continue;
        }

        // Regular character
        char c = html[i++];
        if (in_title) {
            title_raw.push_back(c);
        } else if (ignored_tag_stack.empty()) {
            text_raw.push_back(c);
        }
    }

    // Decode entities
    std::string decoded_text = decode_entities(text_raw);
    std::string decoded_title = decode_entities(title_raw);

    // Normalize whitespace in text:
    // Collapse horizontal whitespace (spaces/tabs), collapse > 2 consecutive newlines
    std::string normalized;
    normalized.reserve(decoded_text.size());

    int consecutive_newlines = 0;
    bool in_whitespace = false;

    for (char c : decoded_text) {
        if (c == '\r') {
            continue;
        }
        if (c == '\n') {
            if (consecutive_newlines < 2) {
                normalized.push_back('\n');
                ++consecutive_newlines;
            }
            in_whitespace = false;
        } else if (std::isspace(static_cast<unsigned char>(c))) {
            if (!in_whitespace && consecutive_newlines == 0 && !normalized.empty() && normalized.back() != '\n') {
                normalized.push_back(' ');
                in_whitespace = true;
            }
        } else {
            normalized.push_back(c);
            consecutive_newlines = 0;
            in_whitespace = false;
        }
    }

    // Trim leading/trailing whitespace
    auto trim_s = [](std::string& s) {
        while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
            s.erase(s.begin());
        }
        while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
            s.pop_back();
        }
    };

    trim_s(normalized);
    trim_s(decoded_title);

    result.text = std::move(normalized);
    result.title = std::move(decoded_title);
    return result;
}

} // namespace aquila::knowledge

