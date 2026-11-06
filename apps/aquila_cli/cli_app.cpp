// apps/aquila_cli/cli_app.cpp
#include "cli_app.hpp"

#include "aquila/core.hpp"
#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/inference/ollama_backend.hpp"
#include "aquila/modules/registry.hpp"

#if AQUILA_HAS_LLAMACPP
#include "aquila/inference/llama_backend.hpp"
#endif

#include <algorithm>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string_view>

namespace aquila::cli {

int print_version(std::ostream& out) {
    const auto v = aquila::version();
    out << "aquila " << std::string_view(v.data(), v.size()) << "\n";
    return 0;
}

int print_help(std::ostream& out) {
    const auto v = aquila::version();
    out << "Aquila AI CLI - Autonomous Multi-Domain Agent Rebuild (version "
        << std::string_view(v.data(), v.size()) << ")\n\n"
        << "Usage: aquila_cli <command> [options]\n\n"
        << "Commands:\n"
        << "  run           Execute a workflow recipe cartridge\n"
        << "  chat          Interactive terminal chat REPL\n"
        << "  list-recipes  List all builtin and workspace recipe cartridges\n"
        << "  list-modules  List all registered modules and action schemas\n"
        << "  eval          Evaluate recipe cartridges against verification rubrics\n"
        << "  version       Print version information (--version, -v)\n"
        << "  help          Show this help message (--help, -h)\n\n"
        << "Options for 'run':\n"
        << "  --recipe, -r <id>    Recipe cartridge ID or .recipe.json file path (required)\n"
        << "  --task, -t <prompt>  Task prompt (defaults to recipe goal_template)\n"
        << "  --workspace, -w <p>  Workspace root directory (defaults to '.')\n"
        << "  --tier <cpu|gpu>     Runtime tier profile (default: cpu)\n"
        << "  --backend <ollama|llama> Inference backend (default: ollama)\n"
        << "  --model, -m <name>   Model name or GGUF path\n"
        << "  --host <url>         Ollama host (default: http://127.0.0.1:11434)\n"
        << "  --verbose, -v        Enable verbose turn outputs\n\n"
        << "Options for 'chat':\n"
        << "  --tier <cpu|gpu>     Runtime tier profile (default: cpu)\n"
        << "  --backend <name>     Inference backend (default: ollama)\n"
        << "  --model, -m <name>   Model name or GGUF path\n"
        << "  --host <url>         Ollama host URL\n";
    return 0;
}

int list_recipes(const std::filesystem::path& workspace_root, std::ostream& out) {
    const auto builtins = all_builtin_recipes();
    out << "Builtin Recipe Cartridges (" << builtins.size() << "):\n";
    for (const auto& r : builtins) {
        out << "  - " << std::left << std::setw(26) << r.recipe_id;
        out << " [Modules: ";
        for (std::size_t i = 0; i < r.load_modules.size(); ++i) {
            if (i > 0) out << ", ";
            out << r.load_modules[i].module;
        }
        out << "]\n";
    }

    std::error_code ec;
    const auto custom_dir = workspace_root / ".aquila" / "recipes";
    if (std::filesystem::exists(custom_dir, ec) && std::filesystem::is_directory(custom_dir, ec)) {
        out << "\nWorkspace Recipes (" << custom_dir.string() << "):\n";
        bool any = false;
        for (const auto& entry : std::filesystem::directory_iterator(custom_dir, ec)) {
            if (entry.is_regular_file() && entry.path().extension() == ".json") {
                any = true;
                out << "  - " << entry.path().stem().string() << " (" << entry.path().filename().string() << ")\n";
            }
        }
        if (!any) {
            out << "  (none found)\n";
        }
    }
    return 0;
}

int list_modules(std::ostream& out) {
    const auto registry = ModuleRegistry::builtin();
    ModuleContext ctx;
    ctx.workspace_root = ".";

    const std::vector<std::string> module_names = {
        "WorkspaceModule",
        "ExecutionModule",
        "OrchestratorModule",
        "KnowledgeModule",
        "DocumentModule",
        "PersonaModule",
        "LearnModule"
    };

    out << "Registered Modules (" << module_names.size() << "):\n";
    for (const auto& name : module_names) {
        out << "\n  [" << name << "]\n";
        try {
            auto mod = registry.create(name, ctx);
            const auto actions = mod->get_actions();
            for (const auto& act : actions) {
                out << "    * " << std::left << std::setw(24) << act.action_name
                    << " : " << act.description << "\n";
            }
        } catch (const std::exception& e) {
            out << "    (could not inspect actions: " << e.what() << ")\n";
        }
    }
    return 0;
}

namespace {

std::optional<RecipeCartridge> resolve_recipe(const std::string& id_or_path,
                                              const std::filesystem::path& workspace_root) {
    for (const auto& r : all_builtin_recipes()) {
        if (r.recipe_id == id_or_path) {
            return r;
        }
    }

    // Try path directly
    std::filesystem::path p(id_or_path);
    if (!std::filesystem::exists(p)) {
        // Try under .aquila/recipes/<id_or_path>.recipe.json
        p = workspace_root / ".aquila" / "recipes" / (id_or_path + ".recipe.json");
    }
    if (!std::filesystem::exists(p)) {
        p = workspace_root / ".aquila" / "recipes" / id_or_path;
    }

    if (std::filesystem::exists(p)) {
        std::ifstream ifs(p, std::ios::binary);
        if (ifs) {
            std::string content((std::istreambuf_iterator<char>(ifs)),
                                std::istreambuf_iterator<char>());
            try {
                return parse<RecipeCartridge>(content);
            } catch (...) {
                return std::nullopt;
            }
        }
    }

    return std::nullopt;
}

}  // namespace

int run_recipe(const CliOptions& opts, std::ostream& out, std::ostream& err,
               IInferenceBackend* custom_backend) {
    if (opts.recipe_id.empty()) {
        err << "Error: --recipe <id> is required for 'run' command.\n";
        return 2;
    }

    auto resolved = resolve_recipe(opts.recipe_id, opts.workspace_root);
    if (!resolved) {
        err << "Error: Could not find or parse recipe '" << opts.recipe_id << "'.\n";
        return 2;
    }

    RecipeCartridge recipe = std::move(*resolved);
    auto resolver = [&opts](const std::string& inc_id) {
        return resolve_recipe(inc_id, opts.workspace_root);
    };
    try {
        recipe = resolve_includes(recipe, resolver);
    } catch (const std::exception& e) {
        err << "Error: Failed to resolve recipe includes: " << e.what() << "\n";
        return 2;
    }

    const std::string task = opts.task_prompt.empty() ? recipe.goal_template : opts.task_prompt;

    out << "Starting recipe '" << recipe.recipe_id << "'...\n";
    out << "Workspace: " << std::filesystem::absolute(opts.workspace_root).string() << "\n";
    out << "Tier: " << opts.tier_name << "\n";
    out << "Task: " << task << "\n\n";

    LoopConfig config;
    if (opts.tier_name == "gpu") {
        config.tier = RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram);
    } else {
        config.tier = RuntimeTierConfig::default_config();
    }
    config.task_id = "cli-" + recipe.recipe_id;
    config.mode = "task";
    config.context_strategy = CondenserStrategy::sac;

