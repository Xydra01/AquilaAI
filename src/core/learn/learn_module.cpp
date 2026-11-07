#include "aquila/learn/learn_module.hpp"
#include "aquila/knowledge/html_cleaner.hpp"
#include "aquila/knowledge/page_scorer.hpp"
#include "aquila/knowledge/web_fetcher.hpp"

#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <regex>
#include <sstream>

namespace aquila::learn {

namespace fs = std::filesystem;

namespace {

std::string now_iso() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm tm_buf{};
#ifdef _WIN32
    gmtime_s(&tm_buf, &t);
#else
    gmtime_r(&t, &tm_buf);
#endif
    std::ostringstream ss;
    ss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
    return ss.str();
}

std::string strip_code_fences(std::string text) {
    while (!text.empty() && (text.front() == ' ' || text.front() == '\t' || text.front() == '\r' || text.front() == '\n')) {
        text.erase(0, 1);
    }
    if (text.rfind("```", 0) == 0) {
        auto end_line = text.find('\n');
        if (end_line != std::string::npos) {
            text = text.substr(end_line + 1);
        }
    }
    while (!text.empty() && (text.back() == ' ' || text.back() == '\t' || text.back() == '\r' || text.back() == '\n')) {
        text.pop_back();
    }
    if (text.size() >= 3 && text.substr(text.size() - 3) == "```") {
        text = text.substr(0, text.size() - 3);
    }
    while (!text.empty() && (text.back() == ' ' || text.back() == '\t' || text.back() == '\r' || text.back() == '\n')) {
        text.pop_back();
    }
    return text;
}

std::string repair_truncated_json(std::string text) {
    bool in_string = false;
    bool escaped = false;
    std::vector<char> stack;

    for (std::size_t i = 0; i < text.size(); ++i) {
        char c = text[i];
        if (escaped) {
            escaped = false;
            continue;
        }
        if (c == '\\') {
            escaped = true;
            continue;
        }
        if (c == '"') {
            in_string = !in_string;
            continue;
        }
        if (!in_string) {
            if (c == '{' || c == '[') {
                stack.push_back(c);
            } else if (c == '}' || c == ']') {
                if (!stack.empty()) {
                    char expected = (c == '}') ? '{' : '[';
                    if (stack.back() == expected) {
                        stack.pop_back();
                    }
                }
            }
        }
    }

    if (in_string) {
        text.push_back('"');
    }

    while (!stack.empty()) {
        char open = stack.back();
        stack.pop_back();
        if (open == '{') text.push_back('}');
        else if (open == '[') text.push_back(']');
    }
    return text;
}

}  // namespace

Json ArchiveSource::to_json() const {
    return Json{
        {"id", id},
        {"name", name},
        {"source_type", source_type},
        {"file_path", file_path},
        {"token_count", token_count},
        {"added_at", added_at}
    };
}

ArchiveSource ArchiveSource::from_json(const Json& j) {
    ArchiveSource s;
    s.id = j.value("id", "");
    s.name = j.value("name", "");
    s.source_type = j.value("source_type", "file");
    s.file_path = j.value("file_path", "");
    s.token_count = j.value("token_count", static_cast<std::size_t>(0));
    s.added_at = j.value("added_at", "");
    return s;
}

Json ArchiveManifest::to_json() const {
    Json arr = Json::array();
    for (const auto& s : sources) {
        arr.push_back(s.to_json());
    }
    return Json{{"sources", std::move(arr)}};
}

ArchiveManifest ArchiveManifest::from_json(const Json& j) {
    ArchiveManifest m;
    if (j.contains("sources") && j["sources"].is_array()) {
        for (const auto& item : j["sources"]) {
            m.sources.push_back(ArchiveSource::from_json(item));
        }
    }
    return m;
}

Json SyllabusNode::to_json() const {
    Json j = Json::object();
    j["id"] = id;
    j["title"] = title;
    if (parent_id) {
        j["parent_id"] = *parent_id;
    } else {
        j["parent_id"] = nullptr;
    }
    j["order"] = order;
    j["mastery_tier"] = mastery_tier;
    j["tier_gate"] = tier_gate;
    if (required_assessment_id) {
        j["required_assessment_id"] = *required_assessment_id;
    } else {
        j["required_assessment_id"] = nullptr;
    }
    return j;
}

