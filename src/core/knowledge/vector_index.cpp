#include "aquila/knowledge/vector_index.hpp"

#include <algorithm>
#include <cstring>
#include <stdexcept>

namespace aquila::knowledge {

VectorIndex::VectorIndex(storage::SqliteDb& db, std::shared_ptr<IEmbeddingEngine> embedder)
    : db_(db), embedder_(std::move(embedder)) {
    init_tables();
}

void VectorIndex::init_tables() {
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS vector_entries (
            id TEXT NOT NULL,
            collection TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            vector BLOB NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (collection, id)
        );
        CREATE INDEX IF NOT EXISTS idx_vector_entries_coll ON vector_entries(collection);
    )");
}

float VectorIndex::dot_product(std::span<const float> a, std::span<const float> b) noexcept {
    if (a.size() != b.size() || a.empty()) {
        return 0.0f;
    }
    float sum = 0.0f;
    const std::size_t n = a.size();
    for (std::size_t i = 0; i < n; ++i) {
        sum += a[i] * b[i];
    }
    return sum;
}

void VectorIndex::upsert(const std::string& collection,
                         const std::string& id,
                         std::string_view content,
                         const nlohmann::json& metadata) {
    if (!embedder_) {
        throw std::runtime_error("VectorIndex::upsert requires an active IEmbeddingEngine");
    }
    const auto vec = embedder_->embed(content);
    upsert_with_vector(collection, id, content, metadata, vec);
}

void VectorIndex::upsert_with_vector(const std::string& collection,
                                     const std::string& id,
                                     std::string_view content,
                                     const nlohmann::json& metadata,
                                     std::span<const float> vector) {
    auto stmt = db_.prepare(R"(
        INSERT INTO vector_entries (id, collection, content, metadata_json, vector)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(collection, id) DO UPDATE SET
            content = excluded.content,
            metadata_json = excluded.metadata_json,
            vector = excluded.vector,
            created_at = CURRENT_TIMESTAMP
    )");

    const auto meta_str = metadata.dump();
    std::span<const uint8_t> blob(
        reinterpret_cast<const uint8_t*>(vector.data()),
        vector.size_bytes()
    );

    stmt.bind(1, id);
    stmt.bind(2, collection);
    stmt.bind(3, content);
    stmt.bind(4, meta_str);
    stmt.bind(5, blob);
    stmt.step();
}

std::vector<ScoredMatch> VectorIndex::search_dense(
    const std::string& collection,
    std::string_view query,
    std::size_t top_k,
    const std::optional<std::string>& filter_instance_id) {
    if (!embedder_) {
        throw std::runtime_error("VectorIndex::search_dense requires an active IEmbeddingEngine");
    }
    const auto q_vec = embedder_->embed(query);
    return search_dense_vector(collection, q_vec, top_k, filter_instance_id);
}

std::vector<ScoredMatch> VectorIndex::search_dense_vector(
    const std::string& collection,
    std::span<const float> query_vec,
    std::size_t top_k,
    const std::optional<std::string>& filter_instance_id) {
    if (top_k == 0 || query_vec.empty()) {
        return {};
    }

    auto stmt = db_.prepare(
        "SELECT id, content, metadata_json, vector FROM vector_entries WHERE collection = ?"
    );
    stmt.bind(1, collection);

    std::vector<ScoredMatch> matches;
    while (stmt.step()) {
        const auto id = std::string(stmt.column_text(0));
        const auto content = std::string(stmt.column_text(1));
        const auto meta_str = stmt.column_text(2);
        const auto blob = stmt.column_blob(3);

        auto meta = nlohmann::json::parse(meta_str, nullptr, false);
        if (meta.is_discarded()) {
            meta = nlohmann::json::object();
        }

        if (filter_instance_id.has_value()) {
            if (meta.value("instance_id", "") != *filter_instance_id) {
                continue;
            }
        }

        if (blob.size() % sizeof(float) != 0) {
            continue;
        }

        const std::size_t num_floats = blob.size() / sizeof(float);
        if (num_floats != query_vec.size()) {
            continue;
        }

        // Copy into aligned buffer if needed or cast
        std::vector<float> row_vec(num_floats);
        std::memcpy(row_vec.data(), blob.data(), blob.size());

        const float score = dot_product(query_vec, row_vec);
        matches.push_back(ScoredMatch{
            .id = id,
            .collection = collection,
            .content = content,
            .metadata = std::move(meta),
            .score = score,
        });
    }

    std::sort(matches.begin(), matches.end(), [](const ScoredMatch& a, const ScoredMatch& b) {
        return a.score > b.score;
    });

    if (matches.size() > top_k) {
        matches.resize(top_k);
    }
    return matches;
}

std::size_t VectorIndex::count(const std::string& collection) const {
    auto stmt = db_.prepare("SELECT count(*) FROM vector_entries WHERE collection = ?");
    stmt.bind(1, collection);
    if (stmt.step()) {
        return static_cast<std::size_t>(stmt.column_int64(0));
    }
    return 0;
}

std::size_t VectorIndex::import_chroma_db(const std::filesystem::path& chroma_db_path) {
    if (!std::filesystem::exists(chroma_db_path)) {
        return 0;
    }

    storage::SqliteDb chroma_db = storage::SqliteDb::open(chroma_db_path, SQLITE_OPEN_READONLY);

    // Verify Chroma schema
    auto check_stmt = chroma_db.prepare(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('collections', 'embeddings_queue')"
    );
    if (!check_stmt.step() || check_stmt.column_int(0) < 2) {
        return 0;
    }

    auto query_stmt = chroma_db.prepare(R"(
        SELECT c.name, eq.id, eq.vector, eq.metadata
        FROM collections c
        JOIN embeddings_queue eq ON eq.topic LIKE '%' || c.id
        ORDER BY eq.seq_id ASC
    )");

    storage::SqliteTx tx(db_);
    std::size_t imported = 0;

    auto upsert_stmt = db_.prepare(R"(
        INSERT INTO vector_entries (id, collection, content, metadata_json, vector)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(collection, id) DO UPDATE SET
            content = excluded.content,
            metadata_json = excluded.metadata_json,
            vector = excluded.vector,
            created_at = CURRENT_TIMESTAMP
    )");

    while (query_stmt.step()) {
        const auto coll_name = std::string(query_stmt.column_text(0));
        const auto doc_id = std::string(query_stmt.column_text(1));
        const auto blob = query_stmt.column_blob(2);
        const auto meta_raw = query_stmt.column_text(3);

        auto meta = nlohmann::json::parse(meta_raw, nullptr, false);
        if (meta.is_discarded()) {
            meta = nlohmann::json::object();
        }

        std::string content = meta.value("chroma:document", "");

        upsert_stmt.reset();
        upsert_stmt.clear_bindings();
        upsert_stmt.bind(1, doc_id);
        upsert_stmt.bind(2, coll_name);
        upsert_stmt.bind(3, content);
        upsert_stmt.bind(4, meta.dump());
        upsert_stmt.bind(5, blob);
        upsert_stmt.step();

        ++imported;
    }

    tx.commit();
    return imported;
}

} // namespace aquila::knowledge