    config.on_token = [&out](std::string_view tok, std::string_view) -> bool {
        out << tok;
        out.flush();
        return true;
    };

    config.on_turn = [&out, &opts](const TurnRecord& rec) {
        out << "\n[Turn " << rec.index + 1;
        if (rec.call) {
            out << ": " << rec.call->module << "." << rec.call->action;
        }
        if (rec.interaction) {
            out << " -> " << (rec.interaction->result.success ? "OK" : rec.interaction->result.error_code);
        }
        out << "]\n";
        if (opts.verbose && rec.interaction) {
            out << "Output: " << rec.interaction->result.llm_facing_output << "\n";
        }
        out.flush();
    };

    ModuleRegistry registry = ModuleRegistry::builtin();
    ModuleContext mod_ctx;
    mod_ctx.workspace_root = opts.workspace_root;

    if (custom_backend != nullptr) {
        AgentLoop loop(*custom_backend, registry, mod_ctx);
        const auto res = loop.run(recipe, task, config);
        out << "\n========================================\n"
            << "Recipe execution " << (res.success ? "SUCCEEDED" : "FAILED") << "\n"
            << "Outcome: " << (res.outcome == LoopOutcome::success ? "success" : (res.outcome == LoopOutcome::aborted ? "aborted" : "turn_limit")) << "\n"
            << "Turns: " << res.transcript.size() << "\n";
        if (!res.completion_output.empty()) {
            out << "Completion Output: " << res.completion_output << "\n";
        }
        out << "========================================\n";
        return res.success ? 0 : 1;
    }