SyllabusNode SyllabusNode::from_json(const Json& j) {
    SyllabusNode n;
    if (j.is_object()) {
        n.id = j.value("id", "");
        n.title = j.value("title", "");
        if (j.contains("parent_id") && !j["parent_id"].is_null()) {
            n.parent_id = j["parent_id"].get<std::string>();
        }
        n.order = j.value("order", 0);
        n.mastery_tier = j.value("mastery_tier", 0);
        n.tier_gate = j.value("tier_gate", 0);
        if (j.contains("required_assessment_id") && !j["required_assessment_id"].is_null()) {
            n.required_assessment_id = j["required_assessment_id"].get<std::string>();
        }
    }
    return n;
}

Json Course::to_json() const {
    return Json::object({
        {"id", id},
        {"title", title},
        {"topic", topic},
        {"intake", intake},
        {"created_at", created_at},
        {"build_complete", build_complete}
    });
}

Course Course::from_json(const Json& j) {
    Course c;
    if (j.is_object()) {
        c.id = j.value("id", "");
        c.title = j.value("title", "Course");
        c.topic = j.value("topic", "");
        c.intake = j.value("intake", "files");
        c.created_at = j.value("created_at", "");
        c.build_complete = j.value("build_complete", false);
    }
    return c;
}

Json Syllabus::to_json() const {
    Json j = Json::object();
    j["version"] = version;
    j["title"] = title;
    j["topic"] = topic;
    j["intake"] = intake;
    j["status"] = status;
    j["current_node_id"] = current_node_id;
    Json arr = Json::array();
    for (const auto& node : nodes) {
        arr.push_back(node.to_json());
    }
    j["nodes"] = std::move(arr);
    j["assessments"] = assessments;
    return j;
}

Syllabus Syllabus::from_json(const Json& j) {
    Syllabus s;
    if (j.is_object()) {
        s.version = j.value("version", 1);
        s.title = j.value("title", "");
        s.topic = j.value("topic", "");
        s.intake = j.value("intake", "files");
        s.status = j.value("status", "building");
        s.current_node_id = j.value("current_node_id", "root");
        if (j.contains("nodes") && j["nodes"].is_array()) {
            for (const auto& item : j["nodes"]) {
                s.nodes.push_back(SyllabusNode::from_json(item));
            }
        }
        if (j.contains("assessments") && j["assessments"].is_array()) {
            s.assessments = j["assessments"].get<std::vector<Json>>();
        }
    }
    return s;
}

std::pair<bool, std::string> validate_syllabus_structure(const std::vector<SyllabusNode>& nodes) {
    std::vector<const SyllabusNode*> valid;
    for (const auto& n : nodes) {
        if (!n.id.empty() && !n.title.empty()) {
            valid.push_back(&n);
        }
    }
    if (valid.size() < kSyllabusMinNodes) {
        return {false,
                "Need at least " + std::to_string(kSyllabusMinNodes) +
                " learning units (got " + std::to_string(valid.size()) +
                "). Add modules and subtopics from the course material."};
    }
    std::size_t children = 0;
    std::size_t roots = 0;
    for (const auto* n : valid) {
        if (n->parent_id && !n->parent_id->empty()) {
            ++children;
        } else {
            ++roots;
        }
    }
    if (children < kSyllabusMinChildNodes) {
        return {false,
                "Need at least " + std::to_string(kSyllabusMinChildNodes) +
                " sub-units with parent_id (got " + std::to_string(children) +
                "). Use a tree: 1 root -> modules -> lessons."};
    }
    if (roots == 0) {
        return {false, "Include at least one root node (parent_id null)."};
    }
    return {true, ""};
}

LearnModule::LearnModule() : LearnModule(ModuleContext{}) {}

LearnModule::LearnModule(ModuleContext ctx) : ctx_(std::move(ctx)) {}

std::filesystem::path LearnModule::course_dir() const {
    return ctx_.workspace_root / "Agent-Learn" / instance_id_ / "courses" / active_course_id_;
}

std::filesystem::path LearnModule::syllabus_file() const {
    return course_dir() / "syllabus.json";
}

std::filesystem::path LearnModule::assessments_dir() const {
    return course_dir() / "assessments";
}

std::filesystem::path LearnModule::archive_dir() const {
    return course_dir() / "archive";
}

std::filesystem::path LearnModule::archive_manifest_file() const {
    return archive_dir() / "manifest.json";
}

std::filesystem::path LearnModule::archive_sources_dir() const {
    return archive_dir() / "sources";
}

