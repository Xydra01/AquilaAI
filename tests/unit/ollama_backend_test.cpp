// OllamaHttpBackend against an in-process fake Ollama. The server thread is
// test-only; the backend itself stays single-threaded (R2).
#include "aquila/inference/ollama_backend.hpp"
#include "aquila/inference/ollama_wire.hpp"

#include <catch2/catch_test_macros.hpp>
#include <httplib.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace aquila;

namespace {

class FakeOllama {
public:
    using Setup = std::function<void(httplib::Server&, FakeOllama&)>;

    explicit FakeOllama(const Setup& setup) {
        setup(server_, *this);
        server_.Get("/api/version", [this](const httplib::Request&, httplib::Response& res) {
            ++version_requests;
            res.set_content(R"({"version":"0.0.0-fake"})", "application/json");
        });
        port_ = server_.bind_to_any_port("127.0.0.1");
        thread_ = std::thread([this] { server_.listen_after_bind(); });
        server_.wait_until_ready();
    }
    ~FakeOllama() {
        stopping = true;
        server_.stop();
        thread_.join();
    }
    FakeOllama(const FakeOllama&) = delete;
    FakeOllama& operator=(const FakeOllama&) = delete;

    [[nodiscard]] std::string url() const { return "http://127.0.0.1:" + std::to_string(port_); }
    [[nodiscard]] int port() const { return port_; }

    void record(const std::string& body) {
        std::lock_guard<std::mutex> lock(mutex_);
        bodies_.push_back(body);
    }
    std::vector<std::string> bodies() {
        std::lock_guard<std::mutex> lock(mutex_);
        return bodies_;
    }

    std::atomic<bool> stopping{false};
    std::atomic<int> chat_requests{0};
    std::atomic<int> version_requests{0};

private:
    httplib::Server server_;
    std::thread thread_;
    int port_ = 0;
    std::mutex mutex_;
    std::vector<std::string> bodies_;
};

// Serves `ndjson` split into pieces of `piece` bytes, each written separately.
FakeOllama::Setup stream_reply(std::string ndjson, std::size_t piece = 7, int stall_ms_after_first = 0) {
    return [ndjson, piece, stall_ms_after_first](httplib::Server& s, FakeOllama& fake) {
        s.Post("/api/chat", [ndjson, piece, stall_ms_after_first, &fake](const httplib::Request& req,
                                                                         httplib::Response& res) {
            ++fake.chat_requests;
            fake.record(req.body);
            res.set_chunked_content_provider(
                "application/x-ndjson", [ndjson, piece, stall_ms_after_first, &fake](std::size_t, httplib::DataSink& sink) {
                    for (std::size_t off = 0; off < ndjson.size(); off += piece) {
                        sink.write(ndjson.data() + off, std::min(piece, ndjson.size() - off));
                        if (off == 0 && stall_ms_after_first > 0) {
                            for (int waited = 0; waited < stall_ms_after_first && !fake.stopping; waited += 20) {
                                std::this_thread::sleep_for(std::chrono::milliseconds(20));
                            }
                            return false;
                        }
                    }
                    sink.done();
                    return true;
                });
        });
    };
}

FakeOllama::Setup json_reply(int status, std::string body) {
    return [status, body](httplib::Server& s, FakeOllama& fake) {
        s.Post("/api/chat", [status, body, &fake](const httplib::Request& req, httplib::Response& res) {
            ++fake.chat_requests;
            fake.record(req.body);
            res.status = status;
            res.set_content(body, "application/json");
        });
    };
}

const char* const kOk =
    R"({"model":"m","message":{"role":"assistant","content":"pong","thinking":"hmm"},"done":true,"done_reason":"stop","prompt_eval_count":12,"eval_count":2})";

const std::string kStream =
    std::string(R"({"message":{"role":"assistant","content":"","thinking":"let me "},"done":false})") + "\n" +
    R"({"message":{"role":"assistant","content":"","thinking":"think"},"done":false})" + "\n" +
    R"({"message":{"role":"assistant","content":"po"},"done":false})" + "\n" +
    R"({"message":{"role":"assistant","content":"ng ✓"},"done":false})" + "\n" +
    R"({"message":{"role":"assistant","content":""},"done":true,"done_reason":"stop","prompt_eval_count":31,"eval_count":4})" + "\n";

OllamaHttpBackend backend_for(const FakeOllama& fake) {
    OllamaConfig c;
    c.base_url = fake.url();
    c.model = "test-model";
    return OllamaHttpBackend(c);
}

GenerationParams quick(double timeout_s = 5.0) {
    GenerationParams p;
    p.temperature = 0.0;
    p.timeout_s = timeout_s;
    return p;
}

int closed_port() {
    int port = 0;
    {
        FakeOllama gone([](httplib::Server&, FakeOllama&) {});
        port = gone.port();
    }
    return port;
}

void set_env(const char* name, const char* value) {
#ifdef _WIN32
    _putenv_s(name, value ? value : "");
#else
    if (value) setenv(name, value, 1); else unsetenv(name);
#endif
}

}  // namespace

