#include "aquila/modules/execution_module.hpp"

#include "aquila/exec/process.hpp"
#include "aquila/workspace/path_firewall.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <system_error>

namespace aquila {

namespace fs = std::filesystem;

namespace {

const std::set<std::string>& default_allowlist() {
    static const std::set<std::string> kPrograms = {"python", "python3", "py",   "pytest", "git",   "cmake", "ninja",
                                                    "ctest",  "cargo",   "go",   "npm",    "npx",   "flake8", "ruff",
                                                    "mypy"};
    return kPrograms;
}

std::string seconds(double s) {
    char buf[32];
    std::snprintf(buf, sizeof buf, "%.1fs", s);
    return buf;
}

Json schema(const char* text) {
    return Json::parse(text);
}

}  // namespace

ExecutionModule::ExecutionModule(const ModuleContext& ctx) : ctx_(ctx), max_output_chars_(ctx.max_output_chars) {}

std::vector<ActionSchema> ExecutionModule::get_actions() const {
    return {
        {"run_build_and_diagnose", "Run the configured build and report the top unique compiler errors.",
         schema(R"({"type":"object","properties":{"target":{"type":"string"}},"additionalProperties":false})")},
        {"run_test_suite", "Run the configured tests, optionally filtered, and report failures and counts.",
         schema(R"({"type":"object","properties":{"filter":{"type":"string"}},"additionalProperties":false})")},
        {"exec_sandboxed_cmd", "Run one allowlisted program (argv, no shell) inside the workspace.",
         schema(R"({"type":"object","properties":{"argv":{"type":"array","minItems":1,"items":{"type":"string"}},"cwd":{"type":"string"}},"required":["argv"],"additionalProperties":false})")},
    };
}

void ExecutionModule::configure(const Json& s) {
    using namespace json_io;
    expect_object(s, "");
    reject_unknown(s, "", {"build_cmd", "test_cmd", "cwd", "allowed_programs", "timeout_s", "env", "max_output_chars"});
    const auto check_cmd = [&](const char* key) {
        const auto cmd = read_string(s[key], std::string("/") + key);
        try {
            (void)exec::split_command(cmd);
        } catch (const std::invalid_argument& e) {
            throw SchemaError(std::string("/") + key, e.what());
        }
        return cmd;
    };
    if (s.contains("build_cmd")) build_cmd_ = check_cmd("build_cmd");
    if (s.contains("test_cmd")) test_cmd_ = check_cmd("test_cmd");
    if (s.contains("cwd")) {
        const auto dir = read_string(s["cwd"], "/cwd");
        if (!ctx_.workspace_root.empty()) {
            try {
                const auto r = PathFirewall(ctx_.workspace_root).resolve(dir, Access::read);
                std::error_code ec;
                if (!fs::is_directory(r.absolute, ec)) throw SchemaError("/cwd", "not a directory: " + dir);
            } catch (const PathDenied& e) {
                throw SchemaError("/cwd", e.what());
            }
        }
        cwd_ = dir;
    }
    if (s.contains("allowed_programs")) {
        extra_allowed_.clear();
        for (const auto& p : read_string_array(s["allowed_programs"], "/allowed_programs")) {
            extra_allowed_.insert(program_name(p));
        }
    }
    if (s.contains("timeout_s")) {
        const auto& t = s["timeout_s"];
        if (!t.is_number() || t.get<double>() <= 0) throw SchemaError("/timeout_s", "must be a positive number");
        timeout_s_ = t.get<double>();
    }
    if (s.contains("env")) {
        expect_object(s["env"], "/env");
        env_.clear();
        for (const auto& [k, v] : s["env"].items()) env_[k] = read_string(v, child_path("/env", k));
    }
    if (s.contains("max_output_chars")) {
        const auto n = read_u64(s["max_output_chars"], "/max_output_chars");
        if (n < 200) throw SchemaError("/max_output_chars", "must be >= 200");
        max_output_chars_ = static_cast<std::size_t>(n);
    }
}

std::string ExecutionModule::program_name(const std::string& argv0) const {
    std::string name = path_to_utf8(path_from_utf8(argv0).filename());
    std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    for (const auto* ext : {".exe", ".cmd", ".bat", ".com"}) {
        const std::string e(ext);
        if (name.size() > e.size() && name.compare(name.size() - e.size(), e.size(), e) == 0) {
            name.resize(name.size() - e.size());
            break;
        }
    }
    return name;
}

bool ExecutionModule::allowed(const std::string& argv0) const {
    const auto name = program_name(argv0);
    if (default_allowlist().count(name) || extra_allowed_.count(name)) return true;
    for (const auto* cmd : {&build_cmd_, &test_cmd_}) {
        if (!cmd->empty() && program_name(exec::split_command(*cmd).front()) == name) return true;
    }
    return false;
}

ActionResult ExecutionModule::run(const std::string& action, const Json& args) {
    if (action == "run_build_and_diagnose") {
        if (build_cmd_.empty()) return fail("not_configured", "no build_cmd is configured for this recipe");
        auto argv = exec::split_command(build_cmd_);
        if (args.contains("target")) {
            if (program_name(argv.front()) == "cmake") argv.push_back("--target");
            argv.push_back(args["target"].get<std::string>());
        }
        return execute(action, std::move(argv), cwd_, true, "build_failed");
    }
    if (action == "run_test_suite") {
        if (test_cmd_.empty()) return fail("not_configured", "no test_cmd is configured for this recipe");
        auto argv = exec::split_command(test_cmd_);
        if (args.contains("filter")) {
            const auto prog = program_name(argv.front());
            const bool pytest = prog == "pytest" ||
                                std::find(argv.begin(), argv.end(), "pytest") != argv.end();
            if (pytest) argv.push_back("-k");
            else if (prog == "ctest") argv.push_back("-R");
            argv.push_back(args["filter"].get<std::string>());
        }
        return execute(action, std::move(argv), cwd_, true, "tests_failed");
    }
    if (action == "exec_sandboxed_cmd") {
        auto argv = args["argv"].get<std::vector<std::string>>();
        const auto cwd = args.contains("cwd") ? args["cwd"].get<std::string>() : cwd_;
        return execute(action, std::move(argv), cwd, false, "command_failed");
    }
    return fail("unknown_action", "ExecutionModule has no action '" + action + "'");
}

ActionResult ExecutionModule::execute(const std::string& action, std::vector<std::string> argv, const std::string& cwd,
                                      bool diagnose, const std::string& fail_code) {
    if (!allowed(argv.front())) {
        return fail("not_allowed", "program '" + program_name(argv.front()) +
                                       "' is not on the allowlist (no shell; allowed: python, pytest, git, cmake, ninja, "
                                       "ctest, cargo, go, npm, npx, flake8, ruff, mypy, plus the recipe's build/test programs)");
    }
    fs::path dir;
    try {
        const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
        const auto r = PathFirewall(base).resolve(cwd, Access::read);
        std::error_code ec;
        if (!fs::is_directory(r.absolute, ec)) return fail("path_invalid", "cwd is not a directory: " + cwd);
        dir = r.absolute;
    } catch (const PathDenied& e) {
        return fail(e.code(), e.what());
    } catch (const std::invalid_argument& e) {
        return fail("workspace_unavailable", e.what());
    }

    exec::RunOptions opt;
    opt.argv = argv;
    opt.cwd = dir;
    opt.env = env_;
    opt.timeout_s = timeout_s_;
    const auto res = exec::run(opt);
    if (!res.started) return fail("spawn_failed", res.error);

    RunRecord rec;
    rec.action = action;
    rec.argv = argv;
    rec.exit_code = res.exit_code;
    rec.timed_out = res.timed_out;
    rec.duration_ms = static_cast<std::uint64_t>(std::llround(res.duration_s * 1000.0));

    const std::string what = action == "run_build_and_diagnose" ? "build" : action == "run_test_suite" ? "tests" : "command";
    std::string text;
    const bool ok_exit = res.exit_code == 0 && !res.timed_out;
    text = what + (res.timed_out ? " TIMED OUT after " + seconds(timeout_s_) + " (process tree killed)"
                   : ok_exit    ? " succeeded"
                                : " FAILED") +
           " (exit " + std::to_string(res.exit_code) + ", " + seconds(res.duration_s) + ")\n";
    if (diagnose) {
        const auto d = exec::diagnose(res.output);
        rec.errors = d.errors;
        rec.warnings = d.warnings;
        for (std::size_t i = 0; i < d.blocks.size() && i < 5; ++i) {
            const auto& b = d.blocks[i];
            rec.top.push_back(b.file + (b.line ? ":" + std::to_string(b.line) : "") + " " + b.severity +
                              (b.code.empty() ? "" : " " + b.code) + ": " + b.message);
        }
        if (!ok_exit || d.errors || d.warnings || d.tests.found) {
            text += exec::render(d, 5, max_output_chars_ > text.size() ? max_output_chars_ - text.size() : 200);
        }
        if (!ok_exit && d.blocks.empty() && !d.tests.found) {
            // Nothing recognizable: show the end of the raw output instead.
            const auto tail = res.output.size() > 1500 ? res.output.substr(res.output.size() - 1500) : res.output;
            text += "no recognized diagnostics; last output:\n" + tail;
        }
    } else {
        text += res.output;
    }
    history_.push_back(std::move(rec));
    while (history_.size() > kHistory) history_.pop_front();

    ActionResult r = res.timed_out ? fail("timeout", text) : ok_exit ? ok(text) : fail(fail_code, text);
    if (r.llm_facing_output.size() > max_output_chars_) {
        const auto cut = r.llm_facing_output.size() - max_output_chars_;
        r.llm_facing_output.resize(max_output_chars_);
        r.llm_facing_output += "\n...[truncated " + std::to_string(cut) + " chars]";
        r.token_estimate = estimate_tokens(r.llm_facing_output);
    }
    return r;
}

Json ExecutionModule::export_state_snapshot() const {
    Json runs = Json::array();
    for (const auto& r : history_) {
        runs.push_back(Json{{"action", r.action}, {"argv", r.argv}, {"exit_code", r.exit_code}, {"timed_out", r.timed_out},
                            {"duration_ms", r.duration_ms}, {"errors", r.errors}, {"warnings", r.warnings}, {"top", r.top}});
    }
    Json env = Json::object();
    for (const auto& [k, v] : env_) env[k] = v;
    return Json{{"build_cmd", build_cmd_},
                {"test_cmd", test_cmd_},
                {"cwd", cwd_},
                {"allowed_programs", std::vector<std::string>(extra_allowed_.begin(), extra_allowed_.end())},
                {"timeout_s", timeout_s_},
                {"env", env},
                {"max_output_chars", max_output_chars_},
                {"history", runs}};
}

void ExecutionModule::restore_state_snapshot(const Json& s) {
    using namespace json_io;
    expect_object(s, "");
    reject_unknown(s, "", {"build_cmd", "test_cmd", "cwd", "allowed_programs", "timeout_s", "env", "max_output_chars", "history"});
    Json config = Json::object();
    for (const auto* key : {"build_cmd", "test_cmd", "cwd", "allowed_programs", "timeout_s", "env", "max_output_chars"}) {
        config[key] = require(s, "", key);
    }
    if (config["build_cmd"] == "") config.erase("build_cmd");
    if (config["test_cmd"] == "") config.erase("test_cmd");
    auto runs = read_array<RunRecord>(require(s, "", "history"), "/history", [](const Json& e, const std::string& p) {
        expect_object(e, p);
        reject_unknown(e, p, {"action", "argv", "exit_code", "timed_out", "duration_ms", "errors", "warnings", "top"});
        RunRecord r;
        r.action = read_string(require(e, p, "action"), child_path(p, "action"));
        r.argv = read_string_array(require(e, p, "argv"), child_path(p, "argv"));
        const auto& code = require(e, p, "exit_code");
        if (!code.is_number_integer()) throw SchemaError(child_path(p, "exit_code"), "expected integer");
        r.exit_code = code.get<int>();
        r.timed_out = read_bool(require(e, p, "timed_out"), child_path(p, "timed_out"));
        r.duration_ms = read_u64(require(e, p, "duration_ms"), child_path(p, "duration_ms"));
        r.errors = static_cast<std::size_t>(read_u64(require(e, p, "errors"), child_path(p, "errors")));
        r.warnings = static_cast<std::size_t>(read_u64(require(e, p, "warnings"), child_path(p, "warnings")));
        r.top = read_string_array(require(e, p, "top"), child_path(p, "top"));
        return r;
    });
    configure(config);
    history_.assign(runs.begin(), runs.end());
    while (history_.size() > kHistory) history_.pop_front();
}

}  // namespace aquila
