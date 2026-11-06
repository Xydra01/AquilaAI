#include "aquila/document/document_module.hpp"

#include <cctype>
#include <fstream>
#include <regex>
#include <sstream>

namespace aquila::document {

namespace {

std::size_t count_words(std::string_view text) noexcept {
    std::size_t words = 0;
    bool in_word = false;
    for (unsigned char c : text) {
        if (std::isspace(c)) {
            in_word = false;
        } else if (!in_word) {
            in_word = true;
            ++words;
        }
    }
    return words;
}

std::string trim(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return std::string(s);
}

std::string heading_core(std::string_view text) {
    // Strip leading markdown '#'
    std::string s = trim(text);
    while (!s.empty() && s.front() == '#') {
        s.erase(0, 1);
    }
    s = trim(s);

    // Strip leading numbering: e.g. "1. " or "1) "
    std::size_t i = 0;
    while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i]))) {
        ++i;
    }
    if (i > 0 && i < s.size() && (s[i] == '.' || s[i] == ')')) {
        s = trim(s.substr(i + 1));
    }

    // Lowercase and strip non-alphanumeric
    std::string core;
    bool prev_space = false;
    for (unsigned char c : s) {
        if (std::isalnum(c)) {
            core.push_back(static_cast<char>(std::tolower(c)));
            prev_space = false;
        } else if (!prev_space) {
            core.push_back(' ');
            prev_space = true;
        }
    }
    return trim(core);
}

}  // namespace

std::size_t DraftState::compute_word_count() const noexcept {
    std::size_t total = 0;
    for (const auto& sec : sections) {
        total += count_words(sec.content);
    }
    return total;
}

Json DraftState::to_json() const {
    Json j = Json::object();
    j["title"] = title;
    j["synopsis"] = synopsis;
    Json secs = Json::array();
    for (const auto& sec : sections) {
        Json s = Json::object();
        s["header"] = sec.header;
        s["content"] = sec.content;
        secs.push_back(std::move(s));
    }
    j["sections"] = std::move(secs);
    j["word_count"] = compute_word_count();
    return j;
}

DraftState DraftState::from_json(const Json& j) {
    DraftState s;
    if (j.is_object()) {
        s.title = j.value("title", "");
        s.synopsis = j.value("synopsis", "");
        if (j.contains("sections") && j["sections"].is_array()) {
            for (const auto& item : j["sections"]) {
                if (item.is_object()) {
                    s.sections.push_back(DocumentSection{
                        item.value("header", ""),
                        item.value("content", "")
                    });
                }
            }
        }
        s.word_count = s.compute_word_count();
    }
    return s;
}

std::string normalize_section_header(std::string_view header) {
    std::string s = trim(header);
    while (!s.empty() && s.front() == '#') {
        s.erase(0, 1);
    }
    while (!s.empty() && s.back() == '#') {
        s.pop_back();
    }
    s = trim(s);

    std::size_t i = 0;
    while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i]))) {
        ++i;
    }
    if (i > 0 && i < s.size() && (s[i] == '.' || s[i] == ')')) {
        s = trim(s.substr(i + 1));
    }

    return s.empty() ? "Untitled Section" : s;
}

std::string strip_redundant_leading_heading(std::string_view content, std::string_view section_header) {
    std::string text(content);
    // Strip leading newlines
    while (!text.empty() && text.front() == '\n') {
        text.erase(0, 1);
    }
    if (text.empty()) {
        return text;
    }

    const auto nl = text.find('\n');
    const std::string first_line = trim(text.substr(0, nl));
    if (first_line.empty() || first_line.front() != '#') {
        return text;
    }

    const std::string h_core = heading_core(section_header);
    const std::string f_core = heading_core(first_line);
    if (h_core.empty() || f_core.empty()) {
        return text;
    }

    if (h_core == f_core || h_core.find(f_core) != std::string::npos || f_core.find(h_core) != std::string::npos) {
        if (nl == std::string::npos) {
            return "";
        }
        std::string rest = text.substr(nl + 1);
        while (!rest.empty() && rest.front() == '\n') {
            rest.erase(0, 1);
        }
        return rest;
    }

    return text;
}

DocumentModule::DocumentModule() : DocumentModule(ModuleContext{}) {}

DocumentModule::DocumentModule(ModuleContext ctx) : ctx_(std::move(ctx)) {
    load_active_draft();
}

std::filesystem::path DocumentModule::drafts_dir() const {
    return ctx_.workspace_root / "Agent-Drafts";
}