TEST_CASE("construction does no I/O; probe reports reachability") {
    FakeOllama fake(json_reply(200, kOk));
    auto backend = backend_for(fake);
    backend.append({Role::user, "hi", {}});
    CHECK(fake.chat_requests == 0);
    CHECK(fake.version_requests == 0);
    CHECK(backend.probe() == std::optional<std::string>("0.0.0-fake"));
    CHECK(fake.version_requests == 1);

    OllamaConfig c;
    c.base_url = "http://127.0.0.1:" + std::to_string(closed_port());
    const OllamaHttpBackend unreachable(c);
    CHECK_FALSE(unreachable.probe(1.0).has_value());
    CHECK_FALSE(unreachable.supports_kv_reuse());
}

TEST_CASE("non-streaming: request body is the payload; response fields are parsed") {
    FakeOllama fake(json_reply(200, kOk));
    auto backend = backend_for(fake);
    backend.append({Role::system, "sys", {}});
    backend.append({Role::user, "ping", {"aGVsbG8="}});
    auto params = quick();
    params.max_tokens = 8;
    params.constraint = OutputConstraint::json();

    const auto r = backend.generate(params, {});
    REQUIRE(r.ok);
    CHECK(r.content == "pong");
    CHECK(r.thinking == "hmm");
    CHECK(r.done_reason == "stop");
    CHECK(r.prompt_tokens == 12);
    CHECK(r.completion_tokens == 2);

    const auto bodies = fake.bodies();
    REQUIRE(bodies.size() == 1);
    CHECK(Json::parse(bodies[0]) == ollama::build_chat_payload("test-model", backend.context(), params, false));
}

TEST_CASE("config defaults fill num_ctx and keep_alive when the request has none") {
    FakeOllama fake(json_reply(200, kOk));
    OllamaConfig c;
    c.base_url = fake.url();
    c.num_ctx = 4096;
    c.keep_alive = "10m";
    OllamaHttpBackend backend(c);
    REQUIRE(backend.generate(quick(), {}).ok);
    auto params = quick();
    params.num_ctx = 2048;
    REQUIRE(backend.generate(params, {}).ok);
    const auto bodies = fake.bodies();
    REQUIRE(bodies.size() == 2);
    CHECK(Json::parse(bodies[0])["options"]["num_ctx"] == 4096);
    CHECK(Json::parse(bodies[0])["keep_alive"] == "10m");
    CHECK(Json::parse(bodies[1])["options"]["num_ctx"] == 2048);
}

TEST_CASE("streaming: chunks split at arbitrary boundaries reassemble in order") {
    for (const std::size_t piece : {std::size_t{1}, std::size_t{7}, std::size_t{64}, std::size_t{4096}}) {
        INFO("piece size " << piece);
        FakeOllama fake(stream_reply(kStream, piece));
        auto backend = backend_for(fake);
        backend.append({Role::user, "ping", {}});
        std::string streamed_content;
        std::string streamed_thinking;
        std::vector<std::string> order;
        const auto r = backend.generate(quick(), [&](std::string_view c, std::string_view t) {
            streamed_content += c;
            streamed_thinking += t;
            order.emplace_back(c.empty() ? "t:" + std::string(t) : "c:" + std::string(c));
            return true;
        });
        REQUIRE(r.ok);
        CHECK(r.content == "pong ✓");
        CHECK(r.thinking == "let me think");
        CHECK(streamed_content == r.content);
        CHECK(streamed_thinking == r.thinking);
        CHECK(order == std::vector<std::string>{"t:let me ", "t:think", "c:po", "c:ng ✓"});
        CHECK(r.prompt_tokens == 31);
        CHECK(r.completion_tokens == 4);
        CHECK(Json::parse(fake.bodies().at(0))["stream"] == true);
    }
}

TEST_CASE("error: refused connection is 'unreachable'") {
    OllamaConfig c;
    c.base_url = "http://127.0.0.1:" + std::to_string(closed_port());
    OllamaHttpBackend backend(c);
    const auto r = backend.generate(quick(2.0), {});
    CHECK_FALSE(r.ok);
    CHECK(r.error_code == "unreachable");
}

TEST_CASE("error: HTTP 400 is 'http_error' with status and body, streaming or not") {
    const std::string body = R"({"error":"Failed to initialize samplers"})";
    FakeOllama fake(json_reply(400, body));
    auto backend = backend_for(fake);
    const auto plain = backend.generate(quick(), {});
    CHECK(plain.error_code == "http_error");
    CHECK(plain.error_detail == "HTTP 400: " + body);
    bool called = false;
    const auto streamed = backend.generate(quick(), [&](std::string_view, std::string_view) {
        called = true;
        return true;
    });
    CHECK(streamed.error_code == "http_error");
    CHECK(streamed.error_detail == "HTTP 400: " + body);
    CHECK_FALSE(called);
}

TEST_CASE("error: garbage body is 'bad_response'") {
    FakeOllama fake(json_reply(200, "<html>proxy error</html>"));
    auto backend = backend_for(fake);
    CHECK(backend.generate(quick(), {}).error_code == "bad_response");
}

