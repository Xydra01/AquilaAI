// apps/aquila_cli/cli_app.hpp
#pragma once

#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/types/recipe.hpp"

#include <filesystem>
#include <iosfwd>
#include <string>
#include <vector>

namespace aquila::cli {

struct CliOptions {
    std::string command;
    std::string recipe_id;
    std::string task_prompt;
    std::filesystem::path workspace_root = ".";
    std::string tier_name = "cpu";
    std::string backend_type = "ollama";
    std::string model_name;
    std::string ollama_host = "http://127.0.0.1:11434";
    bool verbose = false;
    bool help = false;
    bool version = false;
    bool live = false;
    bool dissect = false;
    std::string report_path;
    std::vector<std::string> extra_args;
};

int print_version(std::ostream& out);
int print_help(std::ostream& out);
int list_recipes(const std::filesystem::path& workspace_root, std::ostream& out);
int list_modules(std::ostream& out);

int run_recipe(const CliOptions& opts, std::ostream& out, std::ostream& err,
               IInferenceBackend* custom_backend = nullptr);
int run_chat(const CliOptions& opts, std::istream& in, std::ostream& out, std::ostream& err,
             IInferenceBackend* custom_backend = nullptr);
int run_eval(const CliOptions& opts, std::ostream& out, std::ostream& err,
             IInferenceBackend* custom_backend = nullptr);

CliOptions parse_args(int argc, const char* const* argv);
int dispatch(const CliOptions& opts, std::istream& in, std::ostream& out, std::ostream& err,
             IInferenceBackend* custom_backend = nullptr);

}  // namespace aquila::cli
