#include "aquila/agent/runtime_tier.hpp"

namespace aquila {

RuntimeTierConfig RuntimeTierConfig::for_profile(ComputeProfile profile) noexcept {
    RuntimeTierConfig config{};
    config.profile = profile;
    config.flags = UniversalFlags{};  // false on the Ollama scaffold (Req 4.3)

    switch (profile) {
        case ComputeProfile::gpu_high_vram:
            // GPU boost tier (Req 4.1): 6144 / 4 / 4500 / 150 / 999.
            config.limits = TierLimits{
                /*condense_threshold*/ 6144,
                /*rolling_tools*/ 4,
                /*tool_output_chars*/ 4500,
                /*max_thought_tokens*/ 150,
                /*gpu_layers*/ 999,
            };
            break;
        case ComputeProfile::cpu_moe_fast:
        case ComputeProfile::cpu_low_spec_edge:
            // CPU tiers share the console-first table (Req 4.1): 2048 / 2 / 1500 / 45 / 0.
            config.limits = TierLimits{
                /*condense_threshold*/ 2048,
                /*rolling_tools*/ 2,
                /*tool_output_chars*/ 1500,
                /*max_thought_tokens*/ 45,
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
