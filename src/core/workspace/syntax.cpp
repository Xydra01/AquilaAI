#include "aquila/workspace/syntax.hpp"

#include <tree_sitter/api.h>

#include <algorithm>
#include <cctype>
#include <cstring>
#include <memory>

extern "C" {
const TSLanguage* tree_sitter_c(void);
const TSLanguage* tree_sitter_cpp(void);
const TSLanguage* tree_sitter_python(void);
}

namespace aquila::syntax {

namespace {

struct ParserDeleter {
    void operator()(TSParser* p) const noexcept { ts_parser_delete(p); }
};
struct TreeDeleter {
    void operator()(TSTree* t) const noexcept { ts_tree_delete(t); }
};
using ParserPtr = std::unique_ptr<TSParser, ParserDeleter>;
using TreePtr = std::unique_ptr<TSTree, TreeDeleter>;

const TSLanguage* grammar(Language lang) noexcept {
    switch (lang) {
        case Language::c: return tree_sitter_c();
        case Language::cpp: return tree_sitter_cpp();
        case Language::python: return tree_sitter_python();
        case Language::none: break;
    }
    return nullptr;
}

TreePtr parse(Language lang, std::string_view text) {
    const TSLanguage* g = grammar(lang);
    if (g == nullptr) return nullptr;
    ParserPtr parser(ts_parser_new());
    if (!ts_parser_set_language(parser.get(), g)) return nullptr;
    return TreePtr(ts_parser_parse_string(parser.get(), nullptr, text.data(), static_cast<uint32_t>(text.size())));
}

std::string node_text(TSNode n, std::string_view text) {
    const auto b = ts_node_start_byte(n);
    const auto e = ts_node_end_byte(n);
    return std::string(text.substr(b, e - b));
}

bool is(TSNode n, const char* type) {
    return std::strcmp(ts_node_type(n), type) == 0;
}

// Walks every node in document order.
template <class Visit>
void walk(TSNode root, Visit&& visit) {
    TSTreeCursor cursor = ts_tree_cursor_new(root);
    for (;;) {
        visit(ts_tree_cursor_current_node(&cursor));
        if (ts_tree_cursor_goto_first_child(&cursor)) continue;
        while (!ts_tree_cursor_goto_next_sibling(&cursor)) {
            if (!ts_tree_cursor_goto_parent(&cursor)) {
                ts_tree_cursor_delete(&cursor);
                return;
            }
        }
    }
}

// Innermost declarator name of a C/C++ function_definition.
std::string c_function_name(TSNode def, std::string_view text) {
    TSNode d = ts_node_child_by_field_name(def, "declarator", 10);
    while (!ts_node_is_null(d)) {
        if (is(d, "function_declarator")) {
            const TSNode inner = ts_node_child_by_field_name(d, "declarator", 10);
            return ts_node_is_null(inner) ? std::string{} : node_text(inner, text);
        }
        // pointer_declarator, reference_declarator, ... wrap the function declarator
        TSNode next = ts_node_child_by_field_name(d, "declarator", 10);
        if (ts_node_is_null(next)) {
            for (uint32_t i = 0; i < ts_node_named_child_count(d); ++i) {
                const TSNode c = ts_node_named_child(d, i);
                if (is(c, "function_declarator")) {
                    next = c;
                    break;
                }
            }
        }
        d = next;
    }
    return {};
}

// Decorators (Python) and template<> headers (C++) belong to the symbol's range.
TSNode outer_wrapper(TSNode n) {
    TSNode parent = ts_node_parent(n);
    while (!ts_node_is_null(parent) && (is(parent, "decorated_definition") || is(parent, "template_declaration"))) {
        n = parent;
        parent = ts_node_parent(n);
    }
    return n;
}

std::optional<Symbol> symbol_at(Language lang, TSNode n, std::string_view text) {
    Symbol s;
    if (lang == Language::python) {
        if (is(n, "function_definition")) s.kind = "function";
        else if (is(n, "class_definition")) s.kind = "class";
        else return std::nullopt;
        const TSNode name = ts_node_child_by_field_name(n, "name", 4);
        if (ts_node_is_null(name)) return std::nullopt;
        s.name = node_text(name, text);
    } else {
        if (is(n, "function_definition")) {
            s.kind = "function";
            s.name = c_function_name(n, text);
        } else if (is(n, "class_specifier") || is(n, "struct_specifier") || is(n, "enum_specifier") ||
                   is(n, "namespace_definition")) {
            const std::string_view t = ts_node_type(n);
            s.kind = t == "class_specifier" ? "class" : t == "struct_specifier" ? "struct"
                     : t == "enum_specifier" ? "enum" : "namespace";
            if (ts_node_is_null(ts_node_child_by_field_name(n, "body", 4))) return std::nullopt;  // declaration only
            const TSNode name = ts_node_child_by_field_name(n, "name", 4);
            if (ts_node_is_null(name)) return std::nullopt;  // anonymous
            s.name = node_text(name, text);
        } else {
            return std::nullopt;
        }
        if (s.name.empty()) return std::nullopt;
    }
    const TSNode outer = outer_wrapper(n);
    s.start_line = ts_node_start_point(outer).row + 1;
    s.end_line = ts_node_end_point(outer).row + 1;
    return s;
}

}  // namespace

Language language_for(std::string_view path) noexcept {
    const auto dot = path.rfind('.');
    if (dot == std::string_view::npos) return Language::none;
    std::string ext(path.substr(dot));
    std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (ext == ".c" || ext == ".h") return Language::c;
    if (ext == ".cc" || ext == ".cpp" || ext == ".cxx" || ext == ".hpp" || ext == ".hh" || ext == ".hxx") return Language::cpp;
    if (ext == ".py" || ext == ".pyw") return Language::python;
    return Language::none;
}

std::string_view to_string(Language lang) noexcept {
    switch (lang) {
        case Language::c: return "c";
        case Language::cpp: return "cpp";
        case Language::python: return "python";
        case Language::none: break;
    }
    return "none";
}

Analysis analyze(Language lang, std::string_view text) {
    Analysis a;
    const auto tree = parse(lang, text);
    if (!tree) return a;
    const TSNode root = ts_tree_root_node(tree.get());
    if (!ts_node_has_error(root)) return a;
    walk(root, [&](TSNode n) {
        if (ts_node_is_error(n) || ts_node_is_missing(n)) {
            ++a.error_count;
            if (!a.first_error) {
                const TSPoint p = ts_node_start_point(n);
                a.first_error = Position{p.row + 1, p.column + 1};
            }
        }
    });
    return a;
}

std::vector<Symbol> symbols(Language lang, std::string_view text) {
    std::vector<Symbol> out;
    const auto tree = parse(lang, text);
    if (!tree) return out;
    walk(ts_tree_root_node(tree.get()), [&](TSNode n) {
        if (auto s = symbol_at(lang, n, text)) out.push_back(std::move(*s));
    });
    return out;
}

std::optional<Symbol> find_symbol(Language lang, std::string_view text, std::string_view name) {
    for (auto& s : symbols(lang, text)) {
        const auto sep = s.name.rfind("::");
        const std::string_view last = sep == std::string::npos ? std::string_view(s.name)
                                                               : std::string_view(s.name).substr(sep + 2);
        if (s.name == name || last == name) return std::move(s);
    }
    return std::nullopt;
}

}  // namespace aquila::syntax
