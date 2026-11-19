#include "aquila/knowledge/browser_module.hpp"
#include "aquila/modules/registry.hpp"

#include <httplib.h>
#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>

using aquila::ActionResult;
using aquila::Json;
using aquila::ModuleContext;
using aquila::ModuleRegistry;
using aquila::knowledge::BrowserModule;

namespace {

struct TempDir {
    std::filesystem::path dir;
    TempDir() {
        static std::atomic<int> counter{0};
        dir = std::filesystem::temp_directory_path() /
              ("aquila_browser_test_" + std::to_string(++counter));
        std::filesystem::remove_all(dir);
        std::filesystem::create_directories(dir);
    }
    ~TempDir() {
        std::error_code ec;
        std::filesystem::remove_all(dir, ec);
    }
    const std::filesystem::path& path() const { return dir; }
};

class LocalTestServer {
public:
    LocalTestServer() {
        svr_.Get("/search", [this](const httplib::Request& req, httplib::Response& res) {
            const std::string q = req.has_param("q") ? req.get_param_value("q") : "";
            const std::string html =
                "<!doctype html><html><head><title>Local Search</title></head><body>"
                "<div class=\"result\">"
                "  <a class=\"result__a\" href=\"" + base_url() + "/app\">Interactive App Result</a>"
                "  <p class=\"result__snippet\">Synthetic match for " + q + " with live JS panel.</p>"
                "</div>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/app", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Aquila Interactive JS Page</title>"
                "<style>"
                "body{background:#0f172a;color:#e2e8f0;font-family:sans-serif;padding:24px;min-height:2200px}"
                "input{padding:8px;font-size:16px}"
                "button{padding:10px 18px;background:#2563eb;color:#fff;border:none}"
                "</style></head><body>"
                "<h1>Browser Interactive Harness</h1>"
                "<input id=\"query\" type=\"text\" placeholder=\"Enter token\" />"
                "<button id=\"go\" onclick=\"document.getElementById('result').textContent = "
                "'Computed: ' + document.getElementById('query').value;\">Run Action</button>"
                "<div id=\"result\">Waiting for input</div>"
                "<div style=\"margin-top:1500px\" id=\"footer\">Bottom Section Reached</div>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/captcha", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Verify you are human</title></head><body>"
                "<h1>Please verify you are human</h1>"
                "<div class=\"g-recaptcha\" data-sitekey=\"dummy\"></div>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/explore", [this](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Exploration Hub</title>"
                "<style>body{background:#0f172a;color:#e2e8f0;font-family:sans-serif;padding:24px;min-height:2400px}</style>"
                "</head><body><main>"
                "<h1>Exploration Hub</h1>"
                "<button id=\"tab-specs\" role=\"tab\" aria-expanded=\"false\" "
                "onclick=\"this.setAttribute('aria-expanded','true');document.getElementById('tab-out').textContent='TAB_REVEALED_99';\">Deep Specs</button>"
                "<div id=\"tab-out\"></div>"
                "<details><summary id=\"acc-summary\">Expand Benchmarks</summary><p>ACCORDION_SECRET_77</p></details>"
                "<p><a id=\"nav-link\" href=\"" + base_url() + "/details\">Open Primary Details</a></p>"
                "<p><a id=\"blank-link\" target=\"_blank\" href=\"" + base_url() + "/details\">Open Details In New Tab</a></p>"
                "<div style=\"margin-top:1800px\" id=\"deep-footer\">DEEP_SCROLL_FOOTER_OK</div>"
                "</main></body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/details", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Primary Details Page</title></head><body>"
                "<h1>Primary Details Reached</h1><p>DETAIL_PAYLOAD_VERIFIED</p>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/soft404", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Game decompilation - Wikipedia</title></head><body>"
                "<h1>Game decompilation</h1>"
                "<p>Wikipedia does not have an article with this exact name.</p>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/site-search", [this](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Site Search Fixture</title></head><body>"
                "<nav><div id=\"ca-view\"><a href=\"" + base_url() + "/details\">Read</a></div>"
                "<div id=\"frb-mini-banner\"><a href=\"https://donate.wikimedia.org/wiki\">Donate now</a></div></nav>"
                "<main>"
                "<form action=\"/site-results\" method=\"get\">"
                "<input id=\"site-q\" type=\"search\" name=\"q\" placeholder=\"Search docs\"/>"
                "<button type=\"submit\">Go</button>"
                "</form>"
                "<p><a id=\"real-link\" href=\"" + base_url() + "/details\">Real Article Link</a></p>"
                "</main></body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/site-results", [](const httplib::Request& req, httplib::Response& res) {
            const std::string q = req.has_param("q") ? req.get_param_value("q") : "";
            const std::string html =
                "<!doctype html><html><head><title>Search Results for " + q + "</title></head><body>"
                "<main><h1>Site Results</h1><p>QUERY_ECHO_" + q + "</p></main>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/stall-asset", [](const httplib::Request&, httplib::Response& res) {
            std::this_thread::sleep_for(std::chrono::milliseconds(4000));
            res.set_content("/* delayed */", "text/javascript");
        });

        svr_.Get("/slow-article", [](const httplib::Request&, httplib::Response& res) {
            const std::string body(450, 'A');
            const std::string html =
                "<!doctype html><html><head><title>Slow Blog Article</title></head><body>"
                "<main><h1>Partial Recovery Headline</h1>"
                "<p>PARTIAL_ARTICLE_BODY_OK " + body + "</p>"
                "<img src=\"/stall-asset\" alt=\"slow tracker\"/>"
                "</main></body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/anchor-page", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Anchor Page</title>"
                "<style>body{margin:0;padding:24px}</style></head><body><main>"
                "<h1>Top Section</h1>"
                "<div style=\"margin-top:2200px\"><h2 id=\"Consumption_by_adults\">Consumption by adults</h2>"
                "<p>ANCHOR_SECTION_REACHED_42</p></div>"
                "</main></body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/aws-waf", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title></title></head><body>"
                "<script>AwsWafIntegration.saveReferrer();</script>"
                "<h1>JavaScript is disabled</h1>"
                "<p>In order to continue, we need to verify that you're not a robot. Enable JavaScript and then reload the page.</p>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/reddit-js", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>Reddit - The heart of the internet</title></head><body>"
                "<script>window.CLIENT_EXPERIMENTS = {\"secret\":\"nope\"};</script>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        svr_.Get("/xy-click", [](const httplib::Request&, httplib::Response& res) {
            const std::string html =
                "<!doctype html><html><head><title>XY Fallback</title>"
                "<style>body{margin:0;padding:0}#real-xy-btn{position:fixed;left:20px;top:20px;width:160px;height:60px}</style>"
                "</head><body>"
                "<button id=\"real-xy-btn\" onclick=\"document.getElementById('xy-out').textContent='XY_FALLBACK_CLICKED_OK'\">Click Me</button>"
                "<p id=\"xy-out\" style=\"margin-top:100px\">initial</p>"
                "</body></html>";
            res.set_content(html, "text/html; charset=utf-8");
        });

        port_ = svr_.bind_to_any_port("127.0.0.1");
        REQUIRE(port_ > 0);
        thread_ = std::thread([this]() { svr_.listen_after_bind(); });
    }

    ~LocalTestServer() {
        svr_.stop();
        if (thread_.joinable()) {
            thread_.join();
        }
    }

    std::string base_url() const { return "http://127.0.0.1:" + std::to_string(port_); }

private:
    httplib::Server svr_;
    int port_ = 0;
    std::thread thread_;
};

} // namespace

TEST_CASE("BrowserModule registers cleanly and exposes valid schemas", "[browser][registry]") {
    const auto reg = ModuleRegistry::builtin();
    REQUIRE(reg.contains("BrowserModule"));

    TempDir tmp;
    auto mod = reg.create("BrowserModule", ModuleContext{tmp.path(), 4000});
    REQUIRE(mod != nullptr);
    CHECK(mod->module_id() == "BrowserModule");
    const auto actions = mod->get_actions();
    CHECK(actions.size() == 9);
    auto has_action = [&](const std::string& name) {
        return std::any_of(actions.begin(), actions.end(), [&](const auto& a) { return a.action_name == name; });
    };
    CHECK(has_action("browser_search"));
    CHECK(has_action("browser_navigate"));
    CHECK(has_action("browser_click"));
    CHECK(has_action("browser_type"));
    CHECK(has_action("browser_scroll"));
    CHECK(has_action("browser_find"));
    CHECK(has_action("browser_login"));
    CHECK(has_action("browser_extract_text"));
    CHECK(has_action("browser_screenshot"));
}

TEST_CASE("BrowserModule state snapshot round-trips cleanly", "[browser]") {
    TempDir tmp;
    BrowserModule mod(ModuleContext{tmp.path(), 4000});
    mod.configure(Json::object({{"search_base_url", "http://127.0.0.1:9999/search"}}));

    const Json snap = mod.export_state_snapshot();
    BrowserModule restored(ModuleContext{tmp.path(), 4000});
    restored.restore_state_snapshot(snap);
    CHECK(restored.export_state_snapshot() == snap);
}

#ifdef AQUILA_HAS_BROWSER
TEST_CASE("BrowserModule executes JS navigation, typing, clicking, scrolling, screenshots, and blocks challenges",
          "[browser][integration]") {
    LocalTestServer server;
    TempDir tmp;

    BrowserModule mod(ModuleContext{tmp.path(), 4000});
    mod.configure(Json::object({{"search_base_url", server.base_url() + "/search"}}));

    // Reject non-HTTP(S) schemes before reaching Chromium.
    const ActionResult bad_scheme = mod.execute_action(
        "browser_navigate", Json::object({{"url", "file:///C:/Windows/win.ini"}}));
    CHECK_FALSE(bad_scheme.success);
    CHECK(bad_scheme.error_code == "invalid_url");

    // 1. Search returns structured links
    const ActionResult search_res = mod.execute_action(
        "browser_search", Json::object({{"query", "hybrid attention"}}));
    INFO(search_res.llm_facing_output);
    REQUIRE(search_res.success);
    CHECK(search_res.llm_facing_output.find("Interactive App Result") != std::string::npos);
    CHECK(search_res.llm_facing_output.find(server.base_url() + "/app") != std::string::npos);

    // 1b. Structured search returns typed SearchResult vector directly
    const auto structured = mod.search_structured("hybrid attention", 5);
    REQUIRE(structured.size() == 1);
    CHECK(structured[0].title == "Interactive App Result");
    CHECK(structured[0].url == server.base_url() + "/app");
    CHECK(structured[0].snippet.find("Synthetic match for hybrid attention") != std::string::npos);
    CHECK(structured[0].engine == "aquila_browser");
    CHECK(structured[0].score >= 0.9);

    // 2. Navigate loads JS page and attaches PNG screenshot in ActionResult::images
    const ActionResult nav_res = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/app"}}));
    INFO(nav_res.llm_facing_output);
    REQUIRE(nav_res.success);
    CHECK(nav_res.llm_facing_output.find("Browser Interactive Harness") != std::string::npos);
    REQUIRE(nav_res.images.size() == 1);
    REQUIRE(std::filesystem::exists(nav_res.images[0]));
    CHECK(std::filesystem::file_size(nav_res.images[0]) > 500);

    // 3. Type into input & click JS button -> DOM reflects computed update
    const ActionResult type_res = mod.execute_action(
        "browser_type", Json::object({{"selector", "#query"}, {"text", "aquila_hybrid"}}));
    INFO(type_res.llm_facing_output);
    REQUIRE(type_res.success);

    const ActionResult click_res = mod.execute_action(
        "browser_click", Json::object({{"selector", "#go"}}));
    INFO(click_res.llm_facing_output);
    REQUIRE(click_res.success);
    CHECK(click_res.llm_facing_output.find("Computed: aquila_hybrid") != std::string::npos);

    // 4. Extract text & scroll down
    const ActionResult ext_res = mod.execute_action(
        "browser_extract_text", Json::object({{"selector", "#result"}}));
    REQUIRE(ext_res.success);
    CHECK(ext_res.llm_facing_output.find("Computed: aquila_hybrid") != std::string::npos);

    const ActionResult scroll_res = mod.execute_action(
        "browser_scroll", Json::object({{"direction", "down"}, {"pixels", 1500}}));
    REQUIRE(scroll_res.success);
    CHECK(scroll_res.llm_facing_output.find("Scroll: y=") != std::string::npos);
    CHECK(scroll_res.llm_facing_output.find("Scroll: y=0 ") == std::string::npos);
    CHECK(scroll_res.llm_facing_output.find("Bottom Section Reached") != std::string::npos);

    // 5. Challenge / CAPTCHA page is explicitly detected & refused (never bypassed)
    const ActionResult cap_res = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/captcha"}}));
    CHECK_FALSE(cap_res.success);
    CHECK(cap_res.error_code == "challenge_detected");
}

TEST_CASE("BrowserModule preserves screenshots across separate instances and honors max_screenshots pruning",
          "[browser][integration][screenshots]") {
    LocalTestServer server;
    TempDir tmp;

    // Instance 1 and Instance 2 share the same workspace root; neither should overwrite the other.
    BrowserModule mod1(ModuleContext{tmp.path(), 4000});
    const ActionResult r1 = mod1.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/app"}}));
    REQUIRE(r1.success);
    REQUIRE(r1.images.size() == 1);

    BrowserModule mod2(ModuleContext{tmp.path(), 4000});
    const ActionResult r2 = mod2.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/app"}}));
    REQUIRE(r2.success);
    REQUIRE(r2.images.size() == 1);

    CHECK(r1.images[0] != r2.images[0]);
    CHECK(std::filesystem::exists(r1.images[0]));
    CHECK(std::filesystem::exists(r2.images[0]));

    // Configure max_screenshots = 2 and capture a 3rd screenshot -> oldest file is pruned cleanly.
    mod2.configure(Json::object({{"max_screenshots", 2}}));
    const ActionResult r3 = mod2.execute_action("browser_screenshot", Json::object());
    REQUIRE(r3.success);
    REQUIRE(r3.images.size() == 1);
    CHECK(std::filesystem::exists(r3.images[0]));

    const auto shot_dir = tmp.path() / ".aquila" / "browser_screenshots";
    int png_count = 0;
    for (const auto& entry : std::filesystem::directory_iterator(shot_dir)) {
        if (entry.is_regular_file() && entry.path().extension() == ".png") {
            ++png_count;
        }
    }
    CHECK(png_count == 2);
}

TEST_CASE("BrowserModule exposes scroll cues, tabs/accordions, waits for link clicks, and handles target=_blank",
          "[browser][integration][explore]") {
    LocalTestServer server;
    TempDir tmp;

    BrowserModule mod(ModuleContext{tmp.path(), 4000});
    const ActionResult nav = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/explore"}}));
    INFO(nav.llm_facing_output);
    REQUIRE(nav.success);
    CHECK(nav.llm_facing_output.find("remaining below fold") != std::string::npos);
    CHECK(nav.llm_facing_output.find("[role=tab]") != std::string::npos);
    CHECK(nav.llm_facing_output.find("[collapsed]") != std::string::npos);
    CHECK(nav.llm_facing_output.find("#acc-summary") != std::string::npos);

    // Click tab and accordion summary
    const ActionResult tab = mod.execute_action(
        "browser_click", Json::object({{"selector", "#tab-specs"}}));
    INFO(tab.llm_facing_output);
    REQUIRE(tab.success);
    CHECK(tab.llm_facing_output.find("TAB_REVEALED_99") != std::string::npos);
    CHECK(tab.llm_facing_output.find("[expanded]") != std::string::npos);

    const ActionResult acc = mod.execute_action(
        "browser_click", Json::object({{"selector", "#acc-summary"}}));
    INFO(acc.llm_facing_output);
    REQUIRE(acc.success);
    CHECK(acc.llm_facing_output.find("ACCORDION_SECRET_77") != std::string::npos);

    // Scroll to bottom -> reaches bottom cue
    const ActionResult bottom = mod.execute_action(
        "browser_scroll", Json::object({{"direction", "bottom"}}));
    INFO(bottom.llm_facing_output);
    REQUIRE(bottom.success);
    CHECK(bottom.llm_facing_output.find("reached bottom of page") != std::string::npos);
    CHECK(bottom.llm_facing_output.find("DEEP_SCROLL_FOOTER_OK") != std::string::npos);

    // Clicking a standard <a href> waits for full page load and captures destination content
    const ActionResult link_click = mod.execute_action(
        "browser_click", Json::object({{"selector", "#nav-link"}}));
    INFO(link_click.llm_facing_output);
    REQUIRE(link_click.success);
    CHECK(link_click.llm_facing_output.find("Primary Details Page") != std::string::npos);
    CHECK(link_click.llm_facing_output.find("DETAIL_PAYLOAD_VERIFIED") != std::string::npos);

    // Clicking a target="_blank" link redirects into active page instead of silently dropping
    REQUIRE(mod.execute_action("browser_navigate", Json::object({{"url", server.base_url() + "/explore"}})).success);
    const ActionResult blank_click = mod.execute_action(
        "browser_click", Json::object({{"selector", "#blank-link"}}));
    INFO(blank_click.llm_facing_output);
    REQUIRE(blank_click.success);
    CHECK(blank_click.llm_facing_output.find("Primary Details Page") != std::string::npos);
    CHECK(blank_click.llm_facing_output.find("DETAIL_PAYLOAD_VERIFIED") != std::string::npos);
}

TEST_CASE("BrowserModule enforces URL memory, scroll clamping, chrome filtering, and submit nav-wait",
          "[browser][integration][hardening]") {
    LocalTestServer server;
    TempDir tmp;

    BrowserModule mod(ModuleContext{tmp.path(), 4000});

    // 1. Soft-404 fails cleanly and records URL in failed_urls_do_not_retry; retry fast-fails
    const ActionResult s404 = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/soft404"}}));
    CHECK_FALSE(s404.success);
    CHECK(s404.error_code == "page_not_found");

    const ActionResult s404_retry = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/soft404"}}));
    CHECK_FALSE(s404_retry.success);
    CHECK(s404_retry.error_code == "already_failed_url");

    const Json ctx_after_404 = mod.export_context_summary();
    REQUIRE(ctx_after_404.contains("failed_urls_do_not_retry"));
    CHECK(ctx_after_404["failed_urls_do_not_retry"].dump().find("/soft404") != std::string::npos);

    // 2. Scroll step > 1600px is clamped to 1600px
    REQUIRE(mod.execute_action("browser_navigate", Json::object({{"url", server.base_url() + "/explore"}})).success);
    const ActionResult big_scroll = mod.execute_action(
        "browser_scroll", Json::object({{"direction", "down"}, {"pixels", 5000}}));
    INFO(big_scroll.llm_facing_output);
    REQUIRE(big_scroll.success);
    CHECK(big_scroll.llm_facing_output.find("clamped from 5000px to 1600px") != std::string::npos);
    CHECK(big_scroll.llm_facing_output.find("Scroll: y=1600") != std::string::npos);

    // 3. Visited URL memory surfaces in export_context_summary & guards duplicate 3rd reload
    REQUIRE(mod.execute_action("browser_scroll", Json::object({{"direction", "bottom"}})).success);
    const ActionResult revisit2 = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/explore"}}));
    REQUIRE(revisit2.success);
    CHECK(revisit2.llm_facing_output.find("REVISIT NOTICE") != std::string::npos);

    const ActionResult revisit3 = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/explore"}}));
    CHECK_FALSE(revisit3.success);
    CHECK(revisit3.error_code == "duplicate_navigation");

    const Json ctx_visited = mod.export_context_summary();
    REQUIRE(ctx_visited.contains("visited_urls_do_not_reload"));
    CHECK(ctx_visited["visited_urls_do_not_reload"].dump().find("/explore") != std::string::npos);

    // 4. Wikipedia chrome links (#ca-view, #frb-mini-banner) filtered; [search-input] tagged;
    //    browser_type(submit=true) waits for navigation to /site-results
    const ActionResult search_page = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/site-search"}}));
    INFO(search_page.llm_facing_output);
    REQUIRE(search_page.success);
    CHECK(search_page.llm_facing_output.find("donate.wikimedia.org") == std::string::npos);
    CHECK(search_page.llm_facing_output.find("#ca-view") == std::string::npos);
    CHECK(search_page.llm_facing_output.find("Real Article Link") != std::string::npos);
    CHECK(search_page.llm_facing_output.find("[search-input]") != std::string::npos);

    const ActionResult typed = mod.execute_action(
        "browser_type", Json::object({
            {"selector", "#site-q"},
            {"text", "ghidra"},
            {"submit", true},
        }));
    INFO(typed.llm_facing_output);
    REQUIRE(typed.success);
    CHECK(typed.llm_facing_output.find("QUERY_ECHO_ghidra") != std::string::npos);

    // 5. Partial-DOM recovery on slow background asset timeout
    const ActionResult partial = mod.execute_action(
        "browser_navigate", Json::object({
            {"url", server.base_url() + "/slow-article"},
            {"timeout_ms", 1200},
        }));
    INFO(partial.llm_facing_output);
    REQUIRE(partial.success);
    CHECK(partial.llm_facing_output.find("PARTIAL_ARTICLE_BODY_OK") != std::string::npos);
    CHECK(partial.llm_facing_output.find("Load Note:") != std::string::npos);

    // 6. Same-document #fragment anchor navigation scrolls cleanly without timing out
    REQUIRE(mod.execute_action("browser_navigate", Json::object({{"url", server.base_url() + "/anchor-page"}})).success);
    const ActionResult anchor = mod.execute_action(
        "browser_navigate", Json::object({
            {"url", server.base_url() + "/anchor-page#Consumption_by_adults"},
            {"timeout_ms", 3000},
        }));
    INFO(anchor.llm_facing_output);
    REQUIRE(anchor.success);
    CHECK(anchor.llm_facing_output.find("ANCHOR_SECTION_REACHED_42") != std::string::npos);

    // 7. AWS WAF & Reddit JS-challenge detection
    const ActionResult waf = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/aws-waf"}}));
    CHECK_FALSE(waf.success);
    CHECK(waf.error_code == "challenge_detected");

    const ActionResult rjs = mod.execute_action(
        "browser_navigate", Json::object({{"url", server.base_url() + "/reddit-js?js_challenge=1&jsc_token=abc"}}));
    CHECK_FALSE(rjs.success);
    CHECK(rjs.error_code == "challenge_detected");

    // 8. browser_click falls back to (x, y) when guessed selector misses
    REQUIRE(mod.execute_action("browser_navigate", Json::object({{"url", server.base_url() + "/xy-click"}})).success);
    const ActionResult xy = mod.execute_action(
        "browser_click", Json::object({
            {"selector", "#does-not-exist > a:nth-child(99)"},
            {"x", 80},
            {"y", 45},
        }));
    INFO(xy.llm_facing_output);
    REQUIRE(xy.success);
    CHECK(xy.llm_facing_output.find("XY_FALLBACK_CLICKED_OK") != std::string::npos);

    // 9. browser_find in-page Ctrl+F jumps to keyword and extracts snippet
    REQUIRE(mod.execute_action("browser_navigate", Json::object({{"url", server.base_url() + "/anchor-page"}})).success);
    const ActionResult find_res = mod.execute_action(
        "browser_find", Json::object({
            {"query", "ANCHOR_SECTION_REACHED_42"},
            {"match_index", 1},
        }));
    INFO(find_res.llm_facing_output);
    REQUIRE(find_res.success);
    CHECK(find_res.llm_facing_output.find("Found 1 match") != std::string::npos);
    CHECK(find_res.llm_facing_output.find("ANCHOR_SECTION_REACHED_42") != std::string::npos);

    // 10. browser_login handles missing credential gracefully
    const ActionResult login_res = mod.execute_action(
        "browser_login", Json::object({
            {"domain", "unknown-service-without-credentials.org"},
        }));
    CHECK_FALSE(login_res.success);
    CHECK(login_res.error_code == "no_credentials_found");
}
#endif

