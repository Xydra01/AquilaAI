#pragma once

#include <string>
#include <string_view>

namespace aquila::knowledge {

struct CleanedHtml {
    std::string title;
    std::string text;
};

class HtmlCleaner {
public:
    static CleanedHtml clean(std::string_view html);
    static std::string decode_entities(std::string_view text);
};

} // namespace aquila::knowledge

