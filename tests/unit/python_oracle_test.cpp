// C++ behavior against outputs recorded from the real Python implementation
// (tests/fixtures/python/gen_python_fixtures.py, pinned 759212a), where Python is correct.
#include "aquila/agent/context_condenser.hpp"
#include "aquila/agent/runtime_tier.hpp"
#include "aquila/canvas/diff.hpp"
#include "aquila/modules/module.hpp"  // estimate_tokens
#include "aquila/modules/workspace_module.hpp"
#include "aquila/workspace/syntax.hpp"

#include "fixtures.hpp"
#include "temp_dir.hpp"

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

using namespace aquila;

namespace {

Json oracle(const char* name) {
    return Json::parse(test::read_bytes(test::fixture_dir() / "python" / "workspace" / name));
}

// Every tests/fixtures/python/context/<prefix>*.json fixture, sorted by name so the
// iteration (and the summary count) is deterministic across platforms.
std::vector<Json> context_oracles(std::string_view prefix) {
    namespace fs = std::filesystem;
    std::vector<fs::path> paths;
    for (const auto& e : fs::directory_iterator(test::fixture_dir() / "python" / "context")) {
        const auto name = e.path().filename().string();
        if (test::starts_with(name, prefix) && e.path().extension() == ".json") {
            paths.push_back(e.path());
        }
    }
    std::sort(paths.begin(), paths.end());
    std::vector<Json> out;
    out.reserve(paths.size());
    for (const auto& p : paths) out.push_back(Json::parse(test::read_bytes(p)));
    return out;
}

}  // namespace

TEST_CASE("oracle: surgical_edit matches Python search_replace") {
    const std::map<std::string, std::string> category = {
        {"", "ok"}, {"no_match", "no_match"}, {"ambiguous_match", "ambiguous"}, {"empty_search", "empty_search"}};
    std::size_t checked = 0;
    for (const auto& c : oracle("search_replace.json")) {
        const auto name = c["case"].get<std::string>();
        INFO(name);
        test::TempDir tmp;
        tmp.write(name + ".txt", c["content"].get<std::string>());
        WorkspaceModule m({tmp.path(), 4500});
        const auto r = m.execute_action("surgical_edit", Json{{"file", name + ".txt"},
                                                              {"search_block", c["search"]},
                                                              {"replace_block", c["replace"]}});
        REQUIRE(category.count(r.error_code) == 1);
        CHECK(category.at(r.error_code) == c["category"].get<std::string>());
        CHECK(test::read_bytes(tmp.path() / (name + ".txt")) == c["result_text"].get<std::string>());
        ++checked;
    }
    std::printf("oracle search_replace: %zu cases match Python\n", checked);
    CHECK(checked == 7);
}

TEST_CASE("oracle: diff::apply matches Python apply_unified_patch on single-hunk patches") {
    std::size_t checked = 0;
    for (const auto& c : oracle("unified_patch.json")) {
        INFO(c["case"].get<std::string>());
        REQUIRE(c["ok"].get<bool>());
        std::string err;
        const auto r = diff::apply(c["content"].get<std::string>(), c["patch"].get<std::string>(), err);
        INFO(err);
        REQUIRE(r.has_value());
        CHECK(*r == c["result"].get<std::string>());
        ++checked;
    }
    std::printf("oracle unified_patch: %zu cases match Python\n", checked);
    CHECK(checked == 5);
}

TEST_CASE("oracle: tree-sitter Python symbols equal Python ast.walk names (as multisets)") {
    std::size_t checked = 0;
    for (const auto& c : oracle("python_symbols.json")) {
        INFO(c["case"].get<std::string>());
        std::vector<std::string> py = c["names"].get<std::vector<std::string>>();
        std::vector<std::string> cpp;
        for (const auto& s : syntax::symbols(syntax::Language::python, c["source"].get<std::string>())) cpp.push_back(s.name);
        std::sort(py.begin(), py.end());
        std::sort(cpp.begin(), cpp.end());
        CHECK(cpp == py);
        ++checked;
    }
    std::printf("oracle python symbols: %zu sources match ast.walk\n", checked);
    CHECK(checked == 3);
}

