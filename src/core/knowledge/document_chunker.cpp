#include "aquila/knowledge/document_chunker.hpp"
#include "aquila/knowledge/vector_index.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstring>
#include <sstream>
#include <unordered_map>

namespace aquila::knowledge {

namespace {

std::size_t count_words(std::string_view s) {
    std::size_t count = 0;
    bool in_word = false;
    for (char c : s) {
        if (std::isspace(static_cast<unsigned char>(c))) {
            in_word = false;
        } else if (!in_word) {
            in_word = true;
            ++count;
        }
    }
    return count;
}

std::string trim_spaces(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return std::string(s);
}

std::string make_breadcrumb_string(const std::vector<std::pair<int, std::string>>& stack, std::string_view fallback) {
    if (stack.empty()) {
        return std::string(fallback);
    }
    std::string out;
    for (std::size_t i = 0; i < stack.size(); ++i) {
        if (i > 0) out.append(" > ");
        out.append(stack[i].second);
    }
    return out;
}

std::string sanitize_fts_query(std::string_view query) {
    std::string clean;
    std::vector<std::string> words;
    std::string cur;
    for (char c : query) {
        if (std::isalnum(static_cast<unsigned char>(c))) {
            cur.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        } else if (!cur.empty()) {
            words.push_back(cur);
            cur.clear();
        }
    }
    if (!cur.empty()) {
        words.push_back(cur);
    }

    if (words.empty()) {
        return "";
    }

    std::string fts;
    for (std::size_t i = 0; i < words.size(); ++i) {
        if (i > 0) fts.append(" OR ");
        fts.append(words[i]);
    }
    return fts;
}

} // namespace

DocumentChunker::DocumentChunker(std::size_t max_chunk_words)
    : max_chunk_words_(max_chunk_words) {}

std::vector<DocChunk> DocumentChunker::chunk_markdown(
    std::string_view markdown,
    std::string_view file_path) const {
    std::vector<DocChunk> chunks;
    std::vector<std::pair<int, std::string>> header_stack;

    std::size_t chunk_idx = 0;
    std::string current_content;

    auto flush_chunk = [&](bool is_eof = false) {
        auto trimmed = trim_spaces(current_content);
        if (!trimmed.empty() || (is_eof && chunks.empty())) {
            std::string bc = make_breadcrumb_string(header_stack, file_path.empty() ? "Document" : file_path);
            std::string id = std::string(file_path) + ":" + std::to_string(chunk_idx);
            chunks.push_back(DocChunk{
                .id = std::move(id),
                .file_path = std::string(file_path),
                .breadcrumbs = std::move(bc),
                .content = std::move(trimmed),
                .chunk_index = chunk_idx++
            });
        }
        current_content.clear();
    };

    std::istringstream stream{std::string(markdown)};
    std::string line;

    while (std::getline(stream, line)) {
        // Check for markdown header
        std::size_t h_count = 0;
        while (h_count < line.size() && line[h_count] == '#') {
            ++h_count;
        }

        if (h_count >= 1 && h_count <= 6 && h_count < line.size() && line[h_count] == ' ') {
            // Header detected
            flush_chunk();

            int level = static_cast<int>(h_count);
            std::string title = trim_spaces(line.substr(h_count + 1));

            while (!header_stack.empty() && header_stack.back().first >= level) {
                header_stack.pop_back();
            }
            header_stack.push_back({level, title});
            continue;
        }

        // Regular line
        current_content.append(line);
        current_content.push_back('\n');

        // Check if chunk size exceeded at paragraph boundary
        if (trim_spaces(line).empty() && count_words(current_content) >= max_chunk_words_) {
            flush_chunk();
        }
    }

    flush_chunk(true);
    return chunks;
}

LocalDocIndex::LocalDocIndex(storage::SqliteDb& db, std::shared_ptr<IEmbeddingEngine> embedder)
    : db_(db), embedder_(std::move(embedder)) {
    init_tables();
}

void LocalDocIndex::init_tables() {
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS doc_chunks (
            id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            breadcrumbs TEXT NOT NULL,
            content TEXT NOT NULL,
            vector BLOB NOT NULL,
            chunk_index INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_doc_chunks_file ON doc_chunks(file_path);

        CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5(
            id UNINDEXED,
            breadcrumbs,
            content,
            tokenize='porter unicode61'
        );
    )");
}

void LocalDocIndex::remove_document(std::string_view file_path) {
    auto del_fts = db_.prepare(
        "DELETE FROM doc_chunks_fts WHERE id IN (SELECT id FROM doc_chunks WHERE file_path = ?)"
    );
    del_fts.bind(1, file_path);
    del_fts.step();

    auto del_chunks = db_.prepare("DELETE FROM doc_chunks WHERE file_path = ?");
    del_chunks.bind(1, file_path);
    del_chunks.step();
}

void LocalDocIndex::index_document(std::string_view file_path, std::string_view markdown) {
    if (!embedder_) {
        throw std::runtime_error("LocalDocIndex requires an active IEmbeddingEngine");
    }

    remove_document(file_path);

    const auto chunks = chunker_.chunk_markdown(markdown, file_path);
    if (chunks.empty()) return;

    storage::SqliteTx tx(db_);

    auto insert_chunk = db_.prepare(R"(
        INSERT INTO doc_chunks (id, file_path, breadcrumbs, content, vector, chunk_index)
        VALUES (?, ?, ?, ?, ?, ?)
    )");

    auto insert_fts = db_.prepare(R"(
        INSERT INTO doc_chunks_fts (id, breadcrumbs, content)
        VALUES (?, ?, ?)
    )");

    for (const auto& chunk : chunks) {
        // Embed text combined with breadcrumbs for better semantic matching
        std::string embed_text = chunk.breadcrumbs + "\n" + chunk.content;
        const auto vec = embedder_->embed(embed_text);
        std::span<const uint8_t> blob(
            reinterpret_cast<const uint8_t*>(vec.data()),
            vec.size() * sizeof(float)
        );

        insert_chunk.reset();
        insert_chunk.clear_bindings();
        insert_chunk.bind(1, chunk.id);
        insert_chunk.bind(2, chunk.file_path);
        insert_chunk.bind(3, chunk.breadcrumbs);
        insert_chunk.bind(4, chunk.content);
        insert_chunk.bind(5, blob);
        insert_chunk.bind(6, static_cast<int64_t>(chunk.chunk_index));
        insert_chunk.step();

        insert_fts.reset();
        insert_fts.clear_bindings();
        insert_fts.bind(1, chunk.id);
        insert_fts.bind(2, chunk.breadcrumbs);
        insert_fts.bind(3, chunk.content);
        insert_fts.step();
    }

    tx.commit();
}

std::size_t LocalDocIndex::chunk_count() const {
    auto stmt = db_.prepare("SELECT count(*) FROM doc_chunks");
    if (stmt.step()) {
        return static_cast<std::size_t>(stmt.column_int64(0));
    }
    return 0;
}

std::vector<DocSearchResult> LocalDocIndex::search_hybrid(
    std::string_view query,
    std::size_t max_results) {
    if (max_results == 0 || query.empty() || !embedder_) {
        return {};
    }

    struct Candidate {
        DocSearchResult result;
        int dense_rank{0};
        int sparse_rank{0};
    };

    std::unordered_map<std::string, Candidate> candidates;

    // 1. Dense vector scan
    const auto q_vec = embedder_->embed(query);
    struct DenseMatch {
        std::string id;
        std::string file_path;
        std::string breadcrumbs;
        std::string content;
        float score{0.0f};
    };

    std::vector<DenseMatch> dense_matches;
    auto dense_stmt = db_.prepare("SELECT id, file_path, breadcrumbs, content, vector FROM doc_chunks");
    while (dense_stmt.step()) {
        const auto id = std::string(dense_stmt.column_text(0));
        const auto file_path = std::string(dense_stmt.column_text(1));
        const auto breadcrumbs = std::string(dense_stmt.column_text(2));
        const auto content = std::string(dense_stmt.column_text(3));
        const auto blob = dense_stmt.column_blob(4);

        if (blob.size() % sizeof(float) != 0) continue;
        const std::size_t n_floats = blob.size() / sizeof(float);
        if (n_floats != q_vec.size()) continue;

        std::vector<float> row_vec(n_floats);
        std::memcpy(row_vec.data(), blob.data(), blob.size());

        float score = VectorIndex::dot_product(q_vec, row_vec);
        dense_matches.push_back(DenseMatch{
            .id = id,
            .file_path = file_path,
            .breadcrumbs = breadcrumbs,
            .content = content,
            .score = score
        });
    }

    std::sort(dense_matches.begin(), dense_matches.end(), [](const DenseMatch& a, const DenseMatch& b) {
        return a.score > b.score;
    });

    for (std::size_t i = 0; i < dense_matches.size(); ++i) {
        int rank = static_cast<int>(i + 1);
        const auto& m = dense_matches[i];
        auto& cand = candidates[m.id];
        cand.result.id = m.id;
        cand.result.file_path = m.file_path;
        cand.result.breadcrumbs = m.breadcrumbs;
        cand.result.content = m.content;
        cand.result.dense_score = m.score;
        cand.dense_rank = rank;
    }

    // 2. Sparse FTS5 lexical scan
    std::string fts_query = sanitize_fts_query(query);
    if (!fts_query.empty()) {
        try {
            auto fts_stmt = db_.prepare(
                "SELECT id, bm25(doc_chunks_fts) as rank FROM doc_chunks_fts WHERE doc_chunks_fts MATCH ? ORDER BY rank LIMIT 50"
            );
            fts_stmt.bind(1, fts_query);

            int sparse_rank = 1;
            while (fts_stmt.step()) {
                const auto id = std::string(fts_stmt.column_text(0));
                const float rank_val = static_cast<float>(fts_stmt.column_double(1));

                auto& cand = candidates[id];
                cand.result.id = id;
                cand.result.bm25_rank = rank_val;
                cand.sparse_rank = sparse_rank++;
            }
        } catch (...) {
            // If FTS MATCH fails on unusual characters, continue with dense results only
        }
    }

    // If candidate content was missing from sparse-only hits, load from doc_chunks
    for (auto& [id, cand] : candidates) {
        if (cand.result.content.empty()) {
            auto fetch_stmt = db_.prepare("SELECT file_path, breadcrumbs, content FROM doc_chunks WHERE id = ?");
            fetch_stmt.bind(1, id);
            if (fetch_stmt.step()) {
                cand.result.file_path = std::string(fetch_stmt.column_text(0));
                cand.result.breadcrumbs = std::string(fetch_stmt.column_text(1));
                cand.result.content = std::string(fetch_stmt.column_text(2));
            }
        }
    }

    // 3. Reciprocal Rank Fusion (RRF constant k = 60)
    std::vector<DocSearchResult> scored;
    scored.reserve(candidates.size());

    constexpr float kRrfK = 60.0f;
    for (auto& [id, cand] : candidates) {
        float rrf = 0.0f;
        if (cand.dense_rank > 0) {
            rrf += 1.0f / (kRrfK + static_cast<float>(cand.dense_rank));
        }
        if (cand.sparse_rank > 0) {
            rrf += 1.0f / (kRrfK + static_cast<float>(cand.sparse_rank));
        }
        cand.result.rrf_score = rrf;
        scored.push_back(std::move(cand.result));
    }

    std::sort(scored.begin(), scored.end(), [](const DocSearchResult& a, const DocSearchResult& b) {
        return a.rrf_score > b.rrf_score;
    });

    if (scored.size() > max_results) {
        scored.resize(max_results);
    }
    return scored;
}

std::string LocalDocIndex::format_search_results(const std::vector<DocSearchResult>& results) const {
    if (results.empty()) {
        return "No relevant local documents found for the given query.";
    }

    std::ostringstream oss;
    oss << "### Relevant Documentation (" << results.size() << " matches):\n\n";
    for (std::size_t i = 0; i < results.size(); ++i) {
        const auto& r = results[i];
        oss << "**[" << (i + 1) << "] " << r.file_path << "**\n";
        oss << "*Section:* " << r.breadcrumbs << " *(RRF score: " << r.rrf_score << ")*\n\n";
        oss << "```markdown\n" << r.content << "\n```\n\n";
    }
    return oss.str();
}

} // namespace aquila::knowledge

