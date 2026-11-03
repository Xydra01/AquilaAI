#pragma once

#include "aquila/inference/backend.hpp"

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::ollama {

// Request body for POST /api/chat. Key order:
//   model, messages, stream, keep_alive?, options{temperature, num_ctx?, num_predict?,
//   repeat_penalty?, repeat_last_n?, seed?}, format?, think?
// temperature goes in options: Ollama's ChatRequest has no top-level temperature
// (api/types.go), so Python's top-level field (main.py:808) is silently ignored.
Json build_chat_payload(const std::string& model, const std::vector<Message>& messages,
                        const GenerationParams& params, bool stream);

// Parses a non-streaming /api/chat response body.
GenerationResult parse_chat_response(std::string_view body);

struct StreamChunk {
    std::string content;
    std::string thinking;
    std::string error;  // set when the server streams {"error": ...}
    bool done = false;
    std::string done_reason;
    std::uint64_t prompt_tokens = 0;
    std::uint64_t completion_tokens = 0;
};

// Parses one NDJSON line of a streaming response. Blank lines give nullopt;
// a malformed line throws SchemaError.
std::optional<StreamChunk> parse_stream_line(std::string_view line);

}  // namespace aquila::ollama
