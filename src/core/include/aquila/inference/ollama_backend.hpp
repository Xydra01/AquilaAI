#pragma once

#include "aquila/inference/backend.hpp"

#include <optional>
#include <string>
#include <vector>

namespace aquila {

struct OllamaConfig {
    std::string base_url = "http://127.0.0.1:11434";
    std::string model = "aquila";
    std::optional<std::uint32_t> num_ctx;     // default when a request sets none
    std::optional<std::string> keep_alive;    // default when a request sets none
    ComputeProfile profile = ComputeProfile::gpu_high_vram;
    double connect_timeout_s = 10.0;

    // Reads Ollama's own variables: OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_NUM_CTX
    // (positive integer, else ignored), OLLAMA_KEEP_ALIVE.
    static OllamaConfig from_env();
};

// IInferenceBackend over Ollama's HTTP API. Ollama exposes no KV control, so the
// context is kept as a message list and resent in full on every generate().
// Construction performs no I/O.
class OllamaHttpBackend final : public IInferenceBackend {
public:
    explicit OllamaHttpBackend(OllamaConfig config);

    void append(const Message& message) override;
    [[nodiscard]] std::size_t mark_checkpoint() const override;
    void rollback_to(std::size_t checkpoint) override;
    GenerationResult generate(const GenerationParams& params, const TokenCallback& on_token) override;
    [[nodiscard]] ComputeProfile active_profile() const noexcept override;
    [[nodiscard]] bool supports_kv_reuse() const noexcept override { return false; }

    // GET /api/version; the server's version string, or nullopt if it can't be reached.
    std::optional<std::string> probe(double timeout_s = 3.0) const;

    [[nodiscard]] const std::vector<Message>& context() const noexcept { return messages_; }
    [[nodiscard]] const OllamaConfig& config() const noexcept { return config_; }

private:
    OllamaConfig config_;
    std::vector<Message> messages_;
};

}  // namespace aquila
