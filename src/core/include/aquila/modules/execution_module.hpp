#pragma once

#include "aquila/exec/diagnostics.hpp"
#include "aquila/modules/module.hpp"

#include <deque>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace aquila {

// Build, test and sandboxed commands (R11). Actions:
//   run_build_and_diagnose, run_test_suite, exec_sandboxed_cmd
// Commands run without a shell (argv only). The program must be on the
// allowlist, the working directory stays inside the workspace, secrets are
// removed from the environment, and a timeout ends the whole process tree.
// Build/test output is reduced to deduplicated diagnostic blocks.
class ExecutionModule final : public ModuleBase {
public:
    explicit ExecutionModule(const ModuleContext& ctx);

    [[nodiscard]] std::string module_id() const override { return "ExecutionModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    // initial_state: {build_cmd?, test_cmd?, cwd?, allowed_programs?, timeout_s?, env?, max_output_chars?}
    // allowed_programs adds to the default allowlist.
    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    static constexpr std::size_t kHistory = 8;

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    struct RunRecord {
        std::string action;
        std::vector<std::string> argv;
        int exit_code = 0;
        bool timed_out = false;
        std::uint64_t duration_ms = 0;
        std::size_t errors = 0;
        std::size_t warnings = 0;
        std::vector<std::string> top;  // first diagnostic lines
    };

    ActionResult execute(const std::string& action, std::vector<std::string> argv, const std::string& cwd,
                         bool diagnose, const std::string& fail_code);
    ActionResult ensure_venv_action(const std::string& venv_name);
    ActionResult pip_install_action(const std::vector<std::string>& packages, bool upgrade);
    ActionResult run_python_action(const std::string& script, const std::string& code,
                                   const std::vector<std::string>& script_args, const std::string& cwd);
    ActionResult pip_list_action();
    ActionResult verify_implementation_action(const Json& args);
    [[nodiscard]] std::string program_name(const std::string& argv0) const;
    [[nodiscard]] bool allowed(const std::string& argv0) const;

    ModuleContext ctx_;
    std::string build_cmd_;
    std::string test_cmd_;
    std::string cwd_ = ".";
    std::set<std::string> extra_allowed_;
    double timeout_s_ = 300.0;
    std::map<std::string, std::string> env_;
    std::size_t max_output_chars_;
    std::deque<RunRecord> history_;
};

}  // namespace aquila
