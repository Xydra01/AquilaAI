#include "aquila/agent/micro_pass.hpp"
#include "replay_backend.hpp"

#include <catch2/catch_test_macros.hpp>

using namespace aquila;
using aquila::test::ReplayBackend;

TEST_CASE("micro_pass executes isolated turn and restores context") {
    GenerationResult reply;
    reply.ok = true;
    reply.content = "Here is the micro-pass summary.";
    reply.prompt_tokens = 42;
    reply.completion_tokens = 12;

    ReplayBackend backend({reply});

    // Populate some initial context
    backend.append(Message{Role::system, "Main agent system prompt", {}});
    backend.append(Message{Role::user, "Main conversation turn 1", {}});
    const std::size_t cp_before = backend.mark_checkpoint();
    CHECK(cp_before == 2);

    MicroPassOptions opts;
    opts.system_prompt = "You are a specialized summarizer.";
    opts.user_prompt = "Summarize the document.";
    opts.temperature = 0.2;
    opts.max_tokens = 256;

    MicroPassResult res = run_micro_pass(backend, opts);

    CHECK(res.success);
    CHECK(res.content == "Here is the micro-pass summary.");
    CHECK(res.prompt_tokens == 42);
    CHECK(res.completion_tokens == 12);
    CHECK(res.error_code.empty());

    // Context must be restored exactly to 2 turns
    CHECK(backend.mark_checkpoint() == cp_before);
    CHECK(backend.context().size() == 2);
    CHECK(backend.context()[0].content == "Main agent system prompt");
    CHECK(backend.context()[1].content == "Main conversation turn 1");
}

TEST_CASE("micro_pass handles generation failure and preserves rollback") {
    GenerationResult fail_reply;
    fail_reply.ok = false;
    fail_reply.error_code = "timeout";
    fail_reply.error_detail = "inference timed out";

    ReplayBackend backend({fail_reply});
    backend.append(Message{Role::user, "Hello", {}});
    const std::size_t cp_before = backend.mark_checkpoint();

    MicroPassOptions opts;
    opts.user_prompt = "Quick check";

    MicroPassResult res = run_micro_pass(backend, opts);

    CHECK_FALSE(res.success);
    CHECK(res.error_code == "timeout");
    CHECK(res.error_detail == "inference timed out");

    // Context must still be restored
    CHECK(backend.mark_checkpoint() == cp_before);
    CHECK(backend.context().size() == 1);
}

