#pragma once

#include "aquila/knowledge/web_search.hpp"
#include "aquila/modules/module.hpp"

#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace aquila::knowledge {

// Interactive headless browser module delegating rendering, JS execution, DOM
// extraction, and viewport screenshots to an out-of-process `aquila_browser`
// worker over line-delimited JSON-RPC (keeping aquila_core Qt-free).
class BrowserModule final : public ModuleBase {
public:
    explicit BrowserModule(const ModuleContext& ctx);
    ~BrowserModule() override;

    BrowserModule(const BrowserModule&) = delete;
    BrowserModule& operator=(const BrowserModule&) = delete;

    [[nodiscard]] std::string module_id() const override { return "BrowserModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    // Direct structured web search returning typed SearchResult objects without LLM formatting.
    [[nodiscard]] std::vector<SearchResult> search_structured(const std::string& query, int max_results = 5, bool force_browser = false);
    [[nodiscard]] std::vector<SearchResult> search_browser_direct(const std::string& query, int max_results = 5);

    // initial_state: {browser_bin?: path, search_base_url?: url, searxng_endpoint?: url, timeout_ms?: int, max_output_chars?: int, max_screenshots?: int}
    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    [[nodiscard]] Json export_context_summary() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    [[nodiscard]] std::string current_url() const { return current_url_; }
    [[nodiscard]] std::string current_title() const { return current_title_; }

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    struct WorkerProcess;
    struct VisitedUrlInfo {
        std::string url;
        std::string title;
        int visit_count = 0;
        int max_scroll_pct = 0;
    };
    struct FailedUrlInfo {
        std::string url;
        std::string error_code;
        std::string reason;
    };

    bool ensure_worker(std::string& error_out);
    Json call_worker(const std::string& action, const Json& params, std::string& error_code, std::string& error_msg);
    std::string next_screenshot_path();
    void prune_old_screenshots(const std::string& just_saved_path) const;
    void record_discovered_url(const std::string& url, const std::string& snippet = {});
    void record_visited_url(const std::string& url, const std::string& title, int scroll_pct, bool increment_visit);
    void record_failed_url(const std::string& url, const std::string& error_code, const std::string& reason);
    [[nodiscard]] std::vector<std::string> unvisited_suggestions(std::size_t max_count = 3) const;
    ActionResult format_snapshot_result(const std::string& header,
                                        const Json& res,
                                        bool attach_screenshot,
                                        bool count_as_new_visit = false,
                                        const std::string& leading_note = {});

    ModuleContext ctx_;
    std::string browser_bin_;
    std::string search_base_url_;
    std::string searxng_endpoint_ = "http://127.0.0.1:8888";
    std::string session_stamp_;
    int default_timeout_ms_ = 25000;
    std::size_t max_output_chars_ = 4000;
    std::size_t max_screenshots_ = 100;
    std::uint64_t req_seq_ = 0;
    std::uint64_t shot_seq_ = 0;
    std::string current_url_;
    std::string current_title_;
    std::vector<std::string> visited_order_;
    std::unordered_map<std::string, VisitedUrlInfo> visited_urls_;
    std::vector<std::string> failed_order_;
    std::unordered_map<std::string, FailedUrlInfo> failed_urls_;
    std::unordered_map<std::string, int> timeout_counts_;
    std::vector<std::string> discovered_urls_;
    std::unordered_map<std::string, std::string> discovered_snippets_;
    std::vector<std::string> searched_queries_;
    std::unique_ptr<WorkerProcess> worker_;
};

} // namespace aquila::knowledge

