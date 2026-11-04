#include "aquila/agent/runtime_tier.hpp"
#include "aquila/inference/backend.hpp"  // ComputeProfile

#include <catch2/catch_test_macros.hpp>

using namespace aquila;

namespace {

// Asserts a config carries the CPU console-first table (Req 4.1): 2048 / 2 / 1500 / 45 / 0.
void check_cpu_limits(const TierLimits& limits) {
    CHECK(limits.condense_threshold == 2048u);
    CHECK(limits.rolling_tools == std::size_t{2});
    CHECK(limits.tool_output_chars == std::size_t{1500});
    CHECK(limits.max_thought_tokens == 45u);
    CHECK(limits.gpu_layers == 0u);
    CHECK(limits.max_turns == 16u);
}

// Asserts a config carries the GPU boost table (Req 4.1): 6144 / 4 / 4500 / 150 / 999.
void check_gpu_limits(const TierLimits& limits) {
    CHECK(limits.condense_threshold == 6144u);
    CHECK(limits.rolling_tools == std::size_t{4});
    CHECK(limits.tool_output_chars == std::size_t{4500});
    CHECK(limits.max_thought_tokens == 150u);
    CHECK(limits.gpu_layers == 999u);
    CHECK(limits.max_turns == 16u);
}

}  // namespace

// Req 4.1: the exact tier value table per ComputeProfile.
TEST_CASE("for_profile returns the exact tier table") {
    SECTION("cpu_low_spec_edge is the CPU console-first table") {
        const auto cfg = RuntimeTierConfig::for_profile(ComputeProfile::cpu_low_spec_edge);
        CHECK(cfg.profile == ComputeProfile::cpu_low_spec_edge);
        check_cpu_limits(cfg.limits);
    }

    SECTION("cpu_moe_fast shares the CPU console-first table") {
        const auto cfg = RuntimeTierConfig::for_profile(ComputeProfile::cpu_moe_fast);
        CHECK(cfg.profile == ComputeProfile::cpu_moe_fast);
        check_cpu_limits(cfg.limits);
    }

    SECTION("gpu_high_vram is the GPU boost table") {
        const auto cfg = RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram);
        CHECK(cfg.profile == ComputeProfile::gpu_high_vram);
        check_gpu_limits(cfg.limits);
    }
}

// Req 4.1: max_turns defaults to 16 on every tier.
TEST_CASE("max_turns defaults to 16 on all tiers") {
    CHECK(RuntimeTierConfig::for_profile(ComputeProfile::cpu_low_spec_edge).limits.max_turns == 16u);
    CHECK(RuntimeTierConfig::for_profile(ComputeProfile::cpu_moe_fast).limits.max_turns == 16u);
    CHECK(RuntimeTierConfig::for_profile(ComputeProfile::gpu_high_vram).limits.max_turns == 16u);
}

// Req 4.2: CPU-first default. default_config() is a CPU tier, never GPU.
TEST_CASE("default_config is a CPU tier and GPU is not the default") {
    const auto cfg = RuntimeTierConfig::default_config();
    CHECK(cfg.profile == ComputeProfile::cpu_low_spec_edge);
    CHECK_FALSE(cfg.profile == ComputeProfile::gpu_high_vram);
    check_cpu_limits(cfg.limits);
}

// Req 4.3: UniversalFlags present on every tier and all false on the Ollama scaffold.
TEST_CASE("universal flags are present and all false on the scaffold") {
    for (const auto profile : {ComputeProfile::cpu_low_spec_edge, ComputeProfile::cpu_moe_fast,
                               ComputeProfile::gpu_high_vram}) {
        const auto cfg = RuntimeTierConfig::for_profile(profile);
        CHECK_FALSE(cfg.flags.kv_rollback);
        CHECK_FALSE(cfg.flags.gbnf);
        CHECK_FALSE(cfg.flags.ngram);
    }
}
