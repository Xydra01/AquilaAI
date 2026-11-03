#pragma once

#include "aquila/json.hpp"
#include "aquila/types/message.hpp"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <string_view>

namespace aquila {

// Hardware tier the backend runs on (R16). Tier policy lives in RuntimeTierConfig (M4).
enum class ComputeProfile { gpu_high_vram, cpu_moe_fast, cpu_low_spec_edge };

// What the output must conform to. Backends translate it: Ollama takes `format`,
// llama.cpp (M5) turns a JSON schema into GBNF.
struct OutputConstraint {
    enum class Kind { none, json, json_schema };
    Kind kind = Kind::none;
    Json schema;  // only for json_schema

    static OutputConstraint none() { return {}; }
    static OutputConstraint json() { return {Kind::json, {}}; }
    static OutputConstraint json_schema(Json s) { return {Kind::json_schema, std::move(s)}; }
};

// Every knob is explicit; unset optionals are omitted from the request so the
// server or model default applies.
struct GenerationParams {
    double temperature = 0.6;
    std::optional<std::uint32_t> max_tokens;  // Ollama num_predict
    std::optional<std::uint32_t> num_ctx;
    std::optional<double> repeat_penalty;
    std::optional<std::uint32_t> repeat_last_n;
    std::optional<std::int64_t> seed;
    std::optional<bool> think;
    std::optional<std::string> keep_alive;
    OutputConstraint constraint;
    double timeout_s = 120.0;  // no-progress limit for a response or stream
};

// error_code is empty exactly when ok (same convention as ActionResult):
//   unreachable, timeout, stream_stalled, stream_truncated, http_error,
//   server_error, bad_response, cancelled, unsupported_url, invalid_request,
//   transport_error
struct GenerationResult {
    bool ok = false;
    std::string error_code;
    std::string error_detail;
    std::string content;
    std::string thinking;
    std::string done_reason;
    std::uint64_t prompt_tokens = 0;
    std::uint64_t completion_tokens = 0;
};

// Called per streamed chunk; return false to cancel the generation.
using TokenCallback = std::function<bool(std::string_view content, std::string_view thinking)>;

// KV-aware inference backend (R15). The context is a sequence of messages; a
// checkpoint is a position in it. Backends that cannot reuse KV (Ollama over
// HTTP) resend the whole context on every generate().
class IInferenceBackend {
public:
    virtual ~IInferenceBackend() = default;

    virtual void append(const Message& message) = 0;
    [[nodiscard]] virtual std::size_t mark_checkpoint() const = 0;
    // Throws std::out_of_range if `checkpoint` is past the current end.
    virtual void rollback_to(std::size_t checkpoint) = 0;

    // Generates a reply to the current context, which is left unchanged; append
    // the reply yourself to keep it. A non-empty on_token streams the reply.
    virtual GenerationResult generate(const GenerationParams& params, const TokenCallback& on_token) = 0;

    [[nodiscard]] virtual ComputeProfile active_profile() const noexcept = 0;
    [[nodiscard]] virtual bool supports_kv_reuse() const noexcept = 0;
};

}  // namespace aquila
