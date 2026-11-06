#pragma once

#include "aquila/knowledge/embedding.hpp"
#include "aquila/storage/sqlite_db.hpp"

#include <cstddef>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

namespace aquila::knowledge {

struct ScoredMatch {
    std::string id;
    std::string collection;
    std::string content;
    nlohmann::json metadata;
    float score{0.0f};
};

class VectorIndex {
public:
    explicit VectorIndex(storage::SqliteDb& db, std::shared_ptr<IEmbeddingEngine> embedder = nullptr);

    void init_tables();

    void upsert(const std::string& collection,
                const std::string& id,
                std::string_view content,
                const nlohmann::json& metadata);

    void upsert_with_vector(const std::string& collection,
                            const std::string& id,
                            std::string_view content,
                            const nlohmann::json& metadata,
                            std::span<const float> vector);

    [[nodiscard]] std::vector<ScoredMatch> search_dense(
        const std::string& collection,
        std::string_view query,
        std::size_t top_k,
        const std::optional<std::string>& filter_instance_id = std::nullopt);

    [[nodiscard]] std::vector<ScoredMatch> search_dense_vector(
        const std::string& collection,
        std::span<const float> query_vec,
        std::size_t top_k,
        const std::optional<std::string>& filter_instance_id = std::nullopt);

    [[nodiscard]] std::size_t count(const std::string& collection) const;

    // Migrate from Chroma SQLite database (chroma.sqlite3)
    std::size_t import_chroma_db(const std::filesystem::path& chroma_db_path);

    [[nodiscard]] static float dot_product(std::span<const float> a, std::span<const float> b) noexcept;

private:
    storage::SqliteDb& db_;
    std::shared_ptr<IEmbeddingEngine> embedder_;
};

} // namespace aquila::knowledge

