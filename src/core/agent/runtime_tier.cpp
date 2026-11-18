#include "aquila/agent/runtime_tier.hpp"

namespace aquila {

RuntimeTierConfig RuntimeTierConfig::for_profile(ComputeProfile profile) noexcept {
    RuntimeTierConfig config{};
    config.profile = profile;
    config.flags = UniversalFlags{};  // false on the Ollama scaffold (Req 4.3)

    switch (profile) {
        case ComputeProfile::gpu_high_vram:
            // GPU boost tier (Qwen 3.5 9B @ 32K ctx): 16384 / 6 / 8000 / 192 / 999.
            config.limits = TierLimits{
                /*condense_threshold*/ 16384,
                /*rolling_tools*/ 6,
                /*tool_output_chars*/ 8000,
                /*max_thought_tokens*/ 192,
                /*gpu_layers*/ 999,
            };
            break;
        case ComputeProfile::cpu_moe_fast:
        case ComputeProfile::cpu_low_spec_edge:
            // CPU tiers share the Qwen 3.5 4B table (@ 16K ctx): 8192 / 3 / 3000 / 128 / 0.
            config.limits = TierLimits{
                /*condense_threshold*/ 8192,
                /*rolling_tools*/ 3,
                /*tool_output_chars*/ 3000,
                /*max_thought_tokens*/ 128,
                /*gpu_layers*/ 0,
            };
            break;
    }

    return config;
}

RuntimeTierConfig RuntimeTierConfig::default_config() noexcept {
    // CPU-first (Req 4.2): the CPU edge tier is the default; GPU is an explicit boost.
    return for_profile(ComputeProfile::cpu_low_spec_edge);
}

}  // namespace aquila