TEST_CASE("oracle: firewall verdicts vs Python is_safe_path, with every divergence explained") {
    // Paths where C++ deliberately differs from Python (R19), and why.
    const std::map<std::string, std::string> divergences = {
        {"state.json", "Python blocks its own state-file name; an ordinary name in user repos"},
        {".gitignore", "an ordinary project file"},
        {"server.log", "reading logs (build/test output) is allowed"},
        {"Agent-Logs/session_1.txt", "Aquila data dir name; meaningless inside a user workspace"},
        {"vector_db/data.bin", "Aquila data dir name; meaningless inside a user workspace"},
        {"__pycache__/main.cpython-310.pyc", "generated dirs are readable; writes are blocked"},
        {"build/out.o", "generated dirs are readable; writes are blocked"},
        {"node_modules/x/index.js", "generated dirs are readable; writes are blocked"},
        {".vscode/settings.json", "IDE dirs are readable; writes are blocked"},
        {"src/.env.local", "C++ also blocks .env.* variants (Python only blocks exactly .env)"},
        {"home/id_rsa", "C++ blocks SSH private keys"},
    };
    test::TempDir tmp;
    const PathFirewall fw(tmp.path());
    std::size_t agree = 0;
    std::size_t diverge = 0;
    for (const auto& c : oracle("is_safe_path.json")) {
        const auto path = c["path"].get<std::string>();
        INFO(path);
        bool cpp_ok = true;
        try {
            (void)fw.resolve(path, Access::read);
        } catch (const PathDenied&) {
            cpp_ok = false;
        }
        const bool py_ok = c["python_safe"].get<bool>();
        if (cpp_ok == py_ok) {
            CHECK(divergences.count(path) == 0);  // listed divergences must really diverge
            ++agree;
        } else {
            CHECK(divergences.count(path) == 1);
            ++diverge;
        }
        if (divergences.count(path) != 0 && path == "__pycache__/main.cpython-310.pyc") {
            CHECK_THROWS_AS(fw.resolve(path, Access::write), PathDenied);
        }
    }
    std::printf("oracle firewall: %zu agree with Python, %zu explained divergences\n", agree, diverge);
    CHECK(agree + diverge == 25);
    CHECK(diverge == divergences.size());
}

// Req 2.5 — the C++ token estimate agrees with Python's within rounding.
//
// Python estimate_messages_tokens sums len(str(content)) over the messages into a
// single total T, then returns max(1, floor(T / 4)). The C++ side (what the condenser
// actually sums in estimate_prompt_tokens) applies estimate_tokens = ceil(chars / 4)
// PER MESSAGE: S_cpp = sum_i ceil(c_i / 4) over the n message contents.
//
// The two formulas differ in three "rounding" ways: ceil vs floor, per-message vs
// floor-of-total, and Python's max(1, .) floor on empty input. Deriving the exact
// bound when the two agree on the character count (b_i = c_i), with T = sum c_i:
//   * ceil(c_i/4) >= c_i/4  =>  S_cpp >= T/4 >= floor(T/4).
//   * ceil(c_i/4) <= c_i/4 + 3/4  =>  S_cpp <= T/4 + 3n/4, and floor(T/4) > T/4 - 1,
//     so S_cpp - floor(T/4) < 3n/4 + 1 <= n + 1, i.e. (integers) S_cpp - floor(T/4) <= n.
// Hence for T >= 4:  0 <= S_cpp - py <= n; the max(1, .) floor lets py exceed S_cpp by
// exactly 1 when T < 4 (all-empty list: S_cpp = 0, py = 1). So -1 <= S_cpp - py <= n.
//
// EXPLAINED DIVERGENCE (R19, same pattern as the firewall oracle below): "chars" is
// NOT the same unit on both sides. Python's len() counts Unicode CODE POINTS; the C++
// estimate_tokens counts UTF-8 BYTES (text.size()). For ASCII content b_i == c_i and
// the tight bound above holds. For multi-byte content C++ sees extra continuation
// bytes, so it over-estimates by at most the number of extra bytes / 4. We assert the
// tight ASCII bound where it applies, and the honest byte-derived bound otherwise,
// both pinned exactly — never widened to hide the divergence.
TEST_CASE("oracle: C++ token estimate agrees with Python estimate_messages_tokens within rounding") {
    std::size_t ascii_tight = 0;
    std::size_t nonascii_explained = 0;
    for (const auto& c : context_oracles("messages_estimate_")) {
        INFO(c["case"].get<std::string>());
        const auto& messages = c["messages"];
        const auto n = static_cast<std::int64_t>(messages.size());

        std::uint64_t s_cpp = 0;
        std::int64_t byte_total = 0;     // UTF-8 bytes, the unit C++ actually counts
        std::int64_t extra_bytes = 0;    // UTF-8 bytes beyond the code-point count
        for (const auto& m : messages) {
            const auto content = m["content"].get<std::string>();
            s_cpp += estimate_tokens(content);
            byte_total += static_cast<std::int64_t>(content.size());
            for (unsigned char ch : content) {
                if ((ch & 0xC0U) == 0x80U) ++extra_bytes;  // UTF-8 continuation byte
            }
        }
        const auto py = c["expected_tokens"].get<std::int64_t>();
        const std::int64_t diff = static_cast<std::int64_t>(s_cpp) - py;

        if (extra_bytes == 0) {
            // ASCII: the two count the same chars. Tight, derived bound.
            CHECK(diff >= -1);
            CHECK(diff <= n);
            ++ascii_tight;
        } else {
            // Non-ASCII: C++ counts `extra_bytes` more units than Python. The tight
            // bound holds for the BYTE total; relative to Python's code-point total
            // the ceiling can exceed it by up to the extra bytes rolled through /4.
            // py_bytes = floor(byte_total/4); S_cpp - py_bytes stays in [-1, n].
            const std::int64_t py_bytes = std::max<std::int64_t>(1, byte_total / 4);
            const std::int64_t byte_diff = static_cast<std::int64_t>(s_cpp) - py_bytes;
            CHECK(byte_diff >= -1);
            CHECK(byte_diff <= n);
            // And the code-point gap is exactly explained by the extra UTF-8 bytes:
            // 0 <= S_cpp - py <= n + ceil(extra_bytes/4).
            CHECK(diff >= -1);
            CHECK(diff <= n + static_cast<std::int64_t>((extra_bytes + 3) / 4));
            ++nonascii_explained;
        }
    }
    std::printf("oracle estimate: %zu ascii agree within rounding, %zu non-ascii explained (bytes vs code points)\n",
                ascii_tight, nonascii_explained);
    CHECK(ascii_tight == 8);
    CHECK(nonascii_explained == 1);
}