ArchiveManifest LearnModule::load_manifest() const {
    const auto file = archive_manifest_file();
    if (!fs::exists(file)) {
        return ArchiveManifest{};
    }
    std::ifstream in(file, std::ios::binary);
    if (!in.is_open()) {
        return ArchiveManifest{};
    }
    try {
        Json j;
        in >> j;
        return ArchiveManifest::from_json(j);
    } catch (...) {
        return ArchiveManifest{};
    }
}

void LearnModule::save_manifest(const ArchiveManifest& manifest) const {
    std::error_code ec;
    fs::create_directories(archive_dir(), ec);
    const auto file = archive_manifest_file();
    std::ofstream out(file, std::ios::trunc | std::ios::binary);
    if (out.is_open()) {
        out << manifest.to_json().dump(2);
    }
}

std::vector<ActionSchema> LearnModule::get_actions() const {
    return {
        ActionSchema{
            "create_or_load_course",
            "Creates or loads a course syllabus ledger.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"course_id", Json::object({{"type", "string"}, {"description", "Course unique ID"}})},
                    {"title", Json::object({{"type", "string"}, {"description", "Course title"}})},
                    {"topic", Json::object({{"type", "string"}, {"description", "Course topic"}})},
                    {"instance_id", Json::object({{"type", "string"}, {"description", "Instance ID (defaults to 'default')"}})}
                })},
                {"required", Json::array({"course_id"})}
            })
        },
        ActionSchema{
            "create_course",
            "Creates a new course syllabus ledger (alias for create_or_load_course).",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"course_id", Json::object({{"type", "string"}, {"description", "Course unique ID"}})},
                    {"title", Json::object({{"type", "string"}, {"description", "Course title"}})},
                    {"topic", Json::object({{"type", "string"}, {"description", "Course topic"}})},
                    {"instance_id", Json::object({{"type", "string"}, {"description", "Instance ID"}})}
                })}
            })
        },
        ActionSchema{
            "write_syllabus",
            "Validates and writes the hierarchical syllabus JSON for the active course.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"content", Json::object({{"type", "string"}, {"description", "Syllabus JSON string (tree of learning units)"}})}
                })},
                {"required", Json::array({"content"})}
            })
        },
        ActionSchema{
            "finalize_course",
            "Finalizes course build once syllabus satisfies hierarchy quality gates.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object()}
            })
        },
        ActionSchema{
            "generate_assessment",
            "Generates an assessment rubric or quiz for a specific learning node.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"node_id", Json::object({{"type", "string"}, {"description", "Target syllabus node ID"}})},
                    {"questions", Json::object({{"type", "array"}, {"description", "List of assessment questions"}})}
                })},
                {"required", Json::array({"node_id"})}
            })
        },
        ActionSchema{
            "record_result",
            "Records an assessment result and advances mastery tier upon pass.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"node_id", Json::object({{"type", "string"}, {"description", "Syllabus node ID"}})},
                    {"passed", Json::object({{"type", "boolean"}, {"description", "Whether the learner passed"}})},
                    {"score", Json::object({{"type", "number"}, {"description", "Score percentage (0.0 to 1.0)"}})}
                })},
                {"required", Json::array({"node_id", "passed"})}
            })
        },
        ActionSchema{
            "add_archive_source",
            "Adds raw text or markdown content as a reference source to the course archive.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"name", Json::object({{"type", "string"}, {"description", "Descriptive name of the source (e.g. 'Chapter 1 Notes')"}})},
                    {"content", Json::object({{"type", "string"}, {"description", "Full text or markdown content of the reference material"}})}
                })},
                {"required", Json::array({"name", "content"})}
            })
        },
        ActionSchema{
            "ingest_archive_file",
            "Copies a local document/code file from the workspace into the course archive.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"file_path", Json::object({{"type", "string"}, {"description", "Path to the file to ingest into course archive"}})},
                    {"name", Json::object({{"type", "string"}, {"description", "Optional friendly display name"}})}
                })},
                {"required", Json::array({"file_path"})}
            })
        },
        ActionSchema{
            "ingest_archive_url",
            "Fetches a web URL, cleans and sanitizes HTML, and stores substantive markdown in the course archive.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"url", Json::object({{"type", "string"}, {"description", "Web URL to scrape and ingest"}})},
                    {"name", Json::object({{"type", "string"}, {"description", "Optional friendly display name"}})}
                })},
                {"required", Json::array({"url"})}
            })
        },
        ActionSchema{
            "list_archive_sources",
            "Lists all archived reference sources and token counts for the active course.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object()}
            })
        },
        ActionSchema{
            "search_archive",
            "Performs grounded search over course archive materials, returning attributed excerpts with source citations.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"query", Json::object({{"type", "string"}, {"description", "Question or search keywords to find in course sources"}})},
                    {"max_results", Json::object({{"type", "integer"}, {"description", "Maximum number of excerpts to return"}, {"default", 5}})}
                })},
                {"required", Json::array({"query"})}
            })
        },
        ActionSchema{
            "get_course_info",
            "Returns JSON overview of active course syllabus and mastery state.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object()}
            })
        }
    };
}

