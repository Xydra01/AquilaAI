#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::syntax {

enum class Language { none, c, cpp, python };

// By file extension: .c .h -> c; .cc .cpp .cxx .hpp .hh .hxx -> cpp; .py .pyw -> python.
Language language_for(std::string_view path) noexcept;
std::string_view to_string(Language lang) noexcept;

struct Position {
    std::size_t line = 0;  // 1-based
    std::size_t col = 0;   // 1-based, in bytes
};

struct Analysis {
    std::size_t error_count = 0;  // ERROR and MISSING nodes
    std::optional<Position> first_error;
};

struct Symbol {
    std::string name;  // as written, e.g. "Calc::add" for an out-of-line method
    std::string kind;  // function, class, struct, namespace, enum
    std::size_t start_line = 0;  // 1-based, includes decorators / template<> headers
    std::size_t end_line = 0;
};

// Parses `text` with the grammar for `lang`. Language::none yields an empty Analysis.
Analysis analyze(Language lang, std::string_view text);

// Definitions in document order (nested ones included).
std::vector<Symbol> symbols(Language lang, std::string_view text);

// First symbol whose name equals `name` or whose last `::` component equals it.
std::optional<Symbol> find_symbol(Language lang, std::string_view text, std::string_view name);

}  // namespace aquila::syntax
