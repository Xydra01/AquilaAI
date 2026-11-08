#pragma once

#include "aquila/knowledge/document_chunker.hpp"
#include "aquila/knowledge/embedding.hpp"
#include "aquila/knowledge/page_cache.hpp"
#include "aquila/knowledge/page_scorer.hpp"
#include "aquila/knowledge/vector_index.hpp"
#include "aquila/knowledge/web_fetcher.hpp"
#include "aquila/knowledge/web_search.hpp"
#include "aquila/modules/module.hpp"
#include "aquila/storage/fact_store.hpp"
#include "aquila/storage/sqlite_db.hpp"

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace aquila::knowledge {

class KnowledgeModule final : public ModuleBase {
public:
    explicit KnowledgeModule(const ModuleContext& ctx);
    ~KnowledgeModule() override = default;

    [[nodiscard]] std::string module_id() const override { return "KnowledgeModule"; }
    [[nodiscard]] std::vector<ActionSchema> get_actions() const override;

    // initial_state: {db_path?: ":memory:" | path, max_output_chars?: integer}
    void configure(const Json& initial_state) override;

    [[nodiscard]] Json export_state_snapshot() const override;
    void restore_state_snapshot(const Json& snapshot) override;

    // Direct accessors for unit testing and host integration
    storage::FactStore& facts() noexcept { return *fact_store_; }
    VectorIndex& vectors() noexcept { return *vector_index_; }
    PageCache& cache() noexcept { return *page_cache_; }
    LocalDocIndex& doc_index() noexcept { return *doc_index_; }
    WebFetcher& fetcher() noexcept { return page_cache_->fetcher(); }
    WebSearchEngine& search_engine() noexcept { return search_engine_; }
    storage::SqliteDb& db() noexcept { return fact_store_->db(); }

protected:
    ActionResult run(const std::string& action_name, const Json& args) override;

private:
    ActionResult verify_research_deliverable_action(const Json& args);
    void init_db(const std::string& db_path_str);
    [[nodiscard]] ActionResult capped(ActionResult r) const;

    ModuleContext ctx_;
    std::size_t max_output_chars_;
    std::shared_ptr<IEmbeddingEngine> embedder_;
    std::unique_ptr<storage::FactStore> fact_store_;
    std::unique_ptr<VectorIndex> vector_index_;
    std::unique_ptr<PageCache> page_cache_;
    std::unique_ptr<LocalDocIndex> doc_index_;
    WebSearchEngine search_engine_;
    std::unordered_map<std::string, int> host_visits_;
};

} // namespace aquila::knowledge

