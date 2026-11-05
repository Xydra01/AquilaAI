// Context-strategy bake-off harness (M5 task 11.3/11.4, Req 9 / D14).
//
// Runs each of the three ContextStrategy implementations over the shared task suite
// (bakeoff_tasks.hpp) on a real Qwen 3.5 model and decides D14 by a PRE-COMMITTED
// rule applied to the results (Req 9.5):
//   1. any CRASH disqualifies the strategy (a typed failure does NOT),
//   2. highest task-completion rate wins,
//   3. ties broken by fewest tokens decoded, then lowest wall-clock latency.
// The rule is COMPUTED here (not eyeballed) and the per-strategy table + the winner
// + the raw numbers are printed and written to a JSON artifact (Req 9.3/9.6).
//
// Deciding lane: Qwen 3.5 4B Q4_K_M on CPU (AQUILA_BAKEOFF_GGUF_4B, the default).
// Confirmation lane (non-gating): the 9B on GPU via AQUILA_LIVE_GGUF + n_gpu_layers.
// Opt-in (-DAQUILA_LIVE_TESTS=ON), excluded from CI like the other live tests.

#include <catch2/catch_test_macros.hpp>

#if AQUILA_HAS_LLAMACPP

#include "aquila/context/context_strategy.hpp"
#include "aquila/context/eocc_strategy.hpp"
#include "aquila/context/kv_rollback_strategy.hpp"
#include "aquila/context/sac_strategy.hpp"
#include "aquila/inference/backend.hpp"
#include "aquila/inference/llama_backend.hpp"
#include "aquila/json.hpp"
#include "aquila/types/action.hpp"
#include "bakeoff_tasks.hpp"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

using namespace aquila;

namespace {

// Deciding model: the 4B, CPU. AQUILA_BAKEOFF_GGUF_4B is injected by cmake; an env
// override (AQUILA_BAKEOFF_GGUF) wins so the 9B/GPU confirmation lane can reuse this.
std::string bakeoff_model() {
    if (const char* e = std::getenv("AQUILA_BAKEOFF_GGUF"); e && *e) return e;
#ifdef AQUILA_BAKEOFF_GGUF_4B
    return AQUILA_BAKEOFF_GGUF_4B;
#else
    return "";
#endif
}

// gpu layers: 0 (CPU, the 4B deciding lane) unless AQUILA_BAKEOFF_GPU is set (the
// 9B confirmation lane offloads all layers).
std::int32_t bakeoff_gpu_layers() {
    if (const char* e = std::getenv("AQUILA_BAKEOFF_GPU"); e && *e) return 999;
    return 0;
}

bool model_available() {
    const std::string m = bakeoff_model();
    return !m.empty() && std::filesystem::exists(std::filesystem::path(m));
}

Json action_call_schema() {
    Json schema = Json::object();
    schema["type"] = "object";
    Json props = Json::object();
    for (const char* k : {"thought", "module", "action"}) {
        Json s = Json::object();
        s["type"] = "string";
        props[k] = std::move(s);
    }
    {
        // args is a BOUNDED object: values limited to string|integer|boolean
        // scalars (no nested objects/arrays) so the GBNF forces the object to close
        // instead of recursing forever (the no-EOS cause). The oracles only read
        // flat string/number/bool args.
        Json args = Json::object();
        args["type"] = "object";
        Json addl = Json::object();
        addl["type"] = Json::array({"string", "integer", "boolean"});
        args["additionalProperties"] = std::move(addl);
        props["args"] = std::move(args);
    }
    schema["properties"] = std::move(props);
    schema["required"] = Json::array({"thought", "module", "action", "args"});
    schema["additionalProperties"] = false;
    return schema;
}

GenerationParams schema_params() {
    GenerationParams p;
    p.temperature = 0.3;  // low-temp agent sampling; pure greedy collapses on 4B
    p.repeat_penalty = 1.15;  // proven Python AQUILA_REPEAT_PENALTY
    p.repeat_last_n = std::uint32_t{64};
    p.seed = std::int64_t{1234};  // fixed seed: reproducible across strategies
    p.max_tokens = std::uint32_t{2048};  // match Python AQUILA_ACT_NUM_PREDICT regime; 256 truncated before the action closed
    if (const char* ng = std::getenv("AQUILA_BAKEOFF_NOGRAMMAR"); !(ng && *ng)) {
        p.constraint = OutputConstraint::json_schema(action_call_schema());
    }
    p.timeout_s = 180.0;
    return p;
}

std::unique_ptr<ContextStrategy> make_strategy(const std::string& which, std::uint64_t eocc_threshold) {
    if (which == "kv_rollback") return std::make_unique<KvRollbackStrategy>(4);
    if (which == "eocc")        return std::make_unique<EoCCStrategy>(eocc_threshold, 4);
    return std::make_unique<SacStrategy>();
}

// Per-strategy aggregate over the whole suite.
struct Score {
    std::string name;
    int tasks = 0;
    int completed = 0;         // oracle-pass
    bool crashed = false;      // an untyped crash on any task (disqualifies)
    std::uint64_t tokens = 0;  // total tokens decoded
    double seconds = 0.0;      // total wall-clock
    std::uint64_t typed_failures = 0;
};

// The pre-committed decision rule (Req 9.5). Returns the winning index into scores,
// or -1 if every strategy was disqualified.
int decide_winner(const std::vector<Score>& scores) {
    int best = -1;
    for (int i = 0; i < static_cast<int>(scores.size()); ++i) {
        const Score& s = scores[i];
        if (s.crashed) continue;  // crash disqualifies
        if (best < 0) { best = i; continue; }
        const Score& b = scores[best];
        // 1) higher completion rate wins
        const double s_rate = s.tasks ? double(s.completed) / s.tasks : 0.0;
        const double b_rate = b.tasks ? double(b.completed) / b.tasks : 0.0;
        if (s_rate > b_rate) { best = i; continue; }
        if (s_rate < b_rate) continue;
        // 2) fewer tokens breaks a completion tie
        if (s.tokens < b.tokens) { best = i; continue; }
        if (s.tokens > b.tokens) continue;
        // 3) lower latency breaks a token tie
        if (s.seconds < b.seconds) { best = i; }
    }
    return best;
}

}  // namespace

