#pragma once

#include "aquila/inference/backend.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace aquila {

struct MicroPassOptions {
    std::string system_prompt;
    std::string user_prompt;
    double temperature = 0.0;
    std::uint32_t max_tokens = 1024;
    OutputConstraint constraint = OutputConstraint::none();
    TokenCallback on_token = nullptr;
};

struct MicroPassResult {
    bool success = false;
    std::string error_code;
    std::string error_detail;
    std::string content;
    std::string thinking;
    std::uint64_t prompt_tokens = 0;
    std::uint64_t completion_tokens = 0;
};

// Executes a single-turn, isolated generation against the inference backend.
// Preserves the existing KV cache / context by rolling back to the initial checkpoint
// on exit.
MicroPassResult run_micro_pass(
    IInferenceBackend& backend,
    const MicroPassOptions& options);

}  // namespace aquila

