#include "aquila/canvas/diff.hpp"

#include <algorithm>
#include <cstdlib>
#include <vector>

namespace aquila::diff {

namespace {

struct Lines {
    std::vector<std::string_view> lines;
    bool final_newline = true;  // false when the text ends without '\n'
};

Lines split(std::string_view text) {
    Lines out;
    std::size_t start = 0;
    while (start < text.size()) {
        const auto nl = text.find('\n', start);
        if (nl == std::string_view::npos) {
            out.lines.push_back(text.substr(start));
            out.final_newline = false;
            break;
        }
        out.lines.push_back(text.substr(start, nl - start));
        start = nl + 1;
    }
    return out;
}

enum class Op { equal, remove, insert };
struct Edit {
    Op op;
    std::size_t a;  // old index (for inserts: the old position the line goes before)
    std::size_t b;  // new index (for removes: the new position)
};

std::size_t at(long i) {
    return static_cast<std::size_t>(i);
}

// Myers' O((N+M)D) shortest edit script; V is saved per step for backtracking.
std::vector<Edit> myers(const std::vector<std::string_view>& a, const std::vector<std::string_view>& b) {
    const long n = static_cast<long>(a.size());
    const long m = static_cast<long>(b.size());
    const long off = n + m + 1;
    std::vector<long> v(at(2 * off + 1), 0);
    std::vector<std::vector<long>> trace;
    for (long d = 0; d <= n + m; ++d) {
        trace.push_back(v);
        bool done = false;
        for (long k = -d; k <= d; k += 2) {
            long x = (k == -d || (k != d && v[at(off + k - 1)] < v[at(off + k + 1)])) ? v[at(off + k + 1)]
                                                                                        : v[at(off + k - 1)] + 1;
            long y = x - k;
            while (x < n && y < m && a[at(x)] == b[at(y)]) {
                ++x;
                ++y;
            }
            v[at(off + k)] = x;
            if (x >= n && y >= m) {
                done = true;
                break;
            }
        }
        if (done) break;
    }

    std::vector<Edit> edits;
    long x = n;
    long y = m;
    for (long d = static_cast<long>(trace.size()) - 1; d > 0; --d) {
        const auto& vd = trace[at(d)];
        const long k = x - y;
        const bool down = k == -d || (k != d && vd[at(off + k - 1)] < vd[at(off + k + 1)]);
        const long pk = down ? k + 1 : k - 1;
        const long px = vd[at(off + pk)];
        const long py = px - pk;
        while (x > px && y > py) {
            --x;
            --y;
            edits.push_back({Op::equal, at(x), at(y)});
        }
        if (down) {
            --y;
            edits.push_back({Op::insert, at(x), at(y)});
        } else {
            --x;
            edits.push_back({Op::remove, at(x), at(y)});
        }
    }
    while (x > 0 && y > 0) {
        --x;
        --y;
        edits.push_back({Op::equal, at(x), at(y)});
    }
    std::reverse(edits.begin(), edits.end());
    return edits;
}

std::string range(std::size_t start, std::size_t count) {
    // An empty range names the line before it (0 at the top of the file).
    const auto first = count == 0 ? start : start + 1;
    return count == 1 ? std::to_string(first) : std::to_string(first) + "," + std::to_string(count);
}

}  // namespace

std::string unified(std::string_view old_text, std::string_view new_text, std::string_view old_label,
                    std::string_view new_label, int context) {
    if (old_text == new_text) return {};
    const auto a = split(old_text);
    const auto b = split(new_text);
    const auto edits = myers(a.lines, b.lines);
    const auto ctx = static_cast<std::size_t>(std::max(0, context));

    const auto a_nonl = [&](const Edit& e) { return e.a + 1 == a.lines.size() && !a.final_newline; };
    const auto b_nonl = [&](const Edit& e) { return e.b + 1 == b.lines.size() && !b.final_newline; };
    // Equal text whose final-newline state differs is still a change.
    const auto is_change = [&](const Edit& e) { return e.op != Op::equal || a_nonl(e) != b_nonl(e); };

    std::string out = "--- " + std::string(old_label) + "\n+++ " + std::string(new_label) + "\n";
    const auto line = [&](char tag, std::string_view text, bool nonl) {
        out += tag;
        out += text;
        out += '\n';
        if (nonl) out += "\\ No newline at end of file\n";
    };

    const std::size_t n = edits.size();
    std::size_t i = 0;
    for (;;) {
        std::size_t first = i;
        while (first < n && !is_change(edits[first])) ++first;
        if (first == n) break;

        // Extend through changes separated by at most 2*ctx unchanged lines.
        std::size_t last = first;
        std::size_t j = first;
        for (;;) {
            while (j < n && is_change(edits[j])) last = j++;
            std::size_t k = j;
            while (k < n && !is_change(edits[k])) ++k;
            if (k < n && k - j <= 2 * ctx) {
                j = k;
                continue;
            }
            break;
        }
        const std::size_t begin = std::max(i, first >= ctx ? first - ctx : 0);
        const std::size_t end = std::min(n, last + 1 + ctx);

        std::size_t a_count = 0;
        std::size_t b_count = 0;
        for (std::size_t h = begin; h < end; ++h) {
            if (edits[h].op != Op::insert) ++a_count;
            if (edits[h].op != Op::remove) ++b_count;
        }
        out += "@@ -" + range(edits[begin].a, a_count) + " +" + range(edits[begin].b, b_count) + " @@\n";
        for (std::size_t h = begin; h < end; ++h) {
            const auto& e = edits[h];
            switch (e.op) {
                case Op::equal:
                    if (a_nonl(e) == b_nonl(e)) {
                        line(' ', a.lines[e.a], a_nonl(e));
                    } else {
                        line('-', a.lines[e.a], a_nonl(e));
                        line('+', b.lines[e.b], b_nonl(e));
                    }
                    break;
                case Op::remove: line('-', a.lines[e.a], a_nonl(e)); break;
                case Op::insert: line('+', b.lines[e.b], b_nonl(e)); break;
            }
        }
        i = end;
    }
    return out;
}

std::optional<std::string> apply(std::string_view text, std::string_view patch, std::string& error) {
    const auto src = split(text);
    const auto pl = split(patch);
    std::vector<std::string_view> out;
    bool final_nl = src.final_newline;
    std::size_t pos = 0;  // next unconsumed source line
    bool any_hunk = false;

    std::size_t i = 0;
    while (i < pl.lines.size()) {
        const auto header = pl.lines[i];
        if (header.substr(0, 3) != "@@ ") {
            ++i;
            continue;
        }
        any_hunk = true;
        const auto minus = header.find(" -");
        const auto plus = header.find(" +", minus == std::string_view::npos ? 0 : minus + 2);
        if (minus == std::string_view::npos || plus == std::string_view::npos) {
            error = "malformed hunk header: " + std::string(header);
            return std::nullopt;
        }
        const std::string spec(header.substr(minus + 2, plus - minus - 2));
        const auto comma = spec.find(',');
        const long start = std::strtol(spec.c_str(), nullptr, 10);
        const long count = comma == std::string::npos ? 1 : std::strtol(spec.c_str() + comma + 1, nullptr, 10);
        const auto target = static_cast<std::size_t>(count == 0 ? start : start - 1);
        if (start < 0 || target < pos || target > src.lines.size()) {
            error = "hunk out of order or out of range: " + std::string(header);
            return std::nullopt;
        }
        while (pos < target) out.push_back(src.lines[pos++]);

        bool last_out_nl = true;  // newline state of the last line this hunk emitted
        ++i;
        while (i < pl.lines.size() && pl.lines[i].substr(0, 3) != "@@ ") {
            const auto h = pl.lines[i];
            if (h.empty()) {
                error = "empty line inside hunk";
                return std::nullopt;
            }
            const char tag = h[0];
            const auto body = h.substr(1);
            if (tag == '\\') {
                const auto prev = pl.lines[i - 1];
                if (!prev.empty() && prev[0] != '-') last_out_nl = false;
            } else if (tag == ' ' || tag == '-') {
                if (pos >= src.lines.size() || src.lines[pos] != body) {
                    error = std::string(tag == ' ' ? "context" : "removed line") + " mismatch at line " +
                            std::to_string(pos + 1);
                    return std::nullopt;
                }
                ++pos;
                if (tag == ' ') {
                    out.push_back(body);
                    last_out_nl = true;
                }
            } else if (tag == '+') {
                out.push_back(body);
                last_out_nl = true;
            } else {
                break;  // next file header or trailing text
            }
            ++i;
        }
        if (pos == src.lines.size()) final_nl = last_out_nl;
    }
    if (!any_hunk) {
        error = "patch has no hunks";
        return std::nullopt;
    }
    if (pos < src.lines.size()) {
        while (pos < src.lines.size()) out.push_back(src.lines[pos++]);
        final_nl = src.final_newline;
    }

    std::string result;
    for (std::size_t k = 0; k < out.size(); ++k) {
        result += out[k];
        if (k + 1 < out.size() || final_nl) result += '\n';
    }
    return result;
}

}  // namespace aquila::diff
