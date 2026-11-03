#include "fixtures.hpp"

#include "aquila/inference/ollama_wire.hpp"

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cstdio>
#include <set>

using namespace aquila;
namespace fs = std::filesystem;

namespace {

GenerationParams params_from(const Json& j) {
    GenerationParams p;
    p.temperature = j.at("temperature").get<double>();
    if (j.contains("max_tokens")) p.max_tokens = j["max_tokens"].get<std::uint32_t>();
    if (j.contains("num_ctx")) p.num_ctx = j["num_ctx"].get<std::uint32_t>();
    if (j.contains("repeat_penalty")) p.repeat_penalty = j["repeat_penalty"].get<double>();
    if (j.contains("repeat_last_n")) p.repeat_last_n = j["repeat_last_n"].get<std::uint32_t>();
    if (j.contains("think")) p.think = j["think"].get<bool>();
    if (j.contains("keep_alive")) p.keep_alive = j["keep_alive"].get<std::string>();
    if (j.contains("constraint")) {
        const auto kind = j["constraint"].at("kind").get<std::string>();
        if (kind == "json") p.constraint = OutputConstraint::json();
        if (kind == "json_schema") p.constraint = OutputConstraint::json_schema(j["constraint"].at("schema"));
    }
    return p;
}

// Python's payload with its one known bug fixed: the top-level temperature
// (ignored by Ollama) moves to the front of options.
Json fix_temperature(const Json& py) {
    Json out = Json::object();
    for (const auto& [key, value] : py.items()) {
        if (key == "temperature") continue;
        if (key == "options") {
            Json opts = Json::object();
            opts["temperature"] = py.at("temperature");
            for (const auto& [k, v] : value.items()) opts[k] = v;
            out["options"] = std::move(opts);
        } else {
            out[key] = value;
        }
    }
    return out;
}

void diff_paths(const Json& a, const Json& b, const std::string& path, std::set<std::string>& out) {
    if (a.is_object() && b.is_object()) {
        for (const auto& [k, v] : a.items()) {
            if (!b.contains(k)) out.insert(json_io::child_path(path, k));
            else diff_paths(v, b.at(k), json_io::child_path(path, k), out);
        }
        for (const auto& [k, _] : b.items()) {
            if (!a.contains(k)) out.insert(json_io::child_path(path, k));
        }
    } else if (a != b) {
        out.insert(path.empty() ? "/" : path);
    }
}

std::vector<fs::path> payload_cases() {
    std::vector<fs::path> files;
    for (const auto& e : fs::directory_iterator(test::fixture_dir() / "python" / "payloads")) {
        if (e.path().extension() == ".json") files.push_back(e.path());
    }
    std::sort(files.begin(), files.end());
    return files;
}

}  // namespace

TEST_CASE("payload parity with Python's _build_native_chat_payload (temperature fixed)") {
    std::size_t checked = 0;
    for (const auto& file : payload_cases()) {
        const auto doc = Json::parse(test::read_bytes(file));
        const auto name = doc.at("case").get<std::string>();
        INFO(name);

        std::vector<Message> messages;
        for (std::size_t i = 0; i < doc.at("messages").size(); ++i) {
            Message m;
            from_json(doc["messages"][i], m, json_io::index_path("/messages", i));
            messages.push_back(std::move(m));
        }
        const auto payload = ollama::build_chat_payload(doc.at("model").get<std::string>(), messages,
                                                        params_from(doc.at("params")),
                                                        doc.at("stream").get<bool>());
        const auto& py = doc.at("python_payload");

        CHECK(json_io::canonical_dump(payload) == json_io::canonical_dump(fix_temperature(py)));

        std::set<std::string> diffs;
        diff_paths(py, payload, "", diffs);
        CHECK(diffs == std::set<std::string>{"/temperature", "/options/temperature"});
        ++checked;
    }
    std::printf("payload parity: %zu Python cases; only /temperature -> /options/temperature differs\n",
                checked);
    CHECK(checked == 7);
}