std::filesystem::path DocumentModule::active_draft_file() const {
    return drafts_dir() / "active_draft_state.json";
}

std::vector<ActionSchema> DocumentModule::get_actions() const {
    return {
        ActionSchema{
            "init_document",
            "Initializes a new living document buffer in Agent-Drafts.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"title", Json::object({{"type", "string"}, {"description", "Document title"}})},
                    {"synopsis", Json::object({{"type", "string"}, {"description", "Brief synopsis or summary"}})}
                })},
                {"required", Json::array({"title"})}
            })
        },
        ActionSchema{
            "write_section",
            "Appends or overwrites a section of text in the active document.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"section_header", Json::object({{"type", "string"}, {"description", "Section header title (plain text without '#')"}})},
                    {"content", Json::object({{"type", "string"}, {"description", "Markdown body of section (do not repeat section header as heading)"}})}
                })},
                {"required", Json::array({"section_header", "content"})}
            })
        },
        ActionSchema{
            "read_outline",
            "Reads the current document outline with numbered section headers and word counts.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object()}
            })
        },
        ActionSchema{
            "revise_selection",
            "Revises an existing named section in the active document.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"section_header", Json::object({{"type", "string"}, {"description", "Header of the section to revise"}})},
                    {"new_content", Json::object({{"type", "string"}, {"description", "New content replacement"}})},
                    {"instructions", Json::object({{"type", "string"}, {"description", "Revision intent or notes"}})}
                })},
                {"required", Json::array({"section_header", "new_content"})}
            })
        },
        ActionSchema{
            "compile_document",
            "Compiles all written sections into a final Markdown file saved in Agent-Drafts.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"file_name", Json::object({{"type", "string"}, {"description", "Target filename (e.g. 'report.md')"}})}
                })},
                {"required", Json::array({"file_name"})}
            })
        },
        ActionSchema{
            "get_draft_state",
            "Returns the current active draft structure and word count as JSON.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object()}
            })
        }
    };
}

void DocumentModule::configure(const Json& initial_state) {
    if (!initial_state.is_object()) return;
    if (initial_state.contains("workspace_root")) {
        ctx_.workspace_root = initial_state["workspace_root"].get<std::string>();
        load_active_draft();
    }
}

void DocumentModule::save_active_draft() {
    std::error_code ec;
    std::filesystem::create_directories(drafts_dir(), ec);
    std::ofstream out(active_draft_file(), std::ios::trunc | std::ios::binary);
    if (out.is_open()) {
        const auto text = draft_.to_json().dump(4);
        out.write(text.data(), static_cast<std::streamsize>(text.size()));
    }
}

bool DocumentModule::load_active_draft() {
    const auto file = active_draft_file();
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec)) {
        active_ = false;
        draft_ = DraftState{};
        return false;
    }
    std::ifstream in(file, std::ios::binary);
    if (!in.is_open()) {
        active_ = false;
        return false;
    }
    try {
        Json j;
        in >> j;
        draft_ = DraftState::from_json(j);
        active_ = true;
        return true;
    } catch (...) {
        active_ = false;
        return false;
    }
}

void DocumentModule::clear_active_draft() {
    std::error_code ec;
    std::filesystem::remove(active_draft_file(), ec);
    active_ = false;
    draft_ = DraftState{};
}

Json DocumentModule::export_state_snapshot() const {
    Json snap = Json::object();
    snap["active"] = active_;
    if (active_) {
        snap["title"] = draft_.title;
        snap["synopsis"] = draft_.synopsis;
        snap["section_count"] = draft_.sections.size();
        snap["word_count"] = draft_.compute_word_count();
        Json headers = Json::array();
        for (const auto& sec : draft_.sections) {
            headers.push_back(sec.header);
        }
        snap["outline"] = std::move(headers);
    }
    return snap;
}

void DocumentModule::restore_state_snapshot(const Json& snapshot) {
    if (!snapshot.is_object()) return;
    if (snapshot.value("active", false)) {
        load_active_draft();
    } else {
        clear_active_draft();
    }
}

