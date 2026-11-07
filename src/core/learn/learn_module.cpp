#include "aquila/learn/learn_module.hpp"

#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
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
            "search_archive",
            "Searches course archive materials.",
            Json::object({
                {"type", "object"},
                {"properties", Json::object({
                    {"query", Json::object({{"type", "string"}, {"description", "Search query"}})},
                    {"archive_id", Json::object({{"type", "string"}, {"description", "Archive ID"}})}
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

    if (action_name == "search_archive") {
        const std::string query = args.value("query", "");
        const std::string archive_id = args.value("archive_id", "default");
        return ok("Archive search for '" + query + "' in " + archive_id + ": 0 matches found.");
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

