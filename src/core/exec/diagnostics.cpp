#include "aquila/exec/diagnostics.hpp"

#include <algorithm>
#include <map>
#include <regex>

namespace aquila::exec {

namespace {

constexpr std::size_t kMaxContext = 4;
constexpr std::size_t kMaxContextChars = 200;

std::vector<std::string_view> lines_of(std::string_view text) {
    std::vector<std::string_view> out;
    std::size_t start = 0;
    while (start < text.size()) {
        auto nl = text.find('\n', start);
        if (nl == std::string_view::npos) nl = text.size();
        auto line = text.substr(start, nl - start);
        if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
        out.push_back(line);
        start = nl + 1;
    }
    return out;
}

std::string trim(std::string_view s) {
    const auto b = s.find_first_not_of(" \t");
    if (b == std::string_view::npos) return {};
    const auto e = s.find_last_not_of(" \t");
    return std::string(s.substr(b, e - b + 1));
}

int rank(const std::string& severity) {
    if (severity == "error") return 0;
    if (severity == "failure") return 1;
    return 2;
}

// Identity for folding: quoted names and template arguments are ignored, so
// "'missing': is not a member of 'A'" and "... of 'B'" fold together.
std::string normalize(const std::string& msg) {
    std::string out;
    int angle = 0;
    char quote = 0;
    for (const char c : msg) {
        if (quote != 0) {
            if (c == quote) {
                out += c;
                quote = 0;
            }
            continue;
        }
        if (c == '<') {
            if (angle++ == 0) out += "<*";
            continue;
        }
        if (c == '>' && angle > 0) {
            if (--angle == 0) out += '>';
            continue;
        }
        if (angle > 0) continue;
        if (c == '\'' || c == '"') {
            quote = c;
            out += c;
            out += '*';
            continue;
        }
        out += c;
    }
    return out;
}

std::size_t to_size(const std::ssub_match& m) {
    return m.matched ? static_cast<std::size_t>(std::stoul(m.str())) : 0;
}

const std::regex kMsvc(R"re(^(.+?)\((\d+)(?:,(\d+))?\)\s?:\s+(fatal error|error|warning|note)(?:\s+([A-Z]{1,4}\d+))?\s*:\s*(.*)$)re");
const std::regex kMsvcTool(R"re(^(.+?) : (fatal error|error|warning) ([A-Z]{1,4}\d+): (.*)$)re");
const std::regex kClang(R"re(^(.+?):(\d+):(?:(\d+):)? (fatal error|error|warning|note): (.*?)(?: \[(-W[^\]]+)\])?$)re");
const std::regex kCmakeAt(R"re(^CMake (Error|Warning)(?: \(dev\))? at (.+?):(\d+) \((.+?)\):\s*$)re");
const std::regex kCmakeBare(R"re(^CMake (Error|Warning)(?: \(dev\))?: (.*)$)re");
const std::regex kNinja(R"re(^FAILED: (?:\[code=\d+\] )?(.+?)\s*$)re");
const std::regex kPytestFailed(R"re(^FAILED (.+?)::(\S+)(?: - (.*))?$)re");
const std::regex kPytestError(R"re(^ERROR (\S+)(?: - (.*))?$)re");
const std::regex kPytestSummary(R"re(^=*\s*((?:\d+ \w+(?:, )?)+|no tests ran) in [\d.]+s\s*(?:\(.*\))?\s*=*$)re");
const std::regex kPytestCount(R"re((\d+) (passed|failed|errors?|skipped|xfailed|xpassed))re");
const std::regex kPyFrame(R"re(^\s+File "(.+?)", line (\d+)(?:, in .+)?$)re");
const std::regex kPyException(R"re(^([A-Za-z_][\w.]*)(?::\s*(.*))?$)re");

}  // namespace

Diagnosis diagnose(std::string_view log) {
    Diagnosis d;
    std::vector<Diagnostic> raw;
    Diagnostic* last = nullptr;  // the primary diagnostic that notes/context attach to
    const auto lines = lines_of(log);

    const auto add = [&](Diagnostic diag) {
        if (diag.severity == "fatal error") diag.severity = "error";
        if (diag.severity == "error") ++d.errors;
        if (diag.severity == "warning") ++d.warnings;
        raw.push_back(std::move(diag));
        last = &raw.back();
    };
    const auto attach = [&](std::string_view text) {
        if (last == nullptr || last->context.size() >= kMaxContext) return;
        auto t = trim(text);
        if (t.empty()) return;
        if (t.size() > kMaxContextChars) t = t.substr(0, kMaxContextChars) + "...";
        last->context.push_back(std::move(t));
    };

    for (std::size_t i = 0; i < lines.size(); ++i) {
        const std::string line(lines[i]);
        std::smatch m;
        if (line == "Traceback (most recent call last):") {
            Diagnostic diag;
            diag.tool = "python";
            diag.severity = "error";
            std::size_t j = i + 1;
            for (; j < lines.size() && !lines[j].empty() && (lines[j][0] == ' ' || lines[j][0] == '\t'); ++j) {
                std::smatch f;
                const std::string fl(lines[j]);
                if (std::regex_match(fl, f, kPyFrame)) {
                    diag.file = f[1].str();
                    diag.line = to_size(f[2]);
                }
            }
            if (j < lines.size()) {
                std::smatch e;
                const std::string el(lines[j]);
                if (std::regex_match(el, e, kPyException)) {
                    diag.code = e[1].str();
                    diag.message = e[2].matched ? e[2].str() : "";
                }
            }
            add(std::move(diag));
            i = j;
            continue;
        }
        if (std::regex_match(line, m, kMsvc)) {
            if (m[4] == "note") {
                attach(m[6].str());
                continue;
            }
            add({"msvc", m[1].str(), to_size(m[2]), to_size(m[3]), m[4].str(), m[5].str(), m[6].str(), 1, {}});
            continue;
        }
        if (std::regex_match(line, m, kMsvcTool)) {
            add({"msvc", m[1].str(), 0, 0, m[2].str(), m[3].str(), m[4].str(), 1, {}});
            continue;
        }
        if (std::regex_match(line, m, kClang)) {
            if (m[4] == "note") {
                attach(m[5].str());
                continue;
            }
            add({"clang", m[1].str(), to_size(m[2]), to_size(m[3]), m[4].str(), m[6].str(), m[5].str(), 1, {}});
            continue;
        }
        if (std::regex_match(line, m, kCmakeAt)) {
            std::string msg;
            std::size_t j = i + 1;
            for (; j < lines.size() && (lines[j].empty() || lines[j].rfind("  ", 0) == 0); ++j) {
                if (lines[j].empty()) {
                    if (!msg.empty()) break;
                    continue;
                }
                if (!msg.empty()) msg += ' ';
                msg += trim(lines[j]);
            }
            add({"cmake", m[2].str(), to_size(m[3]), 0, m[1] == "Error" ? "error" : "warning", "", msg, 1, {}});
            i = j - 1;
            continue;
        }
        if (std::regex_match(line, m, kCmakeBare)) {
            add({"cmake", "", 0, 0, m[1] == "Error" ? "error" : "warning", "", trim(m[2].str()), 1, {}});
            continue;
        }
        if (std::regex_match(line, m, kNinja)) {
            d.failed_targets.push_back(m[1].str());
            last = nullptr;
            continue;
        }
        if (std::regex_match(line, m, kPytestFailed)) {
            add({"pytest", m[1].str(), 0, 0, "failure", m[2].str(), m[3].matched ? m[3].str() : "", 1, {}});
            continue;
        }
        if (std::regex_match(line, m, kPytestError)) {
            add({"pytest", m[1].str(), 0, 0, "error", "collection", m[2].matched ? m[2].str() : "error during collection", 1, {}});
            continue;
        }
        if (std::regex_match(line, m, kPytestSummary)) {
            d.tests = TestCounts{};
            d.tests.found = true;
            const std::string counts = m[1].str();
            for (std::sregex_iterator it(counts.begin(), counts.end(), kPytestCount), end; it != end; ++it) {
                const auto n = static_cast<std::size_t>(std::stoul((*it)[1].str()));
                const auto kind = (*it)[2].str();
                if (kind == "passed") d.tests.passed = n;
                else if (kind == "failed") d.tests.failed = n;
                else if (kind == "error" || kind == "errors") d.tests.errors = n;
                else if (kind == "skipped") d.tests.skipped = n;
                else if (kind == "xfailed") d.tests.xfailed = n;
                else if (kind == "xpassed") d.tests.xpassed = n;
            }
            continue;
        }
        // Indented lines (caret lines, "with [ ... ]" blocks) belong to the last diagnostic.
        if (!line.empty() && (line[0] == ' ' || line[0] == '\t')) attach(line);
    }

    // Fold identical diagnostics, keeping the first occurrence.
    std::map<std::string, std::size_t> index;
    for (auto& diag : raw) {
        const auto key = diag.file + "|" + std::to_string(diag.line) + "|" + diag.code + "|" + normalize(diag.message);
        const auto it = index.find(key);
        if (it != index.end()) {
            d.blocks[it->second].count += 1;
            continue;
        }
        index.emplace(key, d.blocks.size());
        d.blocks.push_back(std::move(diag));
    }
    std::stable_sort(d.blocks.begin(), d.blocks.end(),
                     [](const Diagnostic& a, const Diagnostic& b) { return rank(a.severity) < rank(b.severity); });
    return d;
}

std::string render(const Diagnosis& d, std::size_t max_blocks, std::size_t max_chars) {
    std::string out = std::to_string(d.errors) + " error(s), " + std::to_string(d.warnings) + " warning(s), " +
                      std::to_string(d.blocks.size()) + " unique\n";
    const auto shown = std::min(max_blocks, d.blocks.size());
    for (std::size_t i = 0; i < shown; ++i) {
        const auto& b = d.blocks[i];
        out += std::to_string(i + 1) + ". ";
        if (!b.file.empty()) {
            out += b.file;
            if (b.line) out += ":" + std::to_string(b.line);
            if (b.col) out += ":" + std::to_string(b.col);
            out += " ";
        }
        out += b.severity;
        if (!b.code.empty()) out += " " + b.code;
        out += ": " + b.message;
        if (b.count > 1) out += "  (x" + std::to_string(b.count) + ", same error)";
        out += "\n";
        for (const auto& c : b.context) out += "   " + c + "\n";
    }
    if (d.blocks.size() > shown) out += "+" + std::to_string(d.blocks.size() - shown) + " more unique diagnostic(s) not shown\n";
    if (!d.failed_targets.empty()) {
        out += "failed targets:";
        for (const auto& t : d.failed_targets) out += " " + t;
        out += "\n";
    }
    if (d.tests.found) {
        out += "tests: " + std::to_string(d.tests.failed) + " failed, " + std::to_string(d.tests.passed) + " passed";
        if (d.tests.errors) out += ", " + std::to_string(d.tests.errors) + " error(s)";
        if (d.tests.skipped) out += ", " + std::to_string(d.tests.skipped) + " skipped";
        if (d.tests.xfailed) out += ", " + std::to_string(d.tests.xfailed) + " xfailed";
        if (d.tests.xpassed) out += ", " + std::to_string(d.tests.xpassed) + " xpassed";
        out += "\n";
    }
    if (out.size() > max_chars) {
        out.resize(max_chars);
        out += "\n...[truncated]";
    }
    return out;
}

}  // namespace aquila::exec