void LearnModule::configure(const Json& initial_state) {
    if (!initial_state.is_object()) return;
    if (initial_state.contains("workspace_root")) {
        ctx_.workspace_root = initial_state["workspace_root"].get<std::string>();
    }
    if (initial_state.contains("instance_id")) {
        instance_id_ = initial_state["instance_id"].get<std::string>();
    }
    if (initial_state.contains("course_id")) {
        const std::string cid = initial_state["course_id"].get<std::string>();
        load_course_record(cid, instance_id_);
    }
}

void LearnModule::save_course_record() {
    std::error_code ec;
    std::filesystem::create_directories(course_dir(), ec);
    std::ofstream out(course_dir() / "course.json", std::ios::trunc | std::ios::binary);
    if (out.is_open()) {
        const auto text = course_.to_json().dump(4);
        out.write(text.data(), static_cast<std::streamsize>(text.size()));
    }
}

bool LearnModule::load_course_record(const std::string& course_id, const std::string& instance_id) {
    active_course_id_ = course_id;
    if (!instance_id.empty()) {
        instance_id_ = instance_id;
    }
    const auto file = course_dir() / "course.json";
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec)) {
        course_ = Course{};
        course_.id = course_id;
        course_.created_at = now_iso();
        syllabus_ = Syllabus{};
        syllabus_.title = course_.title;
        return false;
    }
    std::ifstream in(file, std::ios::binary);
    if (!in.is_open()) return false;
    try {
        Json j;
        in >> j;
        course_ = Course::from_json(j);
        load_syllabus_record();
        return true;
    } catch (...) {
        return false;
    }
}

void LearnModule::save_syllabus_record() {
    std::error_code ec;
    std::filesystem::create_directories(course_dir(), ec);
    std::ofstream out(syllabus_file(), std::ios::trunc | std::ios::binary);
    if (out.is_open()) {
        const auto text = syllabus_.to_json().dump(2);
        out.write(text.data(), static_cast<std::streamsize>(text.size()));
    }
}

bool LearnModule::load_syllabus_record() {
    const auto file = syllabus_file();
    std::error_code ec;
    if (!std::filesystem::is_regular_file(file, ec)) return false;
    std::ifstream in(file, std::ios::binary);
    if (!in.is_open()) return false;
    try {
        Json j;
        in >> j;
        syllabus_ = Syllabus::from_json(j);
        return true;
    } catch (...) {
        return false;
    }
}

Json LearnModule::export_state_snapshot() const {
    Json snap = Json::object();
    snap["has_active_course"] = has_active_course();
    if (has_active_course()) {
        snap["course_id"] = active_course_id_;
        snap["instance_id"] = instance_id_;
        snap["title"] = course_.title;
        snap["build_complete"] = course_.build_complete;
        snap["syllabus_status"] = syllabus_.status;
        snap["node_count"] = syllabus_.nodes.size();
    }
    return snap;
}

void LearnModule::restore_state_snapshot(const Json& snapshot) {
    if (!snapshot.is_object()) return;
    if (snapshot.value("has_active_course", false)) {
        const std::string cid = snapshot.value("course_id", "");
        const std::string iid = snapshot.value("instance_id", "default");
        load_course_record(cid, iid);
    } else {
        active_course_id_.clear();
        course_ = Course{};
        syllabus_ = Syllabus{};
    }
}