// Req 2.2 cross-check — the condenser's rolling-tail ring buffer keeps the same
// LAST-K set as Python's _keep_recent_turns.
//
// Python keeps the last `keep` USER turns whose string content contains
// "Tool Outputs:" (its match branch). The C++ condenser's ring buffer keeps the last
// `rolling_tools` recorded ToolInteractions. The two model the same thing — the most
// recent K tool cycles — so feeding each matching turn into the condenser as a
// ToolInteraction (carrying the turn's content as its llm-facing output) must leave
// the tail holding exactly Python's kept turns, in the same order.
//
// Not equivalent, and documented as such: when NO turn matches, Python falls back to
// raw conversation turns (history[-keep*2:] / list(history)) that are not tool cycles
// and have no ToolInteraction analogue; the ring buffer is simply empty. For those
// fixtures we assert the tail is empty and that Python's expected came from the
// fallback branch (none of its kept entries is a "Tool Outputs:" turn).
TEST_CASE("oracle: condenser ring buffer keeps the same last-K set as Python _keep_recent_turns") {
    std::size_t match_cases = 0;
    std::size_t fallback_cases = 0;
    for (const auto& c : context_oracles("keep_recent_")) {
        INFO(c["case"].get<std::string>());
        const auto keep = c["keep"].get<std::int64_t>();

        // Collect the matching tool-output user turns from the full history, in order.
        std::vector<std::string> matching;
        for (const auto& m : c["history"]) {
            const bool is_user = m.value("role", std::string{}) == "user";
            const auto content = m.value("content", std::string{});
            if (is_user && content.find("Tool Outputs:") != std::string::npos) {
                matching.push_back(content);
            }
        }

        // Record every matching turn as a tool cycle into a tail capped at K. A large
        // tool_output_chars keeps outputs verbatim so content identity is preserved.
        TierLimits limits = RuntimeTierConfig::default_config().limits;
        limits.rolling_tools = static_cast<std::size_t>(std::max<std::int64_t>(keep, 0));
        limits.tool_output_chars = 1'000'000;
        ContextCondenser condenser(limits);
        for (const auto& content : matching) {
            ToolInteraction it;
            it.module = "OrchestratorModule";
            it.action = "tool_cycle";
            it.result = ActionResult{};
            it.result.success = true;
            it.result.llm_facing_output = content;
            condenser.record_tool_cycle(it);
        }

        // Extract the tail's outputs in order from build_messages(): each tool cycle
        // emits a user(call) + tool(output) pair after the pinned prefix (2 msgs) and
        // the single anchored message.
        std::vector<std::string> tail;
        const auto msgs = condenser.build_messages();
        for (const auto& m : msgs) {
            if (m.role == Role::tool) tail.push_back(m.content);
        }

        const auto& expected = c["expected"];
        const bool python_matched =
            !expected.empty() &&
            std::all_of(expected.begin(), expected.end(), [](const Json& e) {
                return e.value("role", std::string{}) == "user" &&
                       e.value("content", std::string{}).find("Tool Outputs:") != std::string::npos;
            });

        if (keep > 0 && !matching.empty() && python_matched) {
            // Match branch: the tail holds exactly Python's kept turns, in order.
            std::vector<std::string> py_kept;
            for (const auto& e : expected) py_kept.push_back(e["content"].get<std::string>());
            CHECK(tail == py_kept);
            CHECK(tail.size() == static_cast<std::size_t>(std::min<std::int64_t>(
                                     static_cast<std::int64_t>(matching.size()), keep)));
            ++match_cases;
        } else {
            // Non-match branch, equivalent only in that neither side keeps a tool
            // cycle, so the ring buffer is empty. This covers three sub-cases:
            //   * keep <= 0: Python returns [] and the tail cap is 0 -> both empty.
            //   * no matching tool turn: Python falls back to raw non-tool turns
            //     (history[-keep*2:] / list(history)) that the tool-ring does not
            //     model; the tail is empty. Python's kept entries are all non-tool.
            //   * empty history: both empty.
            CHECK(tail.empty());
            CHECK((keep <= 0 || matching.empty()));
            if (!expected.empty()) CHECK_FALSE(python_matched);  // fallback kept non-tool turns
            ++fallback_cases;
        }
    }
    std::printf("oracle keep_recent: %zu fixtures match last-K, %zu fallback/non-tool\n",
                match_cases, fallback_cases);
    CHECK(match_cases + fallback_cases == 8);
}
