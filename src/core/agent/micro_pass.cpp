#include "aquila/agent/micro_pass.hpp"

namespace aquila {

namespace {

struct RollbackGuard {
    IInferenceBackend& backend;
    std::size_t cp;
    ~RollbackGuard() {
        try {
            backend.rollback_to(cp);
        } catch (...) {
        }
    }
};

}  // namespace

MicroPassResult run_micro_pass(
    IInferenceBackend& backend,
    const MicroPassOptions& options) {
    const std::size_t initial_cp = backend.mark_checkpoint();
    RollbackGuard guard{backend, initial_cp};

    if (!options.system_prompt.empty()) {
        backend.append(Message{Role::system, options.system_prompt, {}});
    }
    backend.append(Message{Role::user, options.user_prompt, {}});

    GenerationParams params;
    params.temperature = options.temperature;
    params.max_tokens = options.max_tokens;
    params.constraint = options.constraint;

    GenerationResult gen = backend.generate(params, options.on_token);

    MicroPassResult res;
    res.success = gen.ok;
    res.error_code = std::move(gen.error_code);
    res.error_detail = std::move(gen.error_detail);
    res.content = std::move(gen.content);
    res.thinking = std::move(gen.thinking);
    res.prompt_tokens = gen.prompt_tokens;
    res.completion_tokens = gen.completion_tokens;

    return res;
}

}  // namespace aquila