namespace {

void extract_nodes_recursive(const Json& item, const std::string& parent_id, std::vector<SyllabusNode>& out) {
    if (!item.is_object()) return;
    SyllabusNode n = SyllabusNode::from_json(item);
    if ((!n.parent_id || n.parent_id->empty()) && !parent_id.empty()) {
        n.parent_id = parent_id;
    }
    if (n.id.empty()) {
        n.id = "unit_" + std::to_string(out.size() + 1);
    }
    if (n.title.empty()) {
        n.title = item.value("name", item.value("topic", "Learning Unit " + std::to_string(out.size() + 1)));
    }
    const std::string this_id = n.id;
    out.push_back(n);

    for (const char* key : {"children", "subtopics", "lessons", "units", "modules", "topics", "subunits", "sub-units", "sub_units", "sections", "lectures"}) {
        if (item.contains(key) && item[key].is_array()) {
            for (const auto& child : item[key]) {
                extract_nodes_recursive(child, this_id, out);
            }
        }
    }
}

}  // namespace

ActionResult LearnModule::run(const std::string& action_name, const Json& args) {
    if (action_name == "create_or_load_course" || action_name == "create_course") {
        std::string cid = args.value("course_id", "");
        if (cid.empty()) {
            cid = "course_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count());
        }
        const std::string iid = args.value("instance_id", instance_id_);
        const bool found = load_course_record(cid, iid);
        if (args.contains("title") && !args["title"].get<std::string>().empty()) {
            course_.title = args["title"].get<std::string>();
            syllabus_.title = course_.title;
        }
        if (args.contains("topic")) {
            course_.topic = args["topic"].get<std::string>();
            syllabus_.topic = course_.topic;
        }
        save_course_record();
        save_syllabus_record();
        if (found) {
            return ok("✅ Loaded existing course '" + course_.title + "' (" + cid + ").");
        }
        return ok("✅ Initialized new course '" + course_.title + "' (" + cid + ").");
    }

    if (action_name == "write_syllabus") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded. Use create_or_load_course or create_course first.");
        }
        Json parsed;
        if (args.contains("content")) {
            if (args["content"].is_string()) {
                const std::string raw = args["content"].get<std::string>();
                const std::string clean = strip_code_fences(raw);
                try {
                    parsed = Json::parse(clean);
                } catch (...) {
                    try {
                        parsed = Json::parse(repair_truncated_json(clean));
                    } catch (...) {
                        // Check if clean is a file path in workspace
                        const auto p = ctx_.workspace_root.empty() ? fs::path(clean) : ctx_.workspace_root / clean;
                        std::error_code ec;
                        if (fs::is_regular_file(p, ec)) {
                            std::ifstream f(p);
                            try { f >> parsed; } catch (...) {}
                        }
                    }
                }
            } else if (args["content"].is_object() || args["content"].is_array()) {
                parsed = args["content"];
            }
        }
        if (parsed.is_null()) {
            // Check if path or file was specified
            for (const char* pk : {"path", "file_path", "filename", "file"}) {
                if (args.contains(pk) && args[pk].is_string()) {
                    const auto p = ctx_.workspace_root.empty() ? fs::path(args[pk].get<std::string>()) : ctx_.workspace_root / args[pk].get<std::string>();
                    std::error_code ec;
                    if (fs::is_regular_file(p, ec)) {
                        std::ifstream f(p);
                        try { f >> parsed; break; } catch (...) {}
                    }
                }
            }
        }
        if (parsed.is_null()) {
            return fail("json_parse_error", "❌ Invalid syllabus JSON: could not parse content or find referenced file.");
        }

        std::vector<SyllabusNode> candidate_nodes;
        if (parsed.is_array()) {
            for (const auto& item : parsed) {
                extract_nodes_recursive(item, "", candidate_nodes);
            }
        } else if (parsed.is_object()) {
            bool found_array = false;
            for (const char* key : {"nodes", "modules", "topics", "units", "syllabus", "subunits", "sub-units", "sub_units", "sections"}) {
                if (parsed.contains(key) && parsed[key].is_array()) {
                    for (const auto& item : parsed[key]) {
                        extract_nodes_recursive(item, "", candidate_nodes);
                    }
                    found_array = true;
                    break;
                }
            }
            if (!found_array) {
                extract_nodes_recursive(parsed, "", candidate_nodes);
            }
        } else {
            return fail("invalid_format", "❌ Syllabus must be a JSON array of nodes or an object containing nodes.");
        }

        if (candidate_nodes.empty()) {
            return fail("invalid_format", "❌ No syllabus nodes could be extracted from input JSON.");
        }

        const auto [valid, reason] = validate_syllabus_structure(candidate_nodes);
        if (!valid) {
            return fail("quality_gate_failed", "❌ Syllabus quality gate rejected: " + reason);
        }

        syllabus_.nodes = std::move(candidate_nodes);
        save_syllabus_record();
        return ok("✅ Syllabus successfully written and validated (" +
                  std::to_string(syllabus_.nodes.size()) + " units). Call finalize_course when ready.");
    }

    if (action_name == "finalize_course") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded.");
        }
        if (course_.build_complete) {
            return ok("✅ Course '" + course_.title + "' is already finalized and complete. Call OrchestratorModule.complete_recipe to finish the recipe.");
        }
        if (syllabus_.nodes.empty()) {
            const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
            std::error_code ec_dir;
            for (const auto& entry : fs::recursive_directory_iterator(base, fs::directory_options::skip_permission_denied, ec_dir)) {
                if (entry.is_regular_file() && entry.path().extension() == ".json") {
                    const auto stem = entry.path().stem().string();
                    if (stem.find("syllabus") != std::string::npos || stem.find("course") != std::string::npos) {
                        try {
                            std::ifstream f(entry.path());
                            Json j = Json::parse(f);
                            std::vector<SyllabusNode> nodes;
                            if (j.is_array()) {
                                for (const auto& item : j) extract_nodes_recursive(item, "", nodes);
                            } else if (j.is_object()) {
                                for (const char* k : {"modules", "topics", "nodes", "units", "syllabus", "subunits", "sub-units", "sub_units", "sections"}) {
                                    if (j.contains(k) && j[k].is_array()) {
                                        for (const auto& item : j[k]) extract_nodes_recursive(item, "", nodes);
                                        break;
                                    }
                                }
                                if (nodes.empty()) extract_nodes_recursive(j, "", nodes);
                            }
                            if (!nodes.empty()) {
                                syllabus_.nodes = std::move(nodes);
                                break;
                            }
                        } catch (...) {}
                    }
                }
            }
        }
        const auto [valid, reason] = validate_syllabus_structure(syllabus_.nodes);
        if (!valid) {
            return fail("syllabus_incomplete", "❌ Cannot finalize course: " + reason);
        }
        syllabus_.status = "ready";
        course_.build_complete = true;
        save_course_record();
        save_syllabus_record();
        return ok("✅ Course '" + course_.title + "' finalized with " +
                  std::to_string(syllabus_.nodes.size()) + " learning units. The course build is complete; now call OrchestratorModule.complete_recipe to finish the recipe.");
    }

    if (action_name == "generate_assessment") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded.");
        }
        const std::string node_id = args.value("node_id", "");
        bool node_found = false;
        for (auto& n : syllabus_.nodes) {
            if (n.id == node_id) {
                node_found = true;
                break;
            }
        }
        if (!node_found) {
            return fail("node_not_found", "❌ Node '" + node_id + "' not found in syllabus.");
        }
        std::error_code ec;
        std::filesystem::create_directories(assessments_dir(), ec);
        const auto file = assessments_dir() / (node_id + "_assessment.json");
        std::ofstream out(file, std::ios::trunc | std::ios::binary);
        if (out.is_open()) {
            const auto text = args.dump(2);
            out.write(text.data(), static_cast<std::streamsize>(text.size()));
        }
        return ok("✅ Assessment generated for node '" + node_id + "'.");
    }

    if (action_name == "record_result") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded.");
        }
        const std::string node_id = args.value("node_id", "");
        const bool passed = args.value("passed", false);
        for (auto& n : syllabus_.nodes) {
            if (n.id == node_id) {
                if (passed && n.mastery_tier < kMasteryTierMax) {
                    ++n.mastery_tier;
                }
                save_syllabus_record();
                return ok("✅ Recorded result for node '" + node_id + "' (mastery tier " +
                          std::to_string(n.mastery_tier) + "/" + std::to_string(kMasteryTierMax) + ").");
            }
        }
        return fail("node_not_found", "❌ Node '" + node_id + "' not found in syllabus.");
    }

    if (action_name == "add_archive_source") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded. Create or load a course first.");
        }
        const std::string name = args.value("name", "Untitled Source");
        const std::string content = args.value("content", "");
        if (content.empty()) {
            return fail("empty_content", "❌ Cannot add empty source to archive.");
        }

        std::error_code ec;
        fs::create_directories(archive_sources_dir(), ec);
        std::string slug = "src_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count() % 1000000);
        fs::path file_path = archive_sources_dir() / (slug + ".md");

        std::ofstream out(file_path, std::ios::trunc | std::ios::binary);
        if (!out.is_open()) {
            return fail("io_error", "❌ Failed to write archive file: " + file_path.string());
        }
        out.write(content.data(), static_cast<std::streamsize>(content.size()));
        out.close();

        ArchiveManifest manifest = load_manifest();
        ArchiveSource src;
        src.id = slug;
        src.name = name;
        src.source_type = "text";
        src.file_path = file_path.filename().string();
        src.token_count = content.size() / 4;
        src.added_at = now_iso();
        manifest.sources.push_back(src);
        save_manifest(manifest);

        return ok("✅ Added source '" + name + "' to course archive (" +
                  std::to_string(src.token_count) + " tokens, ID: " + slug + ").");
    }

    if (action_name == "ingest_archive_file") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded. Create or load a course first.");
        }
        const std::string rel_path = args.value("file_path", "");
        if (rel_path.empty()) {
            return fail("missing_path", "❌ file_path is required.");
        }
        fs::path target_file = ctx_.workspace_root.empty() ? fs::path(rel_path) : ctx_.workspace_root / rel_path;
        if (!fs::exists(target_file)) {
            return fail("file_not_found", "❌ File not found: " + target_file.string());
        }

        std::ifstream in(target_file, std::ios::binary);
        if (!in.is_open()) {
            return fail("read_error", "❌ Failed to read file: " + target_file.string());
        }
        std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        in.close();

        std::string name = args.value("name", target_file.filename().string());
        std::error_code ec;
        fs::create_directories(archive_sources_dir(), ec);
        std::string slug = "file_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count() % 1000000);
        fs::path dest_file = archive_sources_dir() / (slug + target_file.extension().string());

        std::ofstream out(dest_file, std::ios::trunc | std::ios::binary);
        if (!out.is_open()) {
            return fail("write_error", "❌ Failed to write into archive: " + dest_file.string());
        }
        out.write(content.data(), static_cast<std::streamsize>(content.size()));
        out.close();

        ArchiveManifest manifest = load_manifest();
        ArchiveSource src;
        src.id = slug;
        src.name = name;
        src.source_type = "file";
        src.file_path = dest_file.filename().string();
        src.token_count = content.size() / 4;
        src.added_at = now_iso();
        manifest.sources.push_back(src);
        save_manifest(manifest);

        return ok("✅ Ingested file '" + name + "' into course archive (" +
                  std::to_string(src.token_count) + " tokens, ID: " + slug + ").");
    }

    if (action_name == "ingest_archive_url") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded. Create or load a course first.");
        }
        const std::string url = args.value("url", "");
        if (url.empty()) {
            return fail("missing_url", "❌ URL is required.");
        }

        try {
            knowledge::WebFetcher fetcher;
            auto resp = fetcher.fetch(url);
            auto cleaned = knowledge::HtmlCleaner::clean(resp.body);
            auto analysis = knowledge::PageScorer::analyze_page(url, cleaned.text, resp.body);
            if (analysis.quality == knowledge::PageQuality::challenge_blocked) {
                return fail("challenge_blocked", "⚠️ URL blocked by anti-bot verification challenge. Scraping withheld.");
            }
            if (analysis.quality == knowledge::PageQuality::paywall) {
                return fail("paywall_blocked", "⚠️ URL classified as academic paywall. Use an open-access source instead.");
            }

            std::string content = !analysis.sanitized_text.empty() ? analysis.sanitized_text : cleaned.text;
            std::string name = args.value("name", cleaned.title.empty() ? url : cleaned.title);

            std::error_code ec;
            fs::create_directories(archive_sources_dir(), ec);
            std::string slug = "url_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count() % 1000000);
            fs::path dest_file = archive_sources_dir() / (slug + ".md");

            std::ofstream out(dest_file, std::ios::trunc | std::ios::binary);
            if (!out.is_open()) {
                return fail("write_error", "❌ Failed to write into archive: " + dest_file.string());
            }
            out.write(content.data(), static_cast<std::streamsize>(content.size()));
            out.close();

            ArchiveManifest manifest = load_manifest();
            ArchiveSource src;
            src.id = slug;
            src.name = name;
            src.source_type = "url";
            src.file_path = dest_file.filename().string();
            src.token_count = content.size() / 4;
            src.added_at = now_iso();
            manifest.sources.push_back(src);
            save_manifest(manifest);

            return ok("✅ Ingested URL '" + name + "' into course archive (" +
                      std::to_string(src.token_count) + " tokens, ID: " + slug + ").");
        } catch (const std::exception& e) {
            return fail("fetch_error", "❌ Failed to fetch and ingest URL: " + std::string(e.what()));
        }
    }

    if (action_name == "list_archive_sources") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded.");
        }
        ArchiveManifest manifest = load_manifest();
        Json j = Json::object();
        j["course_id"] = active_course_id_;
        j["sources_count"] = manifest.sources.size();
        std::size_t total_tokens = 0;
        Json list = Json::array();
        for (const auto& s : manifest.sources) {
            total_tokens += s.token_count;
            list.push_back(s.to_json());
        }
        j["total_tokens"] = total_tokens;
        j["sources"] = std::move(list);
        return ok(j.dump(2));
    }

    if (action_name == "search_archive") {
        if (!has_active_course()) {
            return fail("no_active_course", "❌ Error: No active course loaded.");
        }
        const std::string query = args.value("query", "");
        const int max_results = args.value("max_results", 5);
        if (query.empty()) {
            return fail("missing_query", "❌ query parameter is required.");
        }

        ArchiveManifest manifest = load_manifest();
        if (manifest.sources.empty()) {
            return ok("Archive search for '" + query + "': Course archive is empty. Add files or URLs using 'add_archive_source', 'ingest_archive_file', or 'ingest_archive_url'.");
        }

        // Split query into lowercase search keywords (len >= 3)
        std::vector<std::string> query_words;
        std::string cur;
        for (char c : query) {
            if (std::isalnum(static_cast<unsigned char>(c))) {
                cur.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
            } else if (!cur.empty()) {
                if (cur.size() >= 3) query_words.push_back(std::move(cur));
                cur.clear();
            }
        }
        if (cur.size() >= 3) query_words.push_back(std::move(cur));

        struct MatchPassage {
            std::string source_name;
            std::string header;
            std::string text;
            int score = 0;
        };
        std::vector<MatchPassage> matches;

        for (const auto& src : manifest.sources) {
            fs::path src_file = archive_sources_dir() / src.file_path;
            if (!fs::exists(src_file)) continue;

            std::ifstream in(src_file, std::ios::binary);
            if (!in.is_open()) continue;
            std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
            in.close();

            // Split content into paragraphs or sections
            std::istringstream stream(text);
            std::string line;
            std::string current_header = src.name;
            std::string current_block;

            auto flush_block = [&]() {
                if (current_block.empty()) return;
                std::string lower_block;
                lower_block.reserve(current_block.size());
                for (char ch : current_block) {
                    lower_block.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(ch))));
                }

                int score = 0;
                for (const auto& w : query_words) {
                    if (lower_block.find(w) != std::string::npos) {
                        score += 10;
                    }
                }
                if (score > 0) {
                    matches.push_back(MatchPassage{
                        .source_name = src.name,
                        .header = current_header,
                        .text = current_block.substr(0, 1000),
                        .score = score
                    });
                }
                current_block.clear();
            };

            while (std::getline(stream, line)) {
                if (line.starts_with("# ") || line.starts_with("## ") || line.starts_with("### ")) {
                    flush_block();
                    current_header = line;
                } else if (line.empty()) {
                    flush_block();
                } else {
                    if (!current_block.empty()) current_block += "\n";
                    current_block += line;
                }
            }
            flush_block();
        }

        if (matches.empty()) {
            return ok("Archive search for '" + query + "': 0 matching passages found in " +
                      std::to_string(manifest.sources.size()) + " archived documents.");
        }

        // Sort by relevance score descending
        std::sort(matches.begin(), matches.end(), [](const MatchPassage& a, const MatchPassage& b) {
            return a.score > b.score;
        });

        std::ostringstream ss;
        ss << "Found " << matches.size() << " grounded archive passages for query '" << query << "':\n\n";
        for (std::size_t i = 0; i < matches.size() && static_cast<int>(i) < max_results; ++i) {
            const auto& m = matches[i];
            ss << "[" << (i + 1) << "] Source: " << m.source_name << " (" << m.header << ")\n"
               << m.text << "\n\n";
        }
        return ok(ss.str());
    }

    if (action_name == "get_course_info") {
        if (!has_active_course()) {
            return ok(Json::object({{"active", false}}).dump());
        }
        auto j = course_.to_json();
        j["active"] = true;
        j["status"] = syllabus_.status;
        j["units"] = syllabus_.nodes.size();
        return ok(j.dump(2));
    }

    return fail("unknown_action", "LearnModule: unknown action " + action_name);
}

}  // namespace aquila::learn

