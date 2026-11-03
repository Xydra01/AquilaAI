// Live tests against a real Ollama server (opt-in: -DAQUILA_LIVE_TESTS=ON).
// Model: AQUILA_LIVE_MODEL (default aquila:latest, Python's configured model).
#include "aquila/inference/ollama_backend.hpp"
#include "aquila/inference/ollama_wire.hpp"

#include <catch2/catch_test_macros.hpp>
#include <httplib.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <regex>

using namespace aquila;

namespace {

std::string live_model() {
    const char* m = std::getenv("AQUILA_LIVE_MODEL");
    return (m && *m) ? m : "aquila:latest";
}

OllamaHttpBackend live_backend() {
    auto c = OllamaConfig::from_env();
    c.model = live_model();
    return OllamaHttpBackend(c);
}

void require_stock_server(const OllamaHttpBackend& b) {
    const auto version = b.probe(5.0);
    REQUIRE(version.has_value());
    std::printf("server %s version %s, model %s\n", b.config().base_url.c_str(), version->c_str(),
                b.config().model.c_str());
    // The turboquant build reports "pr15505-turboquant"; only plain releases are accepted.
    REQUIRE(std::regex_match(*version, std::regex(R"(\d+\.\d+\.\d+)")));
}

std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

GenerationParams base_params() {
    GenerationParams p;
    p.temperature = 0.0;
    p.think = false;
    p.max_tokens = 32;
    p.timeout_s = 300.0;
    return p;
}

// Raw /api/chat call so the temperature placement can be controlled exactly.
std::string raw_chat(const OllamaConfig& c, Json payload) {
    httplib::Client cli("127.0.0.1", 11434);
    if (c.base_url != "http://127.0.0.1:11434") {
        FAIL("temperature check expects the default local server, got " << c.base_url);
    }
    cli.set_read_timeout(std::chrono::seconds(300));
    const auto res = cli.Post("/api/chat", payload.dump(), "application/json");
    REQUIRE(res);
    REQUIRE(res->status == 200);
    return Json::parse(res->body)["message"]["content"].get<std::string>();
}

}  // namespace

TEST_CASE("live: plain pong") {
    auto b = live_backend();
    require_stock_server(b);
    b.append({Role::user, "Reply with exactly the word pong and nothing else.", {}});
    const auto r = b.generate(base_params(), {});
    INFO(r.error_code << " " << r.error_detail);
    REQUIRE(r.ok);
    std::printf("plain: content=\"%s\" prompt_tokens=%llu completion_tokens=%llu\n", r.content.c_str(),
                static_cast<unsigned long long>(r.prompt_tokens), static_cast<unsigned long long>(r.completion_tokens));
    CHECK(lower(r.content).find("pong") != std::string::npos);
}

TEST_CASE("live: schema-constrained pong") {
    auto b = live_backend();
    require_stock_server(b);
    b.append({Role::user, "Answer the ping. ping", {}});
    auto p = base_params();
    p.constraint = OutputConstraint::json_schema(Json::parse(
        R"({"type":"object","properties":{"reply":{"type":"string","enum":["pong"]}},"required":["reply"]})"));
    const auto r = b.generate(p, {});
    INFO(r.error_code << " " << r.error_detail);
    REQUIRE(r.ok);
    std::printf("structured: content=%s\n", r.content.c_str());
    CHECK(Json::parse(r.content).at("reply") == "pong");
}

TEST_CASE("live: streaming tokens concatenate to the final content") {
    auto b = live_backend();
    require_stock_server(b);
    b.append({Role::user, "Count from one to five in words, separated by spaces.", {}});
    std::string streamed;
    int chunks = 0;
    const auto r = b.generate(base_params(), [&](std::string_view c, std::string_view) {
        streamed += c;
        ++chunks;
        return true;
    });
    INFO(r.error_code << " " << r.error_detail);
    REQUIRE(r.ok);
    std::printf("stream: %d chunks, content=\"%s\", prompt_tokens=%llu\n", chunks, r.content.c_str(),
                static_cast<unsigned long long>(r.prompt_tokens));
    CHECK(chunks > 1);
    CHECK(streamed == r.content);
    CHECK(!r.content.empty());
    CHECK(r.prompt_tokens > 0);
}

TEST_CASE("live: top-level temperature is ignored, options.temperature is honored") {
    auto b = live_backend();
    require_stock_server(b);
    const std::vector<Message> msgs{{Role::user, "Write one vivid sentence about a lighthouse in a storm.", {}}};
    auto p = base_params();
    p.max_tokens = 40;
    p.seed = 42;

    // Python's shape: temperature at the top level, none in options.
    const auto python_style = [&](double t) {
        auto payload = ollama::build_chat_payload(b.config().model, msgs, p, false);
        payload["options"].erase("temperature");
        payload["temperature"] = t;
        return raw_chat(b.config(), payload);
    };
    const auto in_options = [&](double t) {
        auto q = p;
        q.temperature = t;
        return raw_chat(b.config(), ollama::build_chat_payload(b.config().model, msgs, q, false));
    };

    const auto base_a = in_options(2.0);
    const auto base_b = in_options(2.0);
    std::printf("baseline options.temperature=2.0 twice (seed 42):\n  [%s]\n  [%s]\n", base_a.c_str(), base_b.c_str());
    if (base_a != base_b) {
        SKIP("same seed + temperature gave different outputs: sampling is not deterministic here");
    }

    const auto top0 = python_style(0.0);
    const auto top2 = python_style(2.0);
    const auto opt0 = in_options(0.0);
    const auto opt2 = in_options(2.0);
    const auto opt_modelfile = in_options(0.2);
    std::printf("top-level 0.0: [%s]\ntop-level 2.0: [%s]\noptions 0.0:   [%s]\noptions 2.0:   [%s]\noptions 0.2:   [%s]\n",
                top0.c_str(), top2.c_str(), opt0.c_str(), opt2.c_str(), opt_modelfile.c_str());

    CHECK(top0 == top2);            // ignored: both use the model default
    CHECK(opt0 != opt2);            // honored
    CHECK(top0 == opt_modelfile);   // the default is the Modelfile's 0.2 (aquila:latest)
}