ActionResult DocumentModule::run(const std::string& action_name, const Json& args) {
    if (action_name == "init_document") {
        const std::string title = args.value("title", "Untitled Document");
        const std::string synopsis = args.value("synopsis", "");
        draft_ = DraftState{};
        draft_.title = title;
        draft_.synopsis = synopsis;
        active_ = true;
        save_active_draft();
        return ok("✅ Document '" + title + "' initialized. You may now begin writing sections.");
    }

    if (action_name == "write_section") {
        if (!active_) {
            return fail("no_active_document", "❌ Error: No active document found. Use init_document first.");
        }
        const std::string raw_header = args.value("section_header", "");
        const std::string raw_content = args.value("content", "");
        const std::string header = normalize_section_header(raw_header);
        const std::string body = strip_redundant_leading_heading(raw_content, header);

        bool exists = false;
        for (auto& sec : draft_.sections) {
            if (normalize_section_header(sec.header) == header) {
                sec.header = header;
                sec.content = body;
                exists = true;
                break;
            }
        }
        if (!exists) {
            draft_.sections.push_back(DocumentSection{header, body});
        }
        draft_.word_count = draft_.compute_word_count();
        save_active_draft();

        const std::size_t sec_words = count_words(body);
        const std::size_t total_words = draft_.word_count;
        if (exists) {
            return ok("✅ Section '" + header + "' successfully OVERWRITTEN (" +
                      std::to_string(sec_words) + " words). Total document length: " +
                      std::to_string(total_words) + " words.");
        }
        return ok("✅ Section '" + header + "' added (" +
                  std::to_string(sec_words) + " words). Total document length: " +
                  std::to_string(total_words) + " words.");
    }

    if (action_name == "read_outline") {
        if (!active_) {
            return fail("no_active_document", "❌ Error: No active document found.");
        }
        if (draft_.sections.empty()) {
            return ok("Document '" + draft_.title + "' is currently empty.");
        }
        std::string outline = "OUTLINE FOR: " + draft_.title + "\n";
        for (std::size_t i = 0; i < draft_.sections.size(); ++i) {
            const auto words = count_words(draft_.sections[i].content);
            outline += std::to_string(i + 1) + ". " + draft_.sections[i].header +
                       " (" + std::to_string(words) + " words)\n";
        }
        return ok(outline);
    }

    if (action_name == "revise_selection") {
        if (!active_) {
            return fail("no_active_document", "❌ Error: No active document found.");
        }
        const std::string raw_header = args.value("section_header", "");
        const std::string header = normalize_section_header(raw_header);
        const std::string new_content = strip_redundant_leading_heading(args.value("new_content", ""), header);

        for (auto& sec : draft_.sections) {
            if (normalize_section_header(sec.header) == header) {
                sec.content = new_content;
                draft_.word_count = draft_.compute_word_count();
                save_active_draft();
                return ok("✅ Section '" + header + "' revised successfully (" +
                          std::to_string(count_words(new_content)) + " words).");
            }
        }
        return fail("section_not_found", "❌ Error: Section '" + header + "' not found in outline.");
    }

    if (action_name == "compile_document") {
        if (!active_) {
            return fail("no_active_document", "❌ Error: No active document to compile. Use init_document first.");
        }
        std::string file_name = args.value("file_name", "document.md");
        if (file_name.size() > 3 && file_name.substr(file_name.size() - 3) == ".md") {
            file_name = file_name.substr(0, file_name.size() - 3);
        }
        std::error_code ec;
        std::filesystem::create_directories(drafts_dir(), ec);
        const auto save_path = drafts_dir() / (file_name + ".md");

        std::string md = "# " + (draft_.title.empty() ? "Untitled Document" : draft_.title) + "\n\n";
        if (!draft_.synopsis.empty()) {
            md += draft_.synopsis + "\n\n";
        }
        for (const auto& sec : draft_.sections) {
            const auto norm_h = normalize_section_header(sec.header);
            const auto clean_body = strip_redundant_leading_heading(sec.content, norm_h);
            md += "## " + norm_h + "\n\n";
            if (!clean_body.empty()) {
                md += clean_body + "\n\n";
            }
        }

        std::ofstream out(save_path, std::ios::trunc | std::ios::binary);
        if (!out.is_open()) {
            return fail("file_write_error", "❌ Error saving compiled document to " + save_path.generic_string());
        }
        out.write(md.data(), static_cast<std::streamsize>(md.size()));
        out.close();

        clear_active_draft();
        return ok("✅ SUCCESS: Final document compiled and saved to " + save_path.generic_string());
    }

    if (action_name == "get_draft_state") {
        if (!active_) {
            return ok(Json::object({{"active", false}}).dump());
        }
        auto j = draft_.to_json();
        j["active"] = true;
        return ok(j.dump(2));
    }

    return fail("unknown_action", "DocumentModule: unknown action " + action_name);
}

}  // namespace aquila::document

