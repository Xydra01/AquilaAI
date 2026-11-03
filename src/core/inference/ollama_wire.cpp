#include "aquila/inference/ollama_wire.hpp"

namespace aquila::ollama {

namespace {

std::string string_or_empty(const Json& obj, const char* key) {
    const auto it = obj.find(key);
    return it != obj.end() && it->is_string() ? it->get<std::string>() : std::string{};
}

std::uint64_t count_or_zero(const Json& obj, const char* key) {
    const auto it = obj.find(key);
    return it != obj.end() && it->is_number_unsigned() ? it->get<std::uint64_t>() : 0;
}

}  // namespace

Json build_chat_payload(const std::string& model, const std::vector<Message>& messages,
                        const GenerationParams& params, bool stream) {
    Json payload = Json::object();
    payload["model"] = model;
    Json msgs = Json::array();
    for (const auto& m : messages) {
        Json e;
        to_json(e, m);
        msgs.push_back(std::move(e));
    }
    payload["messages"] = std::move(msgs);
    payload["stream"] = stream;
    if (params.keep_alive) payload["keep_alive"] = *params.keep_alive;

    Json options = Json::object();
    options["temperature"] = params.temperature;
    if (params.num_ctx) options["num_ctx"] = *params.num_ctx;
    if (params.max_tokens) options["num_predict"] = *params.max_tokens;
    if (params.repeat_penalty) options["repeat_penalty"] = *params.repeat_penalty;
    if (params.repeat_last_n) options["repeat_last_n"] = *params.repeat_last_n;
    if (params.seed) options["seed"] = *params.seed;
    payload["options"] = std::move(options);

    switch (params.constraint.kind) {
        case OutputConstraint::Kind::none: break;
        case OutputConstraint::Kind::json: payload["format"] = "json"; break;
        case OutputConstraint::Kind::json_schema: payload["format"] = params.constraint.schema; break;
    }
    if (params.think) payload["think"] = *params.think;
    return payload;
}

GenerationResult parse_chat_response(std::string_view body) {
    GenerationResult r;
    Json doc;
    try {
        doc = json_io::parse_text(body);
    } catch (const SchemaError& e) {
        r.error_code = "bad_response";
        r.error_detail = e.what();
        return r;
    }
    if (!doc.is_object()) {
        r.error_code = "bad_response";
        r.error_detail = "response is not a JSON object";
        return r;
    }
    if (const auto err = string_or_empty(doc, "error"); !err.empty()) {
        r.error_code = "server_error";
        r.error_detail = err;
        return r;
    }
    const auto msg = doc.find("message");
    if (msg == doc.end() || !msg->is_object()) {
        r.error_code = "bad_response";
        r.error_detail = "response has no message object";
        return r;
    }
    r.ok = true;
    r.content = string_or_empty(*msg, "content");
    r.thinking = string_or_empty(*msg, "thinking");
    r.done_reason = string_or_empty(doc, "done_reason");
    r.prompt_tokens = count_or_zero(doc, "prompt_eval_count");
    r.completion_tokens = count_or_zero(doc, "eval_count");
    return r;
}

std::optional<StreamChunk> parse_stream_line(std::string_view line) {
    while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.remove_suffix(1);
    if (line.empty()) return std::nullopt;
    const auto doc = json_io::parse_text(line);
    json_io::expect_object(doc, "");
    StreamChunk c;
    c.error = string_or_empty(doc, "error");
    if (const auto msg = doc.find("message"); msg != doc.end() && msg->is_object()) {
        c.content = string_or_empty(*msg, "content");
        c.thinking = string_or_empty(*msg, "thinking");
    }
    if (const auto done = doc.find("done"); done != doc.end() && done->is_boolean()) {
        c.done = done->get<bool>();
    }
    c.done_reason = string_or_empty(doc, "done_reason");
    c.prompt_tokens = count_or_zero(doc, "prompt_eval_count");
    c.completion_tokens = count_or_zero(doc, "eval_count");
    return c;
}

}  // namespace aquila::ollama
