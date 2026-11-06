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
                                                    "mypy",   "pip",     "pip3", "uv"};
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
        {"ensure_venv", "Ensure an isolated Python virtual environment (.venv) exists in the workspace. Creates it if missing.",
         schema(R"({"type":"object","properties":{"venv_dir":{"type":"string"}},"additionalProperties":false})")},
        {"pip_install", "Install one or more Python packages into the workspace virtual environment.",
         schema(R"({"type":"object","properties":{"packages":{"type":"array","items":{"type":"string"},"minItems":1},"upgrade":{"type":"boolean"}},"required":["packages"],"additionalProperties":false})")},
        {"run_python", "Execute a Python script or Python code snippet inside the workspace virtual environment.",
         schema(R"({"type":"object","properties":{"script":{"type":"string"},"code":{"type":"string"},"args":{"type":"array","items":{"type":"string"}},"cwd":{"type":"string"}},"additionalProperties":false})")},
        {"pip_list", "List installed Python packages inside the workspace virtual environment.",
         schema(R"({"type":"object","additionalProperties":false})")},
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
    if (action == "ensure_venv") {
        const std::string venv_dir = args.contains("venv_dir") ? args["venv_dir"].get<std::string>() : ".venv";
        return ensure_venv_action(venv_dir);
    }
    if (action == "pip_install") {
        if (!args.contains("packages") || !args["packages"].is_array() || args["packages"].empty()) {
            return fail("invalid_args", "pip_install requires a non-empty 'packages' array");
        }
        const auto pkgs = args["packages"].get<std::vector<std::string>>();
        const bool upgrade = args.contains("upgrade") ? args["upgrade"].get<bool>() : false;
        return pip_install_action(pkgs, upgrade);
    }
    if (action == "run_python") {
        const std::string script = args.contains("script") ? args["script"].get<std::string>() : "";
        const std::string code = args.contains("code") ? args["code"].get<std::string>() : "";
        std::vector<std::string> sargs;
        if (args.contains("args") && args["args"].is_array()) {
            sargs = args["args"].get<std::vector<std::string>>();
        }
        const std::string cwd = args.contains("cwd") ? args["cwd"].get<std::string>() : cwd_;
        return run_python_action(script, code, sargs, cwd);
    }
    if (action == "pip_list") {
        return pip_list_action();
    }
    return fail("unknown_action", "ExecutionModule has no action '" + action + "'");
}

ActionResult ExecutionModule::ensure_venv_action(const std::string& venv_name) {
    const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
    const std::string target_name = venv_name.empty() ? ".venv" : venv_name;
    const auto venv = base / target_name;

    std::error_code ec;
#ifdef _WIN32
    const bool exists = fs::exists(venv / "Scripts" / "python.exe", ec);
#else
    const bool exists = fs::exists(venv / "bin" / "python", ec);
#endif

    if (exists) {
        ActionResult res;
        res.success = true;
        res.llm_facing_output = "virtualenv already active at " + path_to_utf8(venv);
        return res;
    }

    std::vector<std::string> argv = {"python", "-m", "venv", target_name};
    exec::RunOptions opt;
    opt.argv = argv;
    opt.cwd = base;
    opt.timeout_s = 60.0;
    opt.env = env_;
    auto run_res = exec::run(opt);
    if (!run_res.started || run_res.exit_code != 0) {
        opt.argv = {"python3", "-m", "venv", target_name};
        run_res = exec::run(opt);
        if (!run_res.started || run_res.exit_code != 0) {
            opt.argv = {"py", "-m", "venv", target_name};
            run_res = exec::run(opt);
        }
    }

    if (!run_res.started || run_res.exit_code != 0) {
        return fail("venv_creation_failed", "failed to create virtualenv at " + path_to_utf8(venv) +
                                                ": " + (run_res.output.empty() ? run_res.error : run_res.output));
    }

    ActionResult res;
    res.success = true;
    res.llm_facing_output = "successfully initialized isolated virtualenv at " + path_to_utf8(venv);
    return res;
}