    if (opts.backend_type == "llama") {
#if AQUILA_HAS_LLAMACPP
        if (opts.model_name.empty()) {
            err << "Error: --model <path_to_gguf> is required for llama.cpp backend.\n";
            return 2;
        }
        LlamaConfig lcfg;
        lcfg.model_path = opts.model_name;
        lcfg.n_ctx = static_cast<std::uint32_t>(config.tier.limits.max_rolling_tools * 1024U);
        if (opts.tier_name == "gpu") {
            lcfg.n_gpu_layers = 999;
        }
        try {
            LlamaCppBackend backend(lcfg);
            AgentLoop loop(backend, registry, mod_ctx);
            const auto res = loop.run(recipe, task, config);
            out << "\n========================================\n"
                << "Recipe execution " << (res.success ? "SUCCEEDED" : "FAILED") << "\n"
                << "Outcome: " << (res.outcome == LoopOutcome::success ? "success" : "failure") << "\n"
                << "Turns: " << res.transcript.size() << "\n";
            if (!res.completion_output.empty()) {
                out << "Completion Output: " << res.completion_output << "\n";
            }
            out << "========================================\n";
            return res.success ? 0 : 1;
        } catch (const std::exception& ex) {
            err << "Error: LlamaCpp initialization failed: " << ex.what() << "\n";
            return 1;
        }
#else
        err << "Error: LlamaCpp backend was not enabled in this build.\n";
        return 1;
#endif
    }

    OllamaConfig ocfg;
    ocfg.base_url = opts.ollama_host;
    if (!opts.model_name.empty()) {
        ocfg.model = opts.model_name;
    }
    OllamaHttpBackend backend(ocfg);
    AgentLoop loop(backend, registry, mod_ctx);
    const auto res = loop.run(recipe, task, config);
    out << "\n========================================\n"
        << "Recipe execution " << (res.success ? "SUCCEEDED" : "FAILED") << "\n"
        << "Outcome: " << (res.outcome == LoopOutcome::success ? "success" : "failure") << "\n"
        << "Turns: " << res.transcript.size() << "\n";
    if (!res.completion_output.empty()) {
        out << "Completion Output: " << res.completion_output << "\n";
    }
    out << "========================================\n";
    return res.success ? 0 : 1;
}

int run_chat(const CliOptions& opts, std::istream& in, std::ostream& out, std::ostream& /*err*/,
             IInferenceBackend* custom_backend) {
    out << "Aquila Chat REPL (type /help for commands, /exit to quit)\n";
    out << "Connecting to backend (" << opts.backend_type << ")...\n\n";

    std::unique_ptr<IInferenceBackend> local_backend;
    IInferenceBackend* backend = custom_backend;
    if (backend == nullptr) {
        OllamaConfig ocfg;
        ocfg.base_url = opts.ollama_host;
        if (!opts.model_name.empty()) {
            ocfg.model = opts.model_name;
        }
        local_backend = std::make_unique<OllamaHttpBackend>(ocfg);
        backend = local_backend.get();
    }

    Message system_msg;
    system_msg.role = Role::system;
    system_msg.content = "You are Aquila, a helpful, precise AI assistant.";
    backend->append(system_msg);

    std::string line;
    while (true) {
        out << "\nYou> ";
        out.flush();
        if (!std::getline(in, line)) {
            break;
        }

        std::string trimmed = line;
        while (!trimmed.empty() && (trimmed.front() == ' ' || trimmed.front() == '\t')) {
            trimmed.erase(0, 1);
        }
        while (!trimmed.empty() && (trimmed.back() == ' ' || trimmed.back() == '\t' || trimmed.back() == '\r')) {
            trimmed.pop_back();
        }

        if (trimmed.empty()) continue;
        if (trimmed == "/exit" || trimmed == "/quit") {
            out << "Goodbye.\n";
            break;
        }
        if (trimmed == "/help") {
            out << "Commands:\n"
                << "  /help   - Show this help\n"
                << "  /reset  - Clear conversation context\n"
                << "  /exit   - Quit the REPL\n";
            continue;
        }
        if (trimmed == "/reset") {
            backend->rollback_to(0);
            backend->append(system_msg);
            out << "Conversation context reset.\n";
            continue;
        }

        Message user_msg;
        user_msg.role = Role::user;
        user_msg.content = trimmed;
        backend->append(user_msg);

        out << "Aquila> ";
        out.flush();

        GenerationParams params;
        params.temperature = 0.7;
        auto on_tok = [&out](std::string_view tok, std::string_view) -> bool {
            out << tok;
            out.flush();
            return true;
        };

        const auto gen = backend->generate(params, on_tok);
        out << "\n";
        if (!gen.ok) {
            out << "[Error: " << gen.error_code << ": " << gen.error_detail << "]\n";
        } else {
            Message assistant_msg;
            assistant_msg.role = Role::assistant;
            assistant_msg.content = gen.content;
            backend->append(assistant_msg);
        }
    }
    return 0;
}