TEST_CASE("live: context-strategy bake-off decides D14", "[context_bakeoff][live]") {
    if (!model_available()) {
        SKIP("bake-off model not present (AQUILA_BAKEOFF_GGUF_4B / AQUILA_BAKEOFF_GGUF); "
             "skipping the D14 bake-off");
    }

    LlamaConfig cfg;
    cfg.model_path = bakeoff_model();
    cfg.n_gpu_layers = bakeoff_gpu_layers();
    cfg.profile = cfg.n_gpu_layers > 0 ? ComputeProfile::gpu_high_vram
                                       : ComputeProfile::cpu_moe_fast;
    cfg.n_ctx = 16384;  // the EoCC threshold regime (16K); fits 4B CPU
    if (const char* nc = std::getenv("AQUILA_BAKEOFF_NCTX"); nc && *nc) {
        cfg.n_ctx = static_cast<std::uint32_t>(std::atoi(nc));  // 9B GPU is VRAM-bound
    }

    std::vector<std::string> strategy_names = {"kv_rollback", "eocc", "sac"};
    if (const char* only = std::getenv("AQUILA_BAKEOFF_ONLY"); only && *only) strategy_names = {std::string(only)};
    std::size_t n_detour = 8;
    if (const char* nd = std::getenv("AQUILA_BAKEOFF_DETOUR"); nd && *nd) n_detour = static_cast<std::size_t>(std::atoi(nd));
    std::vector<bakeoff::Task> tasks = bakeoff::suite(n_detour);
    if (const char* lim = std::getenv("AQUILA_BAKEOFF_LIMIT"); lim && *lim) { std::size_t k = static_cast<std::size_t>(std::atoi(lim)); if (k < tasks.size()) tasks.resize(k); }

    Json artifact = Json::object();
    artifact["model"] = bakeoff_model();
    artifact["gpu_layers"] = cfg.n_gpu_layers;
    artifact["n_ctx"] = cfg.n_ctx;
    artifact["strategies"] = Json::array();

    std::vector<Score> scores;

    for (const std::string& sname : strategy_names) {
        // A fresh backend per strategy so KV state never leaks across strategies.
        LlamaCppBackend backend(cfg);
        Score score;
        score.name = sname;

        Json s_json = Json::object();
        s_json["name"] = sname;
        s_json["tasks"] = Json::array();

        for (const bakeoff::Task& task : tasks) {
            const std::uint64_t eocc_threshold = (cfg.n_ctx * 3) / 4;  // compact before overflow
            std::unique_ptr<ContextStrategy> strat = make_strategy(sname, eocc_threshold);
            Json t_json = Json::object();
            t_json["name"] = task.name;
            ++score.tasks;

            const auto t0 = std::chrono::steady_clock::now();
            std::string last_content; std::string last_done_reason;
            bool completed = false;
            bool crashed = false;
            std::string outcome;
            try {
                strat->set_prefix(backend, task.prefix);
                for (const Message& turn : task.turns) {
                    strat->add_turn(backend, turn);
                }
                strat->add_turn(backend, Message{Role::user, task.final_prompt});
                const GenerationResult r = strat->next_action(backend, schema_params(), nullptr);
                last_content = r.content; last_done_reason = r.done_reason;
                if (r.ok && r.done_reason == "stop") {
                    try {
                        const ActionCall call = parse<ActionCall>(r.content);
                        completed = task.oracle(call);
                        outcome = completed ? "completed" : "wrong_answer";
                    } catch (...) {
                        outcome = "unparseable";  // GBNF should prevent this
                    }
                } else {
                    outcome = r.ok ? "truncated" : ("typed_failure:" + r.error_code);
                    if (const char* d = std::getenv("AQUILA_BAKEOFF_DEBUG"); d && *d) {
                        std::printf("    DEBUG[%s] content[%zu]: %.300s\n",
                                    r.error_code.c_str(), r.content.size(), r.content.c_str());
                    }
                }
            } catch (const std::exception& e) {
                // A typed LlamaError is a std::exception too; the strategies CATCH the
                // M-RoPE typed failure internally and recover, so anything that
                // escapes to HERE is an unexpected hard failure -> treat as a crash
                // for the disqualification rule, but record the what() honestly.
                crashed = true;
                outcome = std::string("crash:") + e.what();
            }
            const auto t1 = std::chrono::steady_clock::now();
            const double secs = std::chrono::duration<double>(t1 - t0).count();

            const StrategyStats st = strat->stats();
            score.tokens += st.tokens_decoded;
            score.seconds += secs;
            score.typed_failures += st.typed_failures;
            if (completed) ++score.completed;
            if (crashed) score.crashed = true;

            t_json["outcome"] = outcome;
            t_json["content_sample"] = last_content.substr(0, 300);
            t_json["done_reason"] = last_done_reason;
            t_json["completed"] = completed;
            t_json["tokens_decoded"] = st.tokens_decoded;
            t_json["resets"] = st.resets;
            t_json["compactions"] = st.compactions;
            t_json["typed_failures"] = st.typed_failures;
            t_json["seconds"] = secs;
            s_json["tasks"].push_back(std::move(t_json));

            std::printf("  [%-11s] %-28s -> %-14s (%.1fs, %llu tok, %llu resets)\n",
                        sname.c_str(), task.name.c_str(), outcome.c_str(), secs,
                        static_cast<unsigned long long>(st.tokens_decoded),
                        static_cast<unsigned long long>(st.resets));
            std::fflush(stdout);
        }

        s_json["completed"] = score.completed;
        s_json["tasks_total"] = score.tasks;
        s_json["crashed"] = score.crashed;
        s_json["tokens_total"] = score.tokens;
        s_json["seconds_total"] = score.seconds;
        artifact["strategies"].push_back(std::move(s_json));
        scores.push_back(std::move(score));
    }

    // --- apply the pre-committed decision rule -----------------------------
    const int winner = decide_winner(scores);

    std::printf("\n=== BAKE-OFF RESULTS (model=%s, gpu_layers=%d) ===\n",
                bakeoff_model().c_str(), cfg.n_gpu_layers);
    std::printf("%-12s %8s %7s %10s %9s %8s\n",
                "strategy", "pass", "crash", "tokens", "seconds", "typedfail");
    for (const Score& s : scores) {
        std::printf("%-12s %6d/%-2d %7s %10llu %9.1f %8llu\n",
                    s.name.c_str(), s.completed, s.tasks, s.crashed ? "YES" : "no",
                    static_cast<unsigned long long>(s.tokens), s.seconds,
                    static_cast<unsigned long long>(s.typed_failures));
    }
    if (winner >= 0) {
        std::printf("WINNER (D14): %s  -- seeds M6 ContextCondenser\n",
                    scores[winner].name.c_str());
        artifact["winner"] = scores[winner].name;
    } else {
        std::printf("WINNER (D14): NONE -- every strategy disqualified (crashed)\n");
        artifact["winner"] = nullptr;
    }

    // --- write the results artifact (Req 9.3/9.6) --------------------------
    std::error_code ec;
    std::filesystem::create_directories("bakeoff-results", ec);
    const std::string out = "bakeoff-results/d14_bakeoff.json";
    if (std::ofstream f{out}; f) {
        f << artifact.dump(2) << '\n';
        std::printf("results written: %s\n", out.c_str());
    }

    // The bake-off is non-vacuous: at least one strategy must have survived to decide
    // D14. (A strategy failing the oracle is a legitimate result, not a test failure;
    // the suite's job is to MEASURE, so we only assert that a decision was reachable.)
    CHECK(winner >= 0);
}

#else  // !AQUILA_HAS_LLAMACPP

TEST_CASE("live context bake-off is stubbed (AQUILA_HAS_LLAMACPP=0)",
          "[context_bakeoff][live][stub]") {
    SUCCEED("llama.cpp backend compiled out on this build; bake-off skipped");
}

#endif  // AQUILA_HAS_LLAMACPP
