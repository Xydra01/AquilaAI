#pragma once

#include "aquila/inference/backend.hpp"  // ComputeProfile (R16); do not redefine

#include <cstddef>
#include <cstdint>

namespace aquila {

// Per-tier knobs (R16, D:L706-734). CPU-first: a CPU tier is the default and the
// GPU tier is an explicit boost. The loop and condenser read every threshold from
// here; there are no hardcoded limits in loop or condenser code (Req 4.4).
struct TierLimits {
    std::uint32_t condense_threshold = 2048;  // prompt tokens that trigger a wipe
    std::size_t rolling_tools = 2;             // K: tool cycles kept in the rolling tail
    std::size_t tool_output_chars = 1500;      // head+tail truncation budget per result
    std::uint32_t max_thought_tokens = 45;     // cap on the action call's `thought`
    std::uint32_t gpu_layers = 0;              // layers offloaded to the GPU (0 = CPU-only)
    std::uint32_t max_turns = 16;              // loop turn cap (parity: code_agent.py `_max_turns`)
};

// Flags present on every tier regardless of hardware (Req 4.3). On the Ollama
// scaffold (M2) KV rollback and GBNF are unsupported, so they report `false`;
// M5's llama.cpp backend flips them without a config change.
struct UniversalFlags {
    bool kv_rollback = false;  // real KV checkpoint/rollback (M5)
    bool gbnf = false;         // GBNF-constrained generation (M5)
    bool ngram = false;        // n-gram prompt-lookup speculation (R17, M5)
};

// Maps a ComputeProfile to its limits and the universal flags (R16).
struct RuntimeTierConfig {
    ComputeProfile profile = ComputeProfile::cpu_low_spec_edge;
    TierLimits limits{};
    UniversalFlags flags{};

    // Exact tier table (Req 4.1):
    //   cpu_low_spec_edge / cpu_moe_fast -> 2048 / 2 / 1500 / 45 / 0
    //   gpu_high_vram                    -> 6144 / 4 / 4500 / 150 / 999
    [[nodiscard]] static RuntimeTierConfig for_profile(ComputeProfile profile) noexcept;

    // CPU-first default: the cpu_low_spec_edge tier (Req 4.2). GPU is an explicit
    // boost, never the default.
    [[nodiscard]] static RuntimeTierConfig default_config() noexcept;
};

}  // namespace aquila