TEST_CASE("error: a streamed {\"error\"} is 'server_error' and keeps partial output") {
    FakeOllama fake(stream_reply(std::string(R"({"message":{"content":"par"},"done":false})") + "\n" +
                                 R"({"error":"model runner crashed"})" + "\n"));
    auto backend = backend_for(fake);
    const auto r = backend.generate(quick(), [](std::string_view, std::string_view) { return true; });
    CHECK(r.error_code == "server_error");
    CHECK(r.error_detail == "model runner crashed");
    CHECK(r.content == "par");
}

TEST_CASE("error: stream ending without done is 'stream_truncated'") {
    FakeOllama fake(stream_reply(std::string(R"({"message":{"content":"half"},"done":false})") + "\n"));
    auto backend = backend_for(fake);
    const auto r = backend.generate(quick(), [](std::string_view, std::string_view) { return true; });
    CHECK(r.error_code == "stream_truncated");
    CHECK(r.content == "half");
}

TEST_CASE("error: a server that stops sending is 'stream_stalled' within the timeout") {
    FakeOllama fake(stream_reply(kStream, 200, 5000));
    auto backend = backend_for(fake);
    const auto start = std::chrono::steady_clock::now();
    const auto r = backend.generate(quick(1.0), [](std::string_view, std::string_view) { return true; });
    const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::printf("stream_stalled after %.2fs (timeout 1.0s)\n", elapsed);
    CHECK(r.error_code == "stream_stalled");
    CHECK(elapsed >= 0.9);
    CHECK(elapsed < 2.0);
}

TEST_CASE("error: callback returning false is 'cancelled' with output so far") {
    FakeOllama fake(stream_reply(kStream, 4096));
    auto backend = backend_for(fake);
    int calls = 0;
    const auto r = backend.generate(quick(), [&](std::string_view, std::string_view) { return ++calls < 3; });
    CHECK(r.error_code == "cancelled");
    CHECK(calls == 3);
    CHECK(r.content == "po");
}

TEST_CASE("error: https and malformed URLs are 'unsupported_url' without any I/O") {
    for (const auto* url : {"https://127.0.0.1:11434", "ftp://x", "http://", "http://host:99999", "http://h:x"}) {
        INFO(url);
        OllamaConfig c;
        c.base_url = url;
        OllamaHttpBackend backend(c);
        CHECK(backend.generate(quick(), {}).error_code == "unsupported_url");
        CHECK_FALSE(backend.probe(0.5).has_value());
    }
}

TEST_CASE("error: content that cannot be serialized is 'invalid_request'") {
    FakeOllama fake(json_reply(200, kOk));
    auto backend = backend_for(fake);
    backend.append({Role::user, "bad \xff byte", {}});
    CHECK(backend.generate(quick(), {}).error_code == "invalid_request");
    CHECK(fake.chat_requests == 0);
}

TEST_CASE("KV degrade: rollback truncates the resent message list") {
    FakeOllama fake(json_reply(200, kOk));
    auto backend = backend_for(fake);
    backend.append({Role::system, "A", {}});
    backend.append({Role::user, "B", {}});
    const auto checkpoint = backend.mark_checkpoint();
    CHECK(checkpoint == 2);
    backend.append({Role::assistant, "C", {}});
    backend.rollback_to(checkpoint);
    backend.append({Role::user, "D", {}});
    REQUIRE(backend.generate(quick(), {}).ok);
    CHECK(backend.context().size() == 3);

    const auto sent = Json::parse(fake.bodies().at(0))["messages"];
    std::vector<std::string> contents;
    for (const auto& m : sent) contents.push_back(m["content"].get<std::string>());
    CHECK(contents == std::vector<std::string>{"A", "B", "D"});

    CHECK_THROWS_AS(backend.rollback_to(4), std::out_of_range);
    CHECK_NOTHROW(backend.rollback_to(0));
    CHECK(backend.context().empty());
}

TEST_CASE("OllamaConfig::from_env reads only Ollama's own variables") {
    set_env("OLLAMA_BASE_URL", " http://10.0.0.5:1234 ");
    set_env("OLLAMA_MODEL", "qwen3.5:9b");
    set_env("OLLAMA_NUM_CTX", "8192");
    set_env("OLLAMA_KEEP_ALIVE", "30m");
    auto c = OllamaConfig::from_env();
    CHECK(c.base_url == "http://10.0.0.5:1234");
    CHECK(c.model == "qwen3.5:9b");
    CHECK(c.num_ctx == std::optional<std::uint32_t>(8192));
    CHECK(c.keep_alive == std::optional<std::string>("30m"));

    set_env("OLLAMA_NUM_CTX", "-5");
    CHECK_FALSE(OllamaConfig::from_env().num_ctx.has_value());
    for (const auto* n : {"OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_NUM_CTX", "OLLAMA_KEEP_ALIVE"}) {
        set_env(n, nullptr);
    }
    c = OllamaConfig::from_env();
    CHECK(c.base_url == "http://127.0.0.1:11434");
    CHECK(c.model == "aquila");
    CHECK_FALSE(c.num_ctx.has_value());
}
