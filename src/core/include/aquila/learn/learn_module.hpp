#pragma once

#include "aquila/modules/module.hpp"

#include <cstddef>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::learn {

inline constexpr std::size_t kSyllabusMinNodes = 8;
inline constexpr std::size_t kSyllabusMinChildNodes = 5;
inline constexpr int kMasteryTierMax = 5;

struct SyllabusNode {
    std::string id;
    std::string title;
    std::optional<std::string> parent_id;
    int order = 0;
    int mastery_tier = 0;
    int tier_gate = 0;
    std::optional<std::string> required_assessment_id;

    [[nodiscard]] Json to_json() const;
    static SyllabusNode from_json(const Json& j);
};

struct Course {
    std::string id;
    std::string title = "Course";
    std::string topic;
    std::string intake = "files";
    std::string created_at;
    bool build_complete = false;

    [[nodiscard]] Json to_json() const;
    static Course from_json(const Json& j);
};

struct Syllabus {
    int version = 1;
    std::string title;
    std::string topic;
    std::string intake = "files";
    std::string status = "building";  // "building" or "ready"
    std::string current_node_id = "root";
    std::vector<SyllabusNode> nodes;
    std::vector<Json> assessments;

    [[nodiscard]] Json to_json() const;
    static Syllabus from_json(const Json& j);
};

[[nodiscard]] std::pair<bool, std::string> validate_syllabus_structure(const std::vector<SyllabusNode>& nodes);

struct ArchiveSource {
    std::string id;
    std::string name;
    std::string source_type;  // "file", "url", "text"
    std::string file_path;    // relative or absolute path
    std::size_t token_count = 0;
    std::string added_at;

    [[nodiscard]] Json to_json() const;
    static ArchiveSource from_json(const Json& j);
};

struct ArchiveManifest {
    std::vector<ArchiveSource> sources;

    [[nodiscard]] Json to_json() const;
    static ArchiveManifest from_json(const Json& j);
};

// LearnModule (Classroom & Archives domain, 5.2):
// Owns courses, syllabus hierarchy validation, mastery progression, and archive retrieval.
class LearnModule final : public ModuleBase {
public:
    LearnModule();
    explicit LearnModule(ModuleContext ctx);

    [[nodiscard]] std::string module_id() const override { return "LearnModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    // Direct accessors for tests & embedding
    [[nodiscard]] bool has_active_course() const noexcept { return !active_course_id_.empty(); }
    [[nodiscard]] const Course& course() const noexcept { return course_; }
    [[nodiscard]] const Syllabus& syllabus() const noexcept { return syllabus_; }
    [[nodiscard]] const std::string& instance_id() const noexcept { return instance_id_; }
    [[nodiscard]] std::filesystem::path course_dir() const;
    [[nodiscard]] std::filesystem::path syllabus_file() const;
    [[nodiscard]] std::filesystem::path assessments_dir() const;
    [[nodiscard]] std::filesystem::path archive_dir() const;
    [[nodiscard]] std::filesystem::path archive_manifest_file() const;
    [[nodiscard]] std::filesystem::path archive_sources_dir() const;
    [[nodiscard]] ArchiveManifest load_manifest() const;
    void save_manifest(const ArchiveManifest& manifest) const;

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    void save_course_record();
    bool load_course_record(const std::string& course_id, const std::string& instance_id);
    void save_syllabus_record();
    bool load_syllabus_record();

    ModuleContext ctx_;
    std::string instance_id_ = "default";
    std::string active_course_id_;
    Course course_;
    Syllabus syllabus_;
};

}  // namespace aquila::learn