ActionResult ExecutionModule::pip_install_action(const std::vector<std::string>& packages, bool upgrade) {
    ensure_venv_action(".venv");

    const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
    const auto venv = base / ".venv";
#ifdef _WIN32
    std::string py_exe = path_to_utf8(venv / "Scripts" / "python.exe");
    std::error_code ec;
    if (!fs::exists(py_exe, ec)) py_exe = "python";
#else
    std::string py_exe = path_to_utf8(venv / "bin" / "python");
    std::error_code ec;
    if (!fs::exists(py_exe, ec)) py_exe = "python3";
#endif

    std::vector<std::string> argv = {py_exe, "-m", "pip", "install"};
    if (upgrade) {
        argv.push_back("--upgrade");
    }
    for (const auto& pkg : packages) {
        argv.push_back(pkg);
    }

    exec::RunOptions opt;
    opt.argv = argv;
    opt.cwd = base;
    opt.timeout_s = 180.0;
    opt.env = env_;
    opt.env["VIRTUAL_ENV"] = path_to_utf8(venv);

    const auto run_res = exec::run(opt);
    if (!run_res.started || run_res.exit_code != 0) {
        return fail("pip_install_failed", "pip install failed with exit code " + std::to_string(run_res.exit_code) +
                                              ":\n" + run_res.output);
    }

    ActionResult res;
    res.success = true;
    res.llm_facing_output = "packages installed successfully into .venv:\n" + run_res.output;
    return res;
}

ActionResult ExecutionModule::run_python_action(const std::string& script, const std::string& code,
                                               const std::vector<std::string>& script_args, const std::string& cwd) {
    ensure_venv_action(".venv");

    const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
    const auto venv = base / ".venv";
#ifdef _WIN32
    std::string py_exe = path_to_utf8(venv / "Scripts" / "python.exe");
    std::error_code ec;
    if (!fs::exists(py_exe, ec)) py_exe = "python";
#else
    std::string py_exe = path_to_utf8(venv / "bin" / "python");
    std::error_code ec;
    if (!fs::exists(py_exe, ec)) py_exe = "python3";
#endif

    std::vector<std::string> argv = {py_exe};
    if (!code.empty()) {
        argv.push_back("-c");
        argv.push_back(code);
    } else if (!script.empty()) {
        argv.push_back(script);
        for (const auto& a : script_args) {
            argv.push_back(a);
        }
    } else {
        return fail("invalid_args", "run_python requires either 'script' or 'code'");
    }

    const auto target_cwd = cwd.empty() ? cwd_ : cwd;
    return execute("run_python", argv, target_cwd, false, "python_execution_failed");
}

ActionResult ExecutionModule::pip_list_action() {
    ensure_venv_action(".venv");

    const auto base = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
    const auto venv = base / ".venv";
#ifdef _WIN32
    std::string py_exe = path_to_utf8(venv / "Scripts" / "python.exe");
    std::error_code ec;
    if (!fs::exists(py_exe, ec)) py_exe = "python";
#else
    std::string py_exe = path_to_utf8(venv / "bin" / "python");
    std::error_code ec;
    if (!fs::exists(py_exe, ec)) py_exe = "python3";
#endif

    std::vector<std::string> argv = {py_exe, "-m", "pip", "list"};
    return execute("pip_list", argv, cwd_, false, "pip_list_failed");
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

    // Inject .venv if active in workspace
    const auto base_dir = ctx_.workspace_root.empty() ? fs::current_path() : ctx_.workspace_root;
    const auto venv_dir = base_dir / ".venv";
    std::error_code ec_v;
    if (fs::is_directory(venv_dir, ec_v)) {
        opt.env["VIRTUAL_ENV"] = path_to_utf8(venv_dir);
#ifdef _WIN32
        const auto scripts_dir = venv_dir / "Scripts";
        if (fs::is_directory(scripts_dir, ec_v)) {
            const auto it_path = opt.env.find("PATH");
            const std::string existing_path = it_path != opt.env.end() ? it_path->second : "";
            opt.env["PATH"] = path_to_utf8(scripts_dir) + (existing_path.empty() ? "" : ";" + existing_path);
        }
#else
        const auto bin_dir = venv_dir / "bin";
        if (fs::is_directory(bin_dir, ec_v)) {
            const auto it_path = opt.env.find("PATH");
            const std::string existing_path = it_path != opt.env.end() ? it_path->second : "";
            opt.env["PATH"] = path_to_utf8(bin_dir) + (existing_path.empty() ? "" : ":" + existing_path);
        }
#endif
    }
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