int run_eval(const CliOptions& opts, std::ostream& out, std::ostream& err,
             IInferenceBackend* custom_backend) {
    const auto all = all_builtin_recipes();
    std::vector<RecipeCartridge> to_eval;
    if (!opts.recipe_id.empty()) {
        auto r = resolve_recipe(opts.recipe_id, opts.workspace_root);
        if (!r) {
            err << "Error: recipe '" << opts.recipe_id << "' not found for eval.\n";
            return 2;
        }
        to_eval.push_back(std::move(*r));
    } else {
        to_eval = all;
    }

    out << "Evaluating " << to_eval.size() << " recipe cartridge(s)...\n";
    out << std::left << std::setw(30) << "Recipe ID"
        << std::setw(15) << "Status"
        << std::setw(10) << "Modules"
        << std::setw(10) << "Checklist" << "\n";
    out << std::string(65, '-') << "\n";

    ModuleRegistry registry = ModuleRegistry::builtin();
    ModuleContext ctx;
    ctx.workspace_root = opts.workspace_root;

    int passed = 0;
    int failed = 0;

    for (const auto& r : to_eval) {
        out << std::left << std::setw(30) << r.recipe_id;
        try {
            registry.validate_recipe(r, ctx);
            out << std::setw(15) << "VALID";
            passed++;
        } catch (const std::exception&) {
            out << std::setw(15) << "INVALID";
            failed++;
        }
        out << std::setw(10) << r.load_modules.size()
            << std::setw(10) << r.scratchpad_checklist.size() << "\n";
    }

    out << std::string(65, '-') << "\n";
    out << "Evaluation Summary: " << passed << " valid, " << failed << " invalid.\n";

    if (custom_backend != nullptr && !to_eval.empty()) {
        out << "\nRunning mock execution on '" << to_eval.front().recipe_id << "'...\n";
        return run_recipe(opts, out, err, custom_backend);
    }

    return failed == 0 ? 0 : 1;
}

CliOptions parse_args(int argc, const char* const* argv) {
    CliOptions opts;
    if (argc <= 1) {
        opts.help = true;
        opts.command = "help";
        return opts;
    }

    int i = 1;
    std::string first = argv[1];
    if (first == "--version" || first == "-v" || first == "version") {
        opts.version = true;
        opts.command = "version";
        return opts;
    }
    if (first == "--help" || first == "-h" || first == "help") {
        opts.help = true;
        opts.command = "help";
        return opts;
    }

    if (!first.empty() && first.front() != '-') {
        opts.command = first;
        i = 2;
    } else {
        opts.command = "run";
    }

    for (; i < argc; ++i) {
        std::string_view arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            opts.help = true;
        } else if (arg == "--version" || arg == "-v") {
            opts.version = true;
        } else if (arg == "--verbose") {
            opts.verbose = true;
        } else if ((arg == "--recipe" || arg == "-r") && i + 1 < argc) {
            opts.recipe_id = argv[++i];
        } else if ((arg == "--task" || arg == "-t") && i + 1 < argc) {
            opts.task_prompt = argv[++i];
        } else if ((arg == "--workspace" || arg == "-w") && i + 1 < argc) {
            opts.workspace_root = argv[++i];
        } else if (arg == "--tier" && i + 1 < argc) {
            opts.tier_name = argv[++i];
        } else if (arg == "--backend" && i + 1 < argc) {
            opts.backend_type = argv[++i];
        } else if ((arg == "--model" || arg == "-m") && i + 1 < argc) {
            opts.model_name = argv[++i];
        } else if (arg == "--host" && i + 1 < argc) {
            opts.ollama_host = argv[++i];
        } else {
            opts.extra_args.emplace_back(arg);
        }
    }

    return opts;
}

int dispatch(const CliOptions& opts, std::istream& in, std::ostream& out, std::ostream& err,
             IInferenceBackend* custom_backend) {
    if (opts.version) {
        return print_version(out);
    }
    if (opts.help || opts.command == "help") {
        return print_help(out);
    }
    if (opts.command == "version") {
        return print_version(out);
    }
    if (opts.command == "list-recipes") {
        return list_recipes(opts.workspace_root, out);
    }
    if (opts.command == "list-modules") {
        return list_modules(out);
    }
    if (opts.command == "run") {
        return run_recipe(opts, out, err, custom_backend);
    }
    if (opts.command == "chat") {
        return run_chat(opts, in, out, err, custom_backend);
    }
    if (opts.command == "eval") {
        return run_eval(opts, out, err, custom_backend);
    }

    err << "Unknown command: '" << opts.command << "'. Run 'aquila_cli --help' for usage.\n";
    return 2;
}

}  // namespace aquila::cli
