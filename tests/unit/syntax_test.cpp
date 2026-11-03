#include "aquila/workspace/syntax.hpp"

#include <catch2/catch_test_macros.hpp>

#include <string>
#include <vector>

using namespace aquila::syntax;

namespace {

std::vector<std::string> names(const std::vector<Symbol>& syms) {
    std::vector<std::string> out;
    for (const auto& s : syms) out.push_back(s.kind + ":" + s.name);
    return out;
}

}  // namespace

TEST_CASE("language_for maps extensions case-insensitively") {
    CHECK(language_for("src/a.cpp") == Language::cpp);
    CHECK(language_for("A.HPP") == Language::cpp);
    CHECK(language_for("x.h") == Language::c);
    CHECK(language_for("x.c") == Language::c);
    CHECK(language_for("app.py") == Language::python);
    CHECK(language_for("README.md") == Language::none);
    CHECK(language_for("Makefile") == Language::none);
}

TEST_CASE("analyze: valid sources have no errors; broken ones report the first error") {
    CHECK(analyze(Language::cpp, "int add(int a, int b) { return a + b; }\n").error_count == 0);
    CHECK(analyze(Language::python, "def f(x):\n    return x\n").error_count == 0);
    CHECK(analyze(Language::c, "int main(void) { return 0; }\n").error_count == 0);

    const auto cpp = analyze(Language::cpp, "int add(int a, int b) {\n  return a + ;\n}\n");
    CHECK(cpp.error_count > 0);
    REQUIRE(cpp.first_error.has_value());
    CHECK(cpp.first_error->line == 2);

    const auto py = analyze(Language::python, "def f(x):\n    return (x\n\ndef g():\n    pass\n");
    CHECK(py.error_count > 0);
    REQUIRE(py.first_error.has_value());

    const auto missing_brace = analyze(Language::cpp, "struct S { int x;\nint y();\n");
    CHECK(missing_brace.error_count > 0);

    CHECK(analyze(Language::none, "this is ((( not code").error_count == 0);
}

TEST_CASE("python symbols include nested, decorated and async definitions") {
    const std::string src =
        "import functools\n"
        "\n"
        "@functools.cache\n"
        "def cached(n):\n"
        "    return n\n"
        "\n"
        "class Calc:\n"
        "    def add(self, a, b):\n"
        "        def inner():\n"
        "            return a\n"
        "        return a + b\n"
        "\n"
        "    async def fetch(self):\n"
        "        return 1\n"
        "\n"
        "class Bare:\n"
        "    pass\n";
    const auto syms = symbols(Language::python, src);
    CHECK(names(syms) == std::vector<std::string>{"function:cached", "class:Calc", "function:add",
                                                   "function:inner", "function:fetch", "class:Bare"});
    const auto cached = find_symbol(Language::python, src, "cached");
    REQUIRE(cached.has_value());
    CHECK(cached->start_line == 3);  // decorator included
    CHECK(cached->end_line == 5);
    const auto calc = find_symbol(Language::python, src, "Calc");
    REQUIRE(calc.has_value());
    CHECK(calc->start_line == 7);
    CHECK(calc->end_line == 14);
}

TEST_CASE("cpp symbols: namespaces, classes, out-of-line methods, templates") {
    const std::string src =
        "namespace calc {\n"
        "struct Fwd;\n"
        "class Calc {\n"
        "public:\n"
        "    int add(int a, int b) { return a + b; }\n"
        "    int sub(int a, int b);\n"
        "};\n"
        "int Calc::sub(int a, int b) { return a - b; }\n"
        "template <typename T>\n"
        "T twice(T v) {\n"
        "    return v + v;\n"
        "}\n"
        "enum class Op { add, sub };\n"
        "}\n";
    const auto syms = symbols(Language::cpp, src);
    CHECK(names(syms) == std::vector<std::string>{"namespace:calc", "class:Calc", "function:add",
                                                   "function:Calc::sub", "function:twice", "enum:Op"});
    const auto sub = find_symbol(Language::cpp, src, "sub");
    REQUIRE(sub.has_value());
    CHECK(sub->name == "Calc::sub");
    CHECK(sub->start_line == 8);
    const auto twice = find_symbol(Language::cpp, src, "twice");
    REQUIRE(twice.has_value());
    CHECK(twice->start_line == 9);  // template<> header included
    CHECK(twice->end_line == 12);
    CHECK_FALSE(find_symbol(Language::cpp, src, "Fwd").has_value());  // declaration only
    CHECK_FALSE(find_symbol(Language::cpp, src, "nope").has_value());
}

TEST_CASE("c symbols and pointer-returning functions") {
    const std::string src =
        "struct node { int v; };\n"
        "static struct node *make(int v) { return 0; }\n"
        "int main(void) { return 0; }\n";
    CHECK(names(symbols(Language::c, src)) ==
          std::vector<std::string>{"struct:node", "function:make", "function:main"});
}
