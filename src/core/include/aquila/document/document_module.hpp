#pragma once

#include "aquila/modules/module.hpp"

#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::document {

struct DocumentSection {
    std::string header;
    std::string content;

    bool operator==(const DocumentSection&) const = default;
};

struct DraftState {
    std::string title;
    std::string synopsis;
    std::vector<DocumentSection> sections;
    std::size_t word_count = 0;

    [[nodiscard]] std::size_t compute_word_count() const noexcept;
    [[nodiscard]] Json to_json() const;
    static DraftState from_json(const Json& j);
};

// Normalization functions for writing canvas
[[nodiscard]] std::string normalize_section_header(std::string_view header);
[[nodiscard]] std::string strip_redundant_leading_heading(std::string_view content, std::string_view section_header);

// DocumentModule (Writing Canvas domain, R11, 5.2):
// Owns active draft state, outline/sections, compilation to Markdown deliverables.
class DocumentModule final : public ModuleBase {
public:
    DocumentModule();
    explicit DocumentModule(ModuleContext ctx);

    [[nodiscard]] std::string module_id() const override { return "DocumentModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    // Direct accessors for tests & embedding
    [[nodiscard]] bool has_active_draft() const noexcept { return active_; }
    [[nodiscard]] const DraftState& draft() const noexcept { return draft_; }
    [[nodiscard]] std::filesystem::path drafts_dir() const;
    [[nodiscard]] std::filesystem::path active_draft_file() const;

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    void save_active_draft();
    bool load_active_draft();
    void clear_active_draft();

    ModuleContext ctx_;
    bool active_ = false;
    DraftState draft_;
};

}  // namespace aquila::document

