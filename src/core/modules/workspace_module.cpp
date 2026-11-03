#include "aquila/modules/workspace_module.hpp"

#include "aquila/workspace/syntax.hpp"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <system_error>

namespace aquila {

namespace fs = std::filesystem;

namespace {

constexpr std::size_t kMaxRegionLines = 150;
constexpr std::size_t kMaxOutlineFiles = 200;
constexpr std::size_t kMaxOutlineSymbols = 12;

std::vector<std::string_view> lines_of(std::string_view text) {
    std::vector<std::string_view> out;
    std::size_t start = 0;
    while (start < text.size()) {
        const auto nl = text.find('\n', start);
        if (nl == std::string_view::npos) {
            out.push_back(text.substr(start));
            break;
        }
        out.push_back(text.substr(start, nl - start));
        start = nl + 1;
    }
    return out;
}

std::size_t count_occurrences(std::string_view text, std::string_view needle) {
    std::size_t n = 0;
    for (auto pos = text.find(needle); pos != std::string_view::npos; pos = text.find(needle, pos + needle.size())) ++n;
    return n;
}

std::size_t line_of_offset(std::string_view text, std::size_t offset) {
    return static_cast<std::size_t>(std::count(text.begin(), text.begin() + static_cast<std::ptrdiff_t>(offset), '\n')) + 1;
}

std::string without_cr_before_lf(std::string s) {
    std::string out;
    out.reserve(s.size());
    for (std::size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\r' && i + 1 < s.size() && s[i + 1] == '\n') continue;
        out += s[i];
    }
    return out;
}

// Lines that start a git conflict marker.
std::size_t conflict_markers(std::string_view text) {
    std::size_t n = 0;
    for (const auto line : lines_of(text)) {
        if (line.rfind("<<<<<<< ", 0) == 0 || line == "<<<<<<<" || line == "=======" ||
            line.rfind(">>>>>>> ", 0) == 0 || line == ">>>>>>>") {
            ++n;
        }
    }
    return n;
}

std::string numbered(const std::vector<std::string_view>& lines, std::size_t first, std::size_t last) {
    std::string out;
    for (std::size_t i = first; i <= last && i <= lines.size(); ++i) {
        out += std::to_string(i) + ": " + std::string(lines[i - 1]) + "\n";
    }
    return out;
}

ActionResult canvas_failure(const CanvasError& e) {
    ActionResult r;
    r.error_code = e.code();
    r.llm_facing_output = e.what();
    r.token_estimate = estimate_tokens(r.llm_facing_output);
    return r;
}

ActionResult path_failure(const PathDenied& e) {
    ActionResult r;
    r.error_code = e.code();
    r.llm_facing_output = e.what();
    r.token_estimate = estimate_tokens(r.llm_facing_output);
    return r;
}

Json schema(const char* text) {
    return Json::parse(text);
}

}  // namespace

WorkspaceModule::WorkspaceModule(const ModuleContext& ctx) : ctx_(ctx), max_output_chars_(ctx.max_output_chars) {}

std::vector<ActionSchema> WorkspaceModule::get_actions() const {
    return {
        {"outline", "List workspace files with line counts and their functions/classes.",
         schema(R"({"type":"object","properties":{"path":{"type":"string"}},"additionalProperties":false})")},
        {"read_region", "Read numbered lines of a file (at most 150 lines per call).",
         schema(R"({"type":"object","properties":{"file":{"type":"string"},"start_line":{"type":"integer","minimum":1},"end_line":{"type":"integer","minimum":1}},"required":["file","start_line"],"additionalProperties":false})")},
        {"inspect_symbol", "Show the full source of a function, class, struct, enum or namespace.",
         schema(R"({"type":"object","properties":{"file":{"type":"string"},"name":{"type":"string"}},"required":["file","name"],"additionalProperties":false})")},
        {"surgical_edit", "Replace one exact, unique block of text in a file. The edit is rejected if it breaks the file's syntax.",
         schema(R"({"type":"object","properties":{"file":{"type":"string"},"search_block":{"type":"string"},"replace_block":{"type":"string"}},"required":["file","search_block","replace_block"],"additionalProperties":false})")},
        {"create_file", "Create a new file with the given content.",
         schema(R"({"type":"object","properties":{"file":{"type":"string"},"content":{"type":"string"}},"required":["file","content"],"additionalProperties":false})")},
        {"revert_file", "Restore a file to its content when it was first opened.",
         schema(R"({"type":"object","properties":{"file":{"type":"string"}},"required":["file"],"additionalProperties":false})")},
    };
}

void WorkspaceModule::configure(const Json& s) {
    using namespace json_io;
    expect_object(s, "");
    reject_unknown(s, "", {"root_dir", "pinned_files", "review", "max_output_chars"});
    if (s.contains("root_dir")) {
        const auto dir = read_string(s["root_dir"], "/root_dir");
        if (!ctx_.workspace_root.empty()) {
            try {
                const auto r = PathFirewall(ctx_.workspace_root).resolve(dir, Access::read);
                std::error_code ec;
                if (!fs::is_directory(r.absolute, ec)) throw SchemaError("/root_dir", "not a directory: " + dir);
            } catch (const PathDenied& e) {
                throw SchemaError("/root_dir", e.what());
            }
        }
        root_dir_ = dir;
    }
    if (s.contains("pinned_files")) pinned_ = read_string_array(s["pinned_files"], "/pinned_files");
    if (s.contains("review")) {
        const auto mode = read_string(s["review"], "/review");
        if (mode != "auto" && mode != "manual") throw SchemaError("/review", "expected auto or manual");
        manual_review_ = mode == "manual";
    }
    if (s.contains("max_output_chars")) {
        const auto n = read_u64(s["max_output_chars"], "/max_output_chars");
        if (n < 200) throw SchemaError("/max_output_chars", "must be >= 200");
        max_output_chars_ = static_cast<std::size_t>(n);
    }
    canvas_.reset();
}

CanvasBuffer& WorkspaceModule::canvas() {
    if (!canvas_) {
        const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
        const auto root = PathFirewall(base).resolve(root_dir_, Access::read).absolute;
        canvas_.emplace(PathFirewall(root));
    }
    return *canvas_;
}

ActionResult WorkspaceModule::capped(ActionResult r) const {
    if (r.llm_facing_output.size() > max_output_chars_) {
        const auto cut = r.llm_facing_output.size() - max_output_chars_;
        r.llm_facing_output.resize(max_output_chars_);
        r.llm_facing_output += "\n...[truncated " + std::to_string(cut) + " chars]";
    }
    r.token_estimate = estimate_tokens(r.llm_facing_output);
    return r;
}

ActionResult WorkspaceModule::run(const std::string& action, const Json& args) {
    try {
        if (action == "outline") return capped(outline(args));
        if (action == "read_region") return capped(read_region(args));
        if (action == "inspect_symbol") return capped(inspect_symbol(args));
        if (action == "surgical_edit") return capped(surgical_edit(args));
        if (action == "create_file") return capped(create_file(args));
        if (action == "revert_file") return capped(revert_file(args));
    } catch (const CanvasError& e) {
        return canvas_failure(e);
    } catch (const PathDenied& e) {
        return path_failure(e);
    } catch (const std::invalid_argument& e) {
        return fail("workspace_unavailable", e.what());
    }
    return fail("unknown_action", "WorkspaceModule has no action '" + action + "'");
}

ActionResult WorkspaceModule::outline(const Json& args) {
    auto& c = canvas();
    const auto& fw = c.firewall();
    const std::string sub = args.contains("path") ? args["path"].get<std::string>() : ".";
    const auto start = fw.resolve(sub, Access::read);

    std::vector<std::string> files;
    std::error_code ec;
    if (fs::is_regular_file(start.absolute, ec)) {
        files.push_back(start.relative);
    } else {
        fs::recursive_directory_iterator it(start.absolute, fs::directory_options::skip_permission_denied, ec);
        for (; !ec && it != fs::recursive_directory_iterator(); it.increment(ec)) {
            const auto name = path_to_utf8(it->path().filename());
            if (it->is_directory(ec)) {
                if (PathFirewall::is_generated_dir(name) || name == ".git") it.disable_recursion_pending();
                continue;
            }
            if (!it->is_regular_file(ec)) continue;
            try {
                files.push_back(fw.resolve(path_to_utf8(it->path()), Access::read).relative);
            } catch (const PathDenied&) {
                // blocked files (secrets) are not listed
            }
        }
    }
    std::sort(files.begin(), files.end());

    std::string out = "WORKSPACE: " + path_to_utf8(fw.root().filename()) + " (" + std::to_string(files.size()) + " files)\n";
    std::size_t shown = 0;
    for (const auto& rel : files) {
        if (shown++ == kMaxOutlineFiles) {
            out += "  ... and " + std::to_string(files.size() - kMaxOutlineFiles) + " more files\n";
            break;
        }
        std::string text;
        if (const auto* d = c.find(rel)) {
            text = d->text();
        } else {
            std::ifstream in(fw.resolve(rel, Access::read).absolute, std::ios::binary);
            text.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
        }
        const auto n_lines = lines_of(text).size();
        out += "  - " + rel + " (" + std::to_string(n_lines) + " lines)";
        if (std::find(pinned_.begin(), pinned_.end(), rel) != pinned_.end()) out += " [pinned]";
        const auto lang = syntax::language_for(rel);
        if (lang != syntax::Language::none) {
            const auto syms = syntax::symbols(lang, text);
            if (!syms.empty()) {
                out += " | symbols: ";
                for (std::size_t i = 0; i < syms.size() && i < kMaxOutlineSymbols; ++i) {
                    if (i) out += ", ";
                    out += syms[i].name;
                }
                if (syms.size() > kMaxOutlineSymbols) out += ", ...";
            }
        }
        out += "\n";
    }
    if (!c.pending().empty()) {
        out += "PENDING PATCHES:";
        for (const auto& p : c.pending()) out += " " + p.id + " (" + p.path + ")";
        out += "\n";
    }
    return ok(out);
}

ActionResult WorkspaceModule::read_region(const Json& args) {
    const auto& d = canvas().open(args["file"].get<std::string>());
    const auto lines = lines_of(d.text());
    std::size_t first = args["start_line"].get<std::size_t>();
    std::size_t last = args.contains("end_line") ? args["end_line"].get<std::size_t>() : first + kMaxRegionLines - 1;
    if (last < first) std::swap(first, last);
    if (first > lines.size()) {
        return fail("out_of_range", "start_line " + std::to_string(first) + " is past the end of " + d.path + " (" +
                                        std::to_string(lines.size()) + " lines)");
    }
    last = std::min({last, first + kMaxRegionLines - 1, lines.size()});
    return ok("--- " + d.path + " lines " + std::to_string(first) + "-" + std::to_string(last) + " of " +
              std::to_string(lines.size()) + " ---\n" + numbered(lines, first, last));
}

ActionResult WorkspaceModule::inspect_symbol(const Json& args) {
    const auto& d = canvas().open(args["file"].get<std::string>());
    const auto name = args["name"].get<std::string>();
    const auto lang = syntax::language_for(d.path);
    if (lang == syntax::Language::none) {
        return fail("unsupported_language", "no symbol support for '" + d.path + "' (C, C++ and Python only)");
    }
    const auto sym = syntax::find_symbol(lang, d.text(), name);
    if (!sym) {
        std::string known;
        const auto syms = syntax::symbols(lang, d.text());
        for (std::size_t i = 0; i < syms.size() && i < 20; ++i) known += (i ? ", " : "") + syms[i].name;
        return fail("symbol_not_found", "no symbol '" + name + "' in " + d.path + (known.empty() ? "" : "; symbols: " + known));
    }
    const auto lines = lines_of(d.text());
    return ok("--- " + d.path + ": " + sym->kind + " " + sym->name + " (lines " + std::to_string(sym->start_line) + "-" +
              std::to_string(sym->end_line) + ") ---\n" + numbered(lines, sym->start_line, sym->end_line));
}

ActionResult WorkspaceModule::submit(const std::string& path, const std::string& old_text, const std::string& new_text,
                                     const std::string& summary) {
    if (conflict_markers(new_text) > conflict_markers(old_text)) {
        return fail("conflict_marker", "refused: the edit adds git conflict markers to " + path + "; nothing was changed");
    }
    const auto lang = syntax::language_for(path);
    std::string note;
    if (lang != syntax::Language::none) {
        const auto before = syntax::analyze(lang, old_text);
        const auto after = syntax::analyze(lang, new_text);
        if (after.error_count > before.error_count) {
            const auto pos = after.first_error.value_or(syntax::Position{1, 1});
            const auto lines = lines_of(new_text);
            const auto lo = pos.line > 2 ? pos.line - 2 : 1;
            return fail("syntax_error", "refused: the edit introduces a " + std::string(syntax::to_string(lang)) +
                                            " syntax error at line " + std::to_string(pos.line) + ", column " +
                                            std::to_string(pos.col) + " of " + path + "; nothing was changed\n" +
                                            numbered(lines, lo, std::min(lines.size(), pos.line + 2)));
        }
    } else {
        note = " (no syntax check for this file type)";
    }

    auto& c = canvas();
    const auto id = c.propose(path, new_text, "agent");
    if (manual_review_) {
        return ok("queued patch " + id + " for review: " + summary + note);
    }
    try {
        c.accept(id);
    } catch (const CanvasError&) {
        c.reject(id);
        throw;
    }
    return ok(summary + note);
}

ActionResult WorkspaceModule::surgical_edit(const Json& args) {
    const auto& d = canvas().open(args["file"].get<std::string>());
    auto search = args["search_block"].get<std::string>();
    auto replace = args["replace_block"].get<std::string>();
    if (d.eol == Eol::crlf) {
        search = without_cr_before_lf(std::move(search));
        replace = without_cr_before_lf(std::move(replace));
    }
    if (search.empty()) return fail("empty_search", "search_block must not be empty");
    const auto& text = d.text();
    const auto count = count_occurrences(text, search);
    if (count == 0) {
        return fail("no_match", "search_block was not found in " + d.path + ". No change made. File starts with: " +
                                    Json(text.substr(0, 400)).dump());
    }
    if (count > 1) {
        return fail("ambiguous_match", "search_block matched " + std::to_string(count) + " times in " + d.path +
                                           ". Include more surrounding lines so the match is unique.");
    }
    const auto at = text.find(search);
    std::string next = text;
    next.replace(at, search.size(), replace);
    const auto first = line_of_offset(text, at);
    const auto old_n = static_cast<std::size_t>(std::count(search.begin(), search.end(), '\n'));
    const std::string path = d.path;
    return submit(path, text, next,
                  "edited " + path + " at line " + std::to_string(first) + " (" + std::to_string(old_n + 1) + " lines -> " +
                      std::to_string(static_cast<std::size_t>(std::count(replace.begin(), replace.end(), '\n')) + 1) +
                      " lines; file now " + std::to_string(lines_of(next).size()) + " lines)");
}

ActionResult WorkspaceModule::create_file(const Json& args) {
    const auto& d = canvas().create(args["file"].get<std::string>());
    const std::string path = d.path;
    const auto content = args["content"].get<std::string>();
    auto r = submit(path, "", content, "created " + path + " (" + std::to_string(lines_of(content).size()) + " lines)");
    if (!r.success) canvas_->discard(path);  // validation failed: forget the empty document
    return r;
}

ActionResult WorkspaceModule::revert_file(const Json& args) {
    const auto& d = canvas().open(args["file"].get<std::string>());
    if (d.text() == d.versions.front()) return ok(d.path + " already matches its loaded content");
    const std::string path = d.path;
    const std::string loaded = d.versions.front();
    const std::string current = d.text();
    return submit(path, current, loaded, "reverted " + path + " to its loaded content");
}

std::vector<PendingPatch> WorkspaceModule::pending() {
    return canvas().pending();
}

std::string WorkspaceModule::disk_diff(const std::string& patch_id) {
    for (const auto& p : canvas().pending()) {
        if (p.id == patch_id) return canvas().disk_diff(p);
    }
    return {};
}

ActionResult WorkspaceModule::accept(const std::string& id) {
    try {
        canvas().accept(id);
        return ok("accepted " + id);
    } catch (const CanvasError& e) {
        return canvas_failure(e);
    }
}

ActionResult WorkspaceModule::reject(const std::string& id) {
    try {
        canvas().reject(id);
        return ok("rejected " + id);
    } catch (const CanvasError& e) {
        return canvas_failure(e);
    }
}

ActionResult WorkspaceModule::undo(const std::string& path) {
    try {
        canvas().undo(canvas().firewall().resolve(path, Access::write).relative);
        return ok("undid last change to " + path);
    } catch (const CanvasError& e) {
        return canvas_failure(e);
    } catch (const PathDenied& e) {
        return path_failure(e);
    }
}

ActionResult WorkspaceModule::redo(const std::string& path) {
    try {
        canvas().redo(canvas().firewall().resolve(path, Access::write).relative);
        return ok("redid change to " + path);
    } catch (const CanvasError& e) {
        return canvas_failure(e);
    } catch (const PathDenied& e) {
        return path_failure(e);
    }
}

Json WorkspaceModule::export_state_snapshot() const {
    Json s = Json::object();
    s["root_dir"] = root_dir_;
    s["pinned_files"] = pinned_;
    s["review"] = manual_review_ ? "manual" : "auto";
    s["max_output_chars"] = max_output_chars_;
    s["canvas"] = canvas_ ? canvas_->snapshot() : Json(nullptr);
    return s;
}

void WorkspaceModule::restore_state_snapshot(const Json& s) {
    using namespace json_io;
    expect_object(s, "");
    reject_unknown(s, "", {"root_dir", "pinned_files", "review", "max_output_chars", "canvas"});
    Json config = Json::object();
    for (const auto* key : {"root_dir", "pinned_files", "review", "max_output_chars"}) {
        config[key] = require(s, "", key);
    }
    configure(config);
    const auto& cv = require(s, "", "canvas");
    if (!cv.is_null()) {
        try {
            canvas().restore(cv);
        } catch (const SchemaError& e) {
            throw SchemaError("/canvas" + e.path(), e.reason());
        }
    }
}

}  // namespace aquila
