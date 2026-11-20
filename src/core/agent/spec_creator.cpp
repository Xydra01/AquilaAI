#include "aquila/agent/spec_creator.hpp"
#include "aquila/knowledge/credential_store.hpp"
#include "aquila/json.hpp"

#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <regex>
#include <sstream>
#include <algorithm>

namespace aquila {

namespace {

std::string get_current_timestamp() {
    const auto now = std::chrono::system_clock::now();
    const auto in_time_t = std::chrono::system_clock::to_time_t(now);
    std::tm bt{};
#if defined(_WIN32)
    localtime_s(&bt, &in_time_t);
#else
    localtime_r(&in_time_t, &bt);
#endif
    std::ostringstream ss;
    ss << std::put_time(&bt, "%Y%m%d_%H%M%S");
    return ss.str();
}

bool is_ignored_directory(const std::string& name) {
    static const std::vector<std::string> ignored = {
        ".git", ".svn", ".hg", "build", "out", "target", "node_modules",
        "__pycache__", ".venv", "venv", ".vs", ".idea", ".vscode", "bin", "obj", ".aquila"
    };
    return std::find(ignored.begin(), ignored.end(), name) != ignored.end();
}

}  // namespace

void to_json(Json& j, const TaskSpec& v) {
    j = Json{
        {"task_id", v.task_id},
        {"timestamp", v.timestamp},
        {"title", v.title},
        {"objective", v.objective},
        {"domain", v.domain},
        {"markdown_spec", v.markdown_spec},
        {"target_deliverables", v.target_deliverables},
        {"saved_path", v.saved_path.string()},
        {"synthesis_tokens", v.synthesis_tokens}
    };
    Json milestones_arr = Json::array();
    for (const auto& step : v.milestones) {
        Json s;
        to_json(s, step);
        milestones_arr.push_back(std::move(s));
    }
    j["milestones"] = std::move(milestones_arr);
}

void from_json(const Json& j, TaskSpec& v, const std::string& path) {
    json_io::reject_unknown(j, path, {
        "task_id", "timestamp", "title", "objective", "domain",
        "markdown_spec", "milestones", "target_deliverables", "saved_path", "synthesis_tokens"
    });
    if (j.contains("task_id")) v.task_id = j["task_id"].get<std::string>();
    if (j.contains("timestamp")) v.timestamp = j["timestamp"].get<std::string>();
    if (j.contains("title")) v.title = j["title"].get<std::string>();
    if (j.contains("objective")) v.objective = j["objective"].get<std::string>();
    if (j.contains("domain")) v.domain = j["domain"].get<std::string>();
    if (j.contains("markdown_spec")) v.markdown_spec = j["markdown_spec"].get<std::string>();
    if (j.contains("target_deliverables")) {
        v.target_deliverables = j["target_deliverables"].get<std::vector<std::string>>();
    }
    if (j.contains("saved_path")) {
        v.saved_path = j["saved_path"].get<std::string>();
    }
    if (j.contains("synthesis_tokens")) {
        v.synthesis_tokens = j["synthesis_tokens"].get<std::uint64_t>();
    }
    if (j.contains("milestones") && j["milestones"].is_array()) {
        v.milestones.clear();
        for (const auto& item : j["milestones"]) {
            LedgerStep step;
            from_json(item, step, path + "/milestones");
            v.milestones.push_back(std::move(step));
        }
    }
}

DomainGroundingContext SpecCreator::inspect_grounding_context(
    const RecipeCartridge& recipe,
    const std::filesystem::path& workspace_root) {
    DomainGroundingContext ctx;

    const std::string& r_id = recipe.recipe_id;
    if (r_id.find("dev") != std::string::npos || r_id.find("code") != std::string::npos) {
        ctx.domain = "dev";
    } else if (r_id.find("research") != std::string::npos || r_id.find("knowledge") != std::string::npos) {
        ctx.domain = "research";
    } else if (r_id.find("writing") != std::string::npos) {
        ctx.domain = "writing";
    } else if (r_id.find("learn") != std::string::npos) {
        ctx.domain = "learn";
    } else if (r_id.find("persona") != std::string::npos) {
        ctx.domain = "persona";
    } else {
        ctx.domain = "general";
    }

    std::error_code ec;
    if (!std::filesystem::exists(workspace_root, ec)) {
        return ctx;
    }

    if (ctx.domain == "dev") {
        ctx.is_existing_repo = std::filesystem::exists(workspace_root / ".git", ec);

        std::vector<std::string> detected_build_systems;
        if (std::filesystem::exists(workspace_root / "CMakeLists.txt", ec)) {
            detected_build_systems.push_back("CMake (C/C++)");
        }
        if (std::filesystem::exists(workspace_root / "Cargo.toml", ec)) {
            detected_build_systems.push_back("Cargo (Rust)");
        }
        if (std::filesystem::exists(workspace_root / "package.json", ec)) {
            detected_build_systems.push_back("npm/yarn (Node.js/TypeScript)");
        }
        if (std::filesystem::exists(workspace_root / "pyproject.toml", ec) ||
            std::filesystem::exists(workspace_root / "requirements.txt", ec) ||
            std::filesystem::exists(workspace_root / "setup.py", ec)) {
            detected_build_systems.push_back("Python (pyproject/requirements)");
        }
        if (std::filesystem::exists(workspace_root / "go.mod", ec)) {
            detected_build_systems.push_back("Go (go.mod)");
        }
        if (std::filesystem::exists(workspace_root / "Makefile", ec)) {
            detected_build_systems.push_back("Make (Makefile)");
        }

        if (!detected_build_systems.empty()) {
            ctx.build_system_or_corpus_info = "Detected Project Systems: ";
            for (std::size_t i = 0; i < detected_build_systems.size(); ++i) {
                if (i > 0) ctx.build_system_or_corpus_info += ", ";
                ctx.build_system_or_corpus_info += detected_build_systems[i];
            }
        } else {
            ctx.build_system_or_corpus_info = ctx.is_existing_repo ? "Existing Git Repository (no standard top-level build manifest detected)"
                                                                   : "Greenfield / Custom Workspace";
        }

        // Gather top 2 levels of file tree
        std::ostringstream tree_ss;
        std::size_t entry_count = 0;
        try {
            for (const auto& entry : std::filesystem::directory_iterator(workspace_root, ec)) {
                if (entry_count >= 30) {
                    tree_ss << "  ... (additional files omitted)\n";
                    break;
                }
                const std::string name = entry.path().filename().string();
                if (name.starts_with(".") && name != ".git") continue;
                if (is_ignored_directory(name)) continue;

                if (entry.is_directory(ec)) {
                    tree_ss << "- " << name << "/\n";
                    ++entry_count;
                    // Read 1 sub-level
                    for (const auto& sub : std::filesystem::directory_iterator(entry.path(), ec)) {
                        if (entry_count >= 30) break;
                        const std::string sub_name = sub.path().filename().string();
                        if (is_ignored_directory(sub_name)) continue;
                        tree_ss << "  - " << sub_name << (sub.is_directory(ec) ? "/" : "") << "\n";
                        ++entry_count;
                    }
                } else {
                    tree_ss << "- " << name << "\n";
                    ++entry_count;
                }
            }
        } catch (...) {}
        ctx.project_structure_summary = tree_ss.str();

        // Read README snippet if available
        std::filesystem::path readme_path = workspace_root / "README.md";
        if (!std::filesystem::exists(readme_path, ec)) {
            readme_path = workspace_root / "readme.md";
        }
        if (std::filesystem::exists(readme_path, ec)) {
            std::ifstream in(readme_path, std::ios::binary);
            if (in.is_open()) {
                std::string buf(800, '\0');
                in.read(buf.data(), static_cast<std::streamsize>(buf.size()));
                buf.resize(static_cast<std::size_t>(in.gcount()));
                if (!buf.empty()) {
                    ctx.build_system_or_corpus_info += "\nREADME Overview:\n" + buf;
                }
            }
        }
    } else if (ctx.domain == "research") {
        // Collect credential domains
        try {
            ctx.available_credential_domains = aquila::knowledge::CredentialStore::default_store().list_domains();
        } catch (...) {}

        // Enumerate documents in workspace or docs/
        std::ostringstream corpus_ss;
        std::size_t doc_count = 0;
        try {
            for (const auto& entry : std::filesystem::directory_iterator(workspace_root, ec)) {
                if (doc_count >= 20) break;
                const std::string name = entry.path().filename().string();
                const std::string ext = entry.path().extension().string();
                if (ext == ".md" || ext == ".txt" || ext == ".pdf" || ext == ".json" || ext == ".csv") {
                    corpus_ss << "- " << name << "\n";
                    ++doc_count;
                }
            }
            const auto docs_dir = workspace_root / "docs";
            if (std::filesystem::exists(docs_dir, ec)) {
                for (const auto& entry : std::filesystem::directory_iterator(docs_dir, ec)) {
                    if (doc_count >= 20) break;
                    corpus_ss << "- docs/" << entry.path().filename().string() << "\n";
                    ++doc_count;
                }
            }
        } catch (...) {}

        if (doc_count > 0) {
            ctx.project_structure_summary = "Local Document Corpus:\n" + corpus_ss.str();
        }
    } else if (ctx.domain == "writing" || ctx.domain == "learn" || ctx.domain == "persona") {
        std::ostringstream assets_ss;
        std::size_t count = 0;
        try {
            for (const auto& entry : std::filesystem::directory_iterator(workspace_root, ec)) {
                if (count >= 20) break;
                const std::string ext = entry.path().extension().string();
                if (ext == ".md" || ext == ".txt" || ext == ".json") {
                    assets_ss << "- " << entry.path().filename().string() << "\n";
                    ++count;
                }
            }
        } catch (...) {}
        if (count > 0) {
            ctx.project_structure_summary = "Existing Workspace Assets:\n" + assets_ss.str();
        }
    }

    return ctx;
}

std::string SpecCreator::build_system_prompt(
    const RecipeCartridge& recipe,
    const DomainGroundingContext& grounding) {
    std::string prompt;
    prompt += "You are the Aquila Architectural Planner & Spec Synthesizer.\n"
              "Your mission is to transform user prompts into a rigorous, actionable Technical Specification.\n"
              "This specification serves as the execution blueprint for the Aquila autonomous agent loop.\n"
              "It must eliminate ambiguity, define concrete verifiable milestones, and provide unambiguous Definition of Done criteria.\n\n"
              "You are planning for recipe cartridge: '" + recipe.recipe_id + "' (Domain: " + grounding.domain + ").\n\n";

    if (grounding.domain == "research") {
        prompt += "DOMAIN DIRECTIVE - RESEARCH:\n"
                  "- Plan an authoritative research itinerary across web and academic sources.\n"
                  "- The final deliverable MUST be 'research_report.md' and MUST include four formal sections:\n"
                  "  1. ## Executive Summary\n"
                  "  2. ## Key Findings & Evidence (with structured markdown data tables & quantitative metrics)\n"
                  "  3. ## Detailed Analysis & Implications\n"
                  "  4. ## References & Sources (with at least 3 distinct numbered real citations/URLs/DOIs)\n"
                  "- Milestones must include: targeted search queries, source verification, storing verified facts via KnowledgeModule.store_fact, compiling research_report.md, updating TaskLedger, and recipe completion.\n\n";
    } else if (grounding.domain == "dev") {
        prompt += "DOMAIN DIRECTIVE - DEVELOPMENT:\n"
                  "- Inspect the codebase grounding to identify whether this is a greenfield project or refactor/addition to an existing repo.\n"
                  "- Clearly specify target files to create or modify, function signatures, and dependency requirements.\n"
                  "- The final deliverable must execute cleanly with zero stub bodies (no TODO/pass), pass non-interactive verification, update TaskLedger, and complete the recipe.\n\n";
    } else {
        prompt += "DOMAIN DIRECTIVE - GENERAL:\n"
                  "- Formulate concrete, ordered milestones that guide the agent from initial exploration to final deliverable creation.\n"
                  "- Ensure milestones conclude with TaskLedger update and recipe completion.\n\n";
    }

    prompt += "OUTPUT FORMAT REQUIREMENT:\n"
              "Your response must be a comprehensive Markdown document with these exact top-level sections:\n"
              "# Task Specification: <Clear Descriptive Title>\n\n"
              "## 1. Objective & Scope\n"
              "- Concise mission statement\n"
              "- In-scope requirements\n"
              "- Explicit out-of-scope boundaries\n\n"
              "## 2. Technical Context & Strategy\n"
              "- Grounding assessment (existing files, build systems, or research corpus)\n"
              "- Strategic approach and architectural choices\n\n"
              "## 3. Key Deliverables & Validation Criteria\n"
              "- Expected deliverables (file paths, formats, required sections)\n"
              "- Acceptance criteria and verification tests\n\n"
              "## 4. Execution Milestones & Task Ledger\n"
              "Detail the step-by-step procedure. At the end of this section, provide the milestones in a fenced JSON block tagged ```json:milestones containing an array of objects with 'id' and 'description':\n"
              "```json:milestones\n"
              "[\n"
              "  {\"id\": \"step_1\", \"description\": \"Actionable imperative instruction 1\"},\n"
              "  {\"id\": \"step_2\", \"description\": \"Actionable imperative instruction 2\"}\n"
              "]\n"
              "```\n\n"
              "## 5. Constraints & Exit Gate Checklist\n"
              "- Operational constraints (tool choices, token budgets, exit criteria)\n";

    return prompt;
}

std::string SpecCreator::build_user_prompt(
    const std::string& user_prompt,
    const RecipeCartridge& recipe,
    const DomainGroundingContext& grounding) {
    std::string text = "USER REQUEST:\n\"" + user_prompt + "\"\n\n";
    text += "RECIPE CARTRIDGE: " + recipe.recipe_id + "\n";

    if (!grounding.build_system_or_corpus_info.empty()) {
        text += "ENVIRONMENT GROUNDING:\n" + grounding.build_system_or_corpus_info + "\n\n";
    }

    if (!grounding.project_structure_summary.empty()) {
        text += "WORKSPACE STRUCTURE:\n" + grounding.project_structure_summary + "\n\n";
    }

    if (!grounding.available_credential_domains.empty()) {
        text += "AUTHENTICATED DOMAINS AVAILABLE (CredentialStore):\n";
        for (const auto& d : grounding.available_credential_domains) {
            text += "- " + d + "\n";
        }
        text += "\n";
    }

    text += "Please synthesize the complete Task Specification and execution milestones for this mission.";
    return text;
}

std::string SpecCreator::extract_title(std::string_view markdown) {
    static const std::regex title_re(R"(#\s*(?:Task Specification:\s*)?([^\r\n]+))", std::regex::icase);
    std::string s(markdown);
    std::smatch match;
    if (std::regex_search(s, match, title_re) && match.size() > 1) {
        std::string title = match[1].str();
        while (!title.empty() && (title.back() == ' ' || title.back() == '\t')) title.pop_back();
        while (!title.empty() && (title.front() == ' ' || title.front() == '\t')) title.erase(title.begin());
        return title;
    }
    return "Task Specification";
}

std::vector<LedgerStep> SpecCreator::parse_milestones(
    std::string_view markdown,
    const RecipeCartridge& recipe) {
    std::vector<LedgerStep> steps;

    // Pattern 1: Look for ```json:milestones or ```json with array
    static const std::regex json_block_re(R"(```json(?::milestones)?\s*(\[\s*\{[\s\S]*?\}\s*\])\s*```)", std::regex::icase);
    std::string s(markdown);
    std::smatch match;
    if (std::regex_search(s, match, json_block_re) && match.size() > 1) {
        try {
            Json parsed = Json::parse(match[1].str());
            if (parsed.is_array()) {
                std::size_t idx = 1;
                for (const auto& item : parsed) {
                    if (item.is_object() && item.contains("description")) {
                        LedgerStep st;
                        st.id = item.value("id", "step_" + std::to_string(idx));
                        st.description = item.value("description", "");
                        st.status = LedgerStepStatus::pending;
                        if (!st.description.empty()) {
                            steps.push_back(std::move(st));
                            ++idx;
                        }
                    }
                }
            }
        } catch (...) {}
    }

    // Pattern 2 Fallback: Regex parse numbered list under milestones
    if (steps.empty()) {
        static const std::regex milestone_item_re(R"(^\s*(?:(\d+)[\.\)]|- \[\s*\])\s*(.+)$)");
        std::istringstream ss(s);
        std::string line;
        bool in_milestones = false;
        std::size_t idx = 1;
        while (std::getline(ss, line)) {
            if (line.find("## 4.") != std::string::npos || line.find("Milestones") != std::string::npos) {
                in_milestones = true;
                continue;
            }
            if (in_milestones && line.starts_with("## ")) {
                in_milestones = false;
                break;
            }
            if (in_milestones) {
                std::smatch lm;
                if (std::regex_search(line, lm, milestone_item_re) && lm.size() > 2) {
                    LedgerStep st;
                    st.id = "step_" + std::to_string(idx++);
                    st.description = lm[2].str();
                    st.status = LedgerStepStatus::pending;
                    steps.push_back(std::move(st));
                }
            }
        }
    }

    // Fallback: Use recipe's built-in scratchpad checklist if parsing yielded nothing
    if (steps.empty()) {
        std::size_t idx = 1;
        for (const auto& item : recipe.scratchpad_checklist) {
            LedgerStep st;
            st.id = "step_" + std::to_string(idx++);
            st.description = item;
            st.status = LedgerStepStatus::pending;
            steps.push_back(std::move(st));
        }
    }

    // Enriched Synthesis (Option B): Ensure mandatory exit-gate steps exist
    bool has_ledger_step = false;
    bool has_complete_step = false;
    for (const auto& st : steps) {
        const std::string desc_lower = [&st]() {
            std::string d = st.description;
            std::transform(d.begin(), d.end(), d.begin(), ::tolower);
            return d;
        }();
        if (desc_lower.find("update_task_ledger") != std::string::npos ||
            desc_lower.find("task ledger") != std::string::npos) {
            has_ledger_step = true;
        }
        if (desc_lower.find("complete_recipe") != std::string::npos ||
            desc_lower.find("complete recipe") != std::string::npos) {
            has_complete_step = true;
        }
    }

    if (!has_ledger_step) {
        LedgerStep st;
        st.id = "step_" + std::to_string(steps.size() + 1);
        st.description = "Call OrchestratorModule update_task_ledger to mark completed milestones before finishing";
        st.status = LedgerStepStatus::pending;
        steps.push_back(std::move(st));
    }

    if (!has_complete_step) {
        LedgerStep st;
        st.id = "step_" + std::to_string(steps.size() + 1);
        st.description = "Call OrchestratorModule complete_recipe to finish the task";
        st.status = LedgerStepStatus::pending;
        steps.push_back(std::move(st));
    }

    // Normalize IDs to step_1, step_2, ...
    for (std::size_t i = 0; i < steps.size(); ++i) {
        steps[i].id = "step_" + std::to_string(i + 1);
    }

    return steps;
}

std::filesystem::path SpecCreator::save_spec_to_workspace(
    TaskSpec& spec,
    const std::filesystem::path& workspace_root) {
    std::error_code ec;
    const std::filesystem::path specs_dir = workspace_root / "specs";
    std::filesystem::create_directories(specs_dir, ec);

    if (spec.timestamp.empty()) {
        spec.timestamp = get_current_timestamp();
    }
    const std::string filename = spec.timestamp + "_" + (spec.task_id.empty() ? "task" : spec.task_id) + "_spec.md";
    const std::filesystem::path archive_path = specs_dir / filename;

    // Write archive file
    {
        std::ofstream out(archive_path, std::ios::binary);
        if (out.is_open()) {
            out.write(spec.markdown_spec.data(), static_cast<std::streamsize>(spec.markdown_spec.size()));
        }
    }

    // Write latest symlink / file copy
    const std::filesystem::path latest_path = specs_dir / "latest_spec.md";
    {
        std::ofstream out(latest_path, std::ios::binary);
        if (out.is_open()) {
            out.write(spec.markdown_spec.data(), static_cast<std::streamsize>(spec.markdown_spec.size()));
        }
    }

    spec.saved_path = archive_path;
    return archive_path;
}

TaskSpec SpecCreator::generate_spec(
    IInferenceBackend& backend,
    const SpecCreatorOptions& options) {
    DomainGroundingContext grounding;
    if (options.include_workspace_grounding) {
        grounding = inspect_grounding_context(options.recipe, options.workspace_root);
    } else {
        grounding.domain = "general";
    }

    const std::string sys_prompt = build_system_prompt(options.recipe, grounding);
    const std::string usr_prompt = build_user_prompt(options.user_prompt, options.recipe, grounding);

    MicroPassOptions pass_opts;
    pass_opts.system_prompt = sys_prompt;
    pass_opts.user_prompt = usr_prompt;
    pass_opts.temperature = options.temperature;
    pass_opts.max_tokens = options.max_tokens;
    pass_opts.on_token = options.on_token;

    MicroPassResult res = run_micro_pass(backend, pass_opts);

    TaskSpec spec;
    spec.task_id = options.recipe.recipe_id;
    spec.timestamp = get_current_timestamp();
    spec.domain = grounding.domain;
    spec.objective = options.user_prompt;
    spec.synthesis_tokens = res.completion_tokens;

    if (res.success && !res.content.empty()) {
        spec.markdown_spec = res.content;
    } else {
        // Fallback default spec if generation failed
        std::ostringstream fb;
        fb << "# Task Specification: " << options.recipe.recipe_id << "\n\n"
           << "## 1. Objective & Scope\n" << options.user_prompt << "\n\n"
           << "## 2. Technical Context & Strategy\n"
           << "Executing standard procedural workflow for recipe " << options.recipe.recipe_id << ".\n\n"
           << "## 3. Key Deliverables & Validation Criteria\n"
           << "Satisfy all recipe post-validation exit gates.\n\n"
           << "## 4. Execution Milestones & Task Ledger\n";
        for (std::size_t i = 0; i < options.recipe.scratchpad_checklist.size(); ++i) {
            fb << (i + 1) << ". " << options.recipe.scratchpad_checklist[i] << "\n";
        }
        fb << "\n## 5. Constraints & Exit Gate Checklist\n"
           << "Standard exit gate validation.\n";
        spec.markdown_spec = fb.str();
    }

    spec.title = extract_title(spec.markdown_spec);
    spec.milestones = parse_milestones(spec.markdown_spec, options.recipe);

    // Save spec to workspace
    save_spec_to_workspace(spec, options.workspace_root);

    return spec;
}

}  // namespace aquila

