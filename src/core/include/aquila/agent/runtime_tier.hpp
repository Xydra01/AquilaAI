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
// M5's llama.cpp backend reports its own via for_llama_backend() (honest per D14).
struct UniversalFlags {
    bool kv_rollback = false;  // mid-sequence KV wipe usable as a context mechanism (M5)
    bool gbnf = false;         // GBNF-constrained generation (M5)
    bool ngram = false;        // n-gram prompt-lookup speculation (R17, M5)

    // The flag reality for the M5 llama.cpp backend, recorded honestly after the
    // D14 bake-off (RECON_MAP 8.5):
    //   gbnf        = TRUE  -- the backend enforces the action schema by GBNF.
    //   kv_rollback = FALSE -- M5 flips this to its HONEST value, not simply true.
    //       The bake-off showed mid-sequence KV rollback is both unsupported on the
    //       Qwen 3.5 M-RoPE path (F1) AND the wrong context mechanism on every family
    //       incl. plain-RoPE (kv_rollback strategy scored 1/6 everywhere; it discards
    //       the tail that holds task state). Only full-reset rollback is used, which
    //       the value-managed strategies (EoCC/SAC) rely on. So the capability the
    //       flag names -- a cheap mid-sequence wipe that preserves context -- is NOT
    //       available, and the flag stays false rather than overclaiming.
    //   ngram       = FALSE -- R17 prompt-lookup speculation deferred past M5.
    [[nodiscard]] static UniversalFlags for_llama_backend() noexcept {
        UniversalFlags f{};
        f.gbnf = true;
        f.kv_rollback = false;  // see the note above: honest, not aspirational
        f.ngram = false;
        return f;
    }
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
