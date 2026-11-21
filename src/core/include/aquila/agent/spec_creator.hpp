#pragma once

#include "aquila/agent/micro_pass.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/inference/backend.hpp"
#include "aquila/json.hpp"
#include "aquila/types/task_ledger.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace aquila {

// Domain-specific grounding context collected from the workspace before spec generation.
struct DomainGroundingContext {
    std::string domain;                                    // "dev", "research", "writing", "learn", "persona", "general"
    std::string project_structure_summary;                 // File tree, directories, existing files
    std::string build_system_or_corpus_info;               // Build system info, repo details, or corpus summary
    std::vector<std::string> available_credential_domains; // Registered domains in CredentialStore
    bool is_existing_repo = false;
};

// Strongly-typed task specification generated pre-flight.
struct TaskSpec {
    std::string task_id;
    std::string timestamp;
    std::string title;
    std::string objective;
    std::string domain;
    std::string markdown_spec;                             // Full markdown specification
    std::vector<LedgerStep> milestones;                    // Parsed, actionable milestones for TaskLedger
    std::vector<std::string> target_deliverables;
    std::filesystem::path saved_path;
    std::uint64_t synthesis_tokens = 0;

    bool operator==(const TaskSpec&) const = default;
};

void to_json(Json& j, const TaskSpec& v);
void from_json(const Json& j, TaskSpec& v, const std::string& path);

// Options for the pre-flight Spec Creator.
struct SpecCreatorOptions {
    std::string user_prompt;
    RecipeCartridge recipe;
    std::filesystem::path workspace_root = ".";
    bool include_workspace_grounding = true;
    std::uint32_t max_tokens = 768;
    double temperature = 0.2;
    std::optional<bool> think = false;
    TokenCallback on_token = nullptr;
};

class SpecCreator {
public:
    // Generates a TaskSpec using an isolated single-turn micro-pass with KV-cache rollback.
    [[nodiscard]] static TaskSpec generate_spec(
        IInferenceBackend& backend,
        const SpecCreatorOptions& options);

    // Gathers domain-aware context from the workspace (repo build files, corpus, credentials).
    [[nodiscard]] static DomainGroundingContext inspect_grounding_context(
        const RecipeCartridge& recipe,
        const std::filesystem::path& workspace_root);

    // Builds the planner system prompt with domain rules and required output schema.
    [[nodiscard]] static std::string build_system_prompt(
        const RecipeCartridge& recipe,
        const DomainGroundingContext& grounding);

    // Builds the user prompt containing the user request and grounding context.
    [[nodiscard]] static std::string build_user_prompt(
        const std::string& user_prompt,
        const RecipeCartridge& recipe,
        const DomainGroundingContext& grounding);

    // Parses milestones from markdown spec and enriches them with mandatory recipe exit gates.
    [[nodiscard]] static std::vector<LedgerStep> parse_milestones(
        std::string_view markdown,
        const RecipeCartridge& recipe);

    // Saves the spec to specs/<timestamp>_<task_id>_spec.md and specs/latest_spec.md.
    static std::filesystem::path save_spec_to_workspace(
        TaskSpec& spec,
        const std::filesystem::path& workspace_root);

    // Extracts the title from markdown (e.g. from '# Task Specification: <Title>').
    [[nodiscard]] static std::string extract_title(std::string_view markdown);
};

}  // namespace aquila

