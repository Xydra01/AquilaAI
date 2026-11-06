#pragma once

#include "aquila/knowledge/embedding.hpp"
#include "aquila/storage/sqlite_db.hpp"

#include <cstddef>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace aquila::knowledge {

struct DocChunk {
    std::string id;
    std::string file_path;
    std::string breadcrumbs;
    std::string content;
    std::size_t chunk_index{0};
};

struct DocSearchResult {
    std::string id;
    std::string file_path;
    std::string breadcrumbs;
    std::string content;
    float rrf_score{0.0f};
    float dense_score{0.0f};
    float bm25_rank{0.0f};
};

class DocumentChunker {
public:
    explicit DocumentChunker(std::size_t max_chunk_words = 400);

    [[nodiscard]] std::vector<DocChunk> chunk_markdown(
        std::string_view markdown,
        std::string_view file_path = ""
    ) const;

private:
    std::size_t max_chunk_words_{400};
};

class LocalDocIndex {
public:
    explicit LocalDocIndex(storage::SqliteDb& db, std::shared_ptr<IEmbeddingEngine> embedder);

    void init_tables();

    void index_document(std::string_view file_path, std::string_view markdown);
    void remove_document(std::string_view file_path);

    [[nodiscard]] std::vector<DocSearchResult> search_hybrid(
        std::string_view query,
        std::size_t max_results = 5
    );

    [[nodiscard]] std::string format_search_results(
        const std::vector<DocSearchResult>& results
    ) const;

    [[nodiscard]] std::size_t chunk_count() const;

private:
    storage::SqliteDb& db_;
    std::shared_ptr<IEmbeddingEngine> embedder_;
    DocumentChunker chunker_;
};

} // namespace aquila::knowledge