TEST_CASE("negative control: a real payload difference is reported by the diff") {
    const auto doc = Json::parse(
        test::read_bytes(test::fixture_dir() / "python" / "payloads" / "act_code_agent.json"));
    Json altered = fix_temperature(doc.at("python_payload"));
    altered["options"]["num_predict"] = 999;
    std::set<std::string> diffs;
    diff_paths(doc.at("python_payload"), altered, "", diffs);
    CHECK(diffs == std::set<std::string>{"/temperature", "/options/temperature", "/options/num_predict"});
}

TEST_CASE("payload omits unset optionals and maps constraints") {
    GenerationParams p;
    p.temperature = 0.0;
    auto j = ollama::build_chat_payload("m", {Message{Role::user, "hi", {}}}, p, false);
    CHECK(json_io::canonical_dump(j) ==
          "{\n  \"model\": \"m\",\n  \"messages\": [\n    {\n      \"role\": \"user\",\n      \"content\": \"hi\"\n"
          "    }\n  ],\n  \"stream\": false,\n  \"options\": {\n    \"temperature\": 0.0\n  }\n}\n");

    p.seed = 42;
    p.constraint = OutputConstraint::json();
    j = ollama::build_chat_payload("m", {}, p, true);
    CHECK(j["options"]["seed"] == 42);
    CHECK(j["format"] == "json");
    CHECK(j["stream"] == true);
    CHECK_FALSE(j.contains("think"));
    CHECK_FALSE(j.contains("keep_alive"));
}

TEST_CASE("non-streaming response parsing") {
    const auto r = ollama::parse_chat_response(
        R"({"model":"m","message":{"role":"assistant","content":"pong","thinking":"hm"},"done":true,"done_reason":"stop","prompt_eval_count":32,"eval_count":3})");
    CHECK(r.ok);
    CHECK(r.error_code.empty());
    CHECK(r.content == "pong");
    CHECK(r.thinking == "hm");
    CHECK(r.done_reason == "stop");
    CHECK(r.prompt_tokens == 32);
    CHECK(r.completion_tokens == 3);

    CHECK(ollama::parse_chat_response("not json").error_code == "bad_response");
    CHECK(ollama::parse_chat_response("[1]").error_code == "bad_response");
    CHECK(ollama::parse_chat_response(R"({"done":true})").error_code == "bad_response");
    const auto err = ollama::parse_chat_response(R"({"error":"model not found"})");
    CHECK(err.error_code == "server_error");
    CHECK(err.error_detail == "model not found");
}

TEST_CASE("stream line parsing") {
    CHECK_FALSE(ollama::parse_stream_line("").has_value());
    CHECK_FALSE(ollama::parse_stream_line("\r").has_value());
    const auto c = ollama::parse_stream_line(R"({"message":{"content":"po","thinking":""},"done":false})" "\r");
    REQUIRE(c.has_value());
    CHECK(c->content == "po");
    CHECK_FALSE(c->done);
    const auto d = ollama::parse_stream_line(
        R"({"message":{"content":""},"done":true,"done_reason":"stop","prompt_eval_count":5,"eval_count":2})");
    REQUIRE(d.has_value());
    CHECK(d->done);
    CHECK(d->prompt_tokens == 5);
    CHECK(ollama::parse_stream_line(R"({"error":"boom"})")->error == "boom");
    CHECK_THROWS_AS(ollama::parse_stream_line("{oops"), SchemaError);
}

TEST_CASE("backend error codes follow the ActionResult convention") {
    for (const auto* code : {"unreachable", "timeout", "stream_stalled", "stream_truncated", "http_error",
                             "server_error", "bad_response", "cancelled", "unsupported_url",
                             "invalid_request", "transport_error"}) {
        INFO(code);
        CHECK(is_valid_error_code(code));
    }
}
