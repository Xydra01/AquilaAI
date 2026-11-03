#pragma once

#include "aquila/canvas/canvas_buffer.hpp"
#include "aquila/modules/module.hpp"

#include <optional>
#include <string>
#include <vector>

namespace aquila {

// File and symbol engine over a CanvasBuffer (R11, D10). Actions:
//   outline, read_region, inspect_symbol, surgical_edit, create_file, revert_file
// Every edit is validated first: an edit that adds tree-sitter syntax errors or
// git conflict markers is refused and nothing changes in RAM or on disk.
// review "auto" writes validated edits through at once; "manual" queues them as
// pending patches for the host (GUI / runner) to accept or reject.
class WorkspaceModule final : public ModuleBase {
public:
    explicit WorkspaceModule(const ModuleContext& ctx);

    [[nodiscard]] std::string module_id() const override { return "WorkspaceModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    // initial_state: {root_dir?, pinned_files?, review?: "auto"|"manual", max_output_chars?}
    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    // Host API (not exposed to the LLM).
    [[nodiscard]] std::vector<PendingPatch> pending();
    // A pending patch as a diff of on-disk bytes (CRLF/BOM applied); "" if unknown.
    [[nodiscard]] std::string disk_diff(const std::string& patch_id);
    ActionResult accept(const std::string& patch_id);
    ActionResult reject(const std::string& patch_id);
    ActionResult undo(const std::string& path);
    ActionResult redo(const std::string& path);

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    CanvasBuffer& canvas();
    ActionResult outline(const Json& args);
    ActionResult read_region(const Json& args);
    ActionResult inspect_symbol(const Json& args);
    ActionResult surgical_edit(const Json& args);
    ActionResult create_file(const Json& args);
    ActionResult revert_file(const Json& args);
    // Validates `new_text` against the current text, then proposes (and in auto mode accepts) it.
    ActionResult submit(const std::string& path, const std::string& old_text, const std::string& new_text,
                        const std::string& summary);
    [[nodiscard]] ActionResult capped(ActionResult r) const;

    ModuleContext ctx_;
    std::string root_dir_ = ".";
    std::vector<std::string> pinned_;
    bool manual_review_ = false;
    std::size_t max_output_chars_;
    std::optional<CanvasBuffer> canvas_;
};

}  // namespace aquila
