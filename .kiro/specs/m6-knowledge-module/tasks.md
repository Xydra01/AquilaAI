# Implementation Plan: M6 — KnowledgeModule (SQLite, Vector Store, Embeddings, Page Cache)

## Overview

Milestone M6 builds `KnowledgeModule`, the third coarse-grained module defined in R11 (`docs/design/aquila-cpp-design.md:422`), providing SQLite-backed structured fact storage, deterministic offline embeddings, native in-process vector similarity search, a high-performance C++ HTML text extractor, a persistent zero-I/O web page cache, and a hybrid local document search engine (dense vector + SQLite FTS5 lexical BM25).

The plan builds in strict dependency order:
1. **SQLite Core:** Pinned SQLite3 amalgamation with FTS5 in CMake + modern C++20 RAII wrappers (`SqliteDb`, `SqliteStmt`, `SqliteTx`).
2. **Fact Storage Parity:** Reading and writing existing `fact_graph.db` (`facts`, `scratchpad`, `workspace_summaries`) at `Agent-Memory/fact_graph.db`.
3. **Deterministic Embedder:** `HashingEmbedder` (Blake2b-64) with bit-for-bit mathematical parity to Python's `HashingEmbeddingFunction`.
4. **Native Vector Store & Chroma Ingest:** In-process vector index + dot-product cosine similarity search + importer for existing `vector_db/chroma.sqlite3`.
5. **Web Ingestion & Page Cache:** C++20 `HtmlCleaner` + `cpp-httplib` `WebFetcher` + SQLite-backed persistent `PageCache`.
6. **Local Document Index:** Structural Markdown chunking with header breadcrumbs + hybrid dense/FTS5 search.
7. **Module Integration:** `KnowledgeModule` implementing `IAgentModule`, action schemas, context condenser snapshot/restore, and `ModuleRegistry::builtin()` registration.
8. **Loop Condenser Upgrade:** Update `ContextCondenser` to use value-managed EoCC (End-of-Context Compaction) from the M5 bake-off winner.
9. **Verification:** RapidCheck property tests, Python oracle parity, 5 build presets + CI green, and RECON_MAP 8.6 / R20 accounting.

New headers land under `src/core/include/aquila/storage/` and `src/core/include/aquila/knowledge/`, sources under `src/core/storage/` and `src/core/knowledge/`, compiled into `aquila_core`. Unit tests go in `tests/unit/` (Catch2WithMain + RapidCheck).

---

## Tasks

- [x] 1. Pin SQLite3 amalgamation in CMake and configure build targets
  - Create `cmake/AquilaSqlite.cmake` fetching official SQLite 3 amalgamation pinned by URL + SHA256; compile as a static library `aquila_sqlite3` with `SQLITE_ENABLE_FTS5=1`, `SQLITE_ENABLE_RTREE=1`, and `-DSQLITE_THREADSAFE=1`
  - Ensure compiler warnings (`/W4 /WX` on MSVC, `-Werror` on Clang) are scoped so third-party SQLite code builds warning-free across all 5 presets (`msvc-release`, `msvc-asan`, `msvc-release-cuda`, `mingw-san`, `linux-san`)
  - Include `AquilaSqlite.cmake` in top-level `CMakeLists.txt` and link `aquila_sqlite3` into `aquila_core`
  - _Requirements: 1.1_

- [x] 2. Implement C++20 SQLite RAII wrappers (`SqliteDb`, `SqliteStmt`, `SqliteTx`)
  - [x] 2.1 Implement connection, statement, and transaction classes
    - Create `src/core/include/aquila/storage/sqlite_db.hpp` and `src/core/storage/sqlite_db.cpp`
    - Implement `SqliteDb`: move-only RAII handle managing `sqlite3*`, `open()`, `open_memory()`, `execute()`, `prepare()`, WAL mode configuration, and busy timeout (5000ms)
    - Implement `SqliteStmt`: move-only RAII handle managing `sqlite3_stmt*`, typed `bind` overloads (int, int64, double, string_view, blob, null), `step()`, `reset()`, column getters
    - Implement `SqliteTx`: RAII transaction scope with automatic rollback on stack unwind and explicit `commit()`
    - Implement `SqliteError`: typed exception carrying SQLite code, extended code, error message, and SQL statement
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [x]* 2.2 Write unit and property tests for SQLite RAII wrappers
    - Create `tests/unit/sqlite_db_test.cpp` (added to `tests/unit/CMakeLists.txt`)
    - **Property 1: RAII Resource Cleanup** — closing or dropping `SqliteDb` / `SqliteStmt` leaves no memory leaks under ASan/LSan/MSVC debug heap
    - **Property 2: Transaction Atomicity** — an uncommitted transaction cleanly rolls back on exception/early return; a committed transaction persists
    - **Property 3: Type Round-Trip** — integers, 64-bit ints, doubles, strings with null bytes/unicode, and binary blobs round-trip byte-for-byte
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

- [x] 3. Implement `fact_graph.db` storage access and verify against real database
  - [x] 3.1 Implement facts, scratchpad, and workspace summary operations
    - Create `src/core/include/aquila/storage/fact_store.hpp` and `src/core/storage/fact_store.cpp`
    - Implement `FactStore` wrapping `SqliteDb`:
      - `store_fact(topic, fact)` (topic lowercased, returns formatted confirmation)
      - `get_all_facts()` (formats lore string `- [TOPIC]: fact` matching Python)
      - `query_facts(topic)`
      - `save_scratchpad_note(task_name, note, instance_id)`
      - `get_scratchpad_notes(task_name, instance_id)`
      - `save_workspace_summary(instance_id, task_name, summary_text)`
      - `get_workspace_summary(instance_id, task_name)`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x]* 3.2 Write parity tests against existing user database
    - In `tests/unit/fact_store_test.cpp`: verify table schemas on a fresh database match existing `Agent-Memory/fact_graph.db` exactly
    - If `F:\Users\myfri\agent-projects\Agent-Memory\fact_graph.db` is present, assert that `FactStore` successfully opens, queries existing rows, and reads facts/scratchpads without modifying existing data
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 4. Implement Blake2b-64 and the deterministic `HashingEmbedder`
  - [x] 4.1 Implement Blake2b-64 and feature extraction
    - Create `src/core/include/aquila/knowledge/embedding.hpp`, `src/core/knowledge/embedding.cpp`, and `src/core/knowledge/blake2b.cpp`
    - Implement portable RFC 7693 Blake2b-64 (`digest_size = 8`)
    - Implement `IEmbeddingEngine` interface (`embed`, `dimension() == 384`)
    - Implement `HashingEmbedder`: lowercase normalization, `[a-z0-9]+` word extraction, char 3/4-grams for words >= 4 chars, adjacent bigrams `bg:w1_w2`, Blake2b-64 little-endian bucket index % 384, sign bit 4, L2 normalization
    - _Requirements: 3.1, 3.2, 3.3_

  - [x]* 4.2 Write Python oracle parity tests for `HashingEmbedder`
    - Generate golden embedding vectors from Python's `agent/storage/embeddings.py:HashingEmbeddingFunction` for test strings (empty, short words, punctuation, multi-byte Unicode, long code blocks)
    - Create `tests/unit/embedding_test.cpp`: assert that C++ `HashingEmbedder` matches Python golden vectors with cosine similarity >= 0.999999
    - **Property 4: Embedder Output Invariants** — for any string, vector dimension is 384, contains no NaNs or Infs, and has Euclidean norm $1.0 \pm 10^{-5}$ (unless input has zero tokens)
    - _Requirements: 3.1, 3.2_

- [x] 5. Implement `VectorIndex` and ChromaDB SQLite migration
  - [x] 5.1 Implement vector table, cosine similarity, and top-k search
    - Create `src/core/include/aquila/knowledge/vector_index.hpp` and `src/core/knowledge/vector_index.cpp`
    - Implement table `vector_entries (id, collection, content, metadata_json, vector, created_at)`
    - Implement `upsert(collection, id, content, metadata)`
    - Implement `search_dense(collection, query, top_k, filter)`: compute dot products over stored vectors, return sorted `ScoredMatch` list
    - Optional SIMD dot product (AVX2/NEON) with scalar fallback
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 5.2 Implement Chroma SQLite importer
    - Implement `import_chroma_db(path)`: open `vector_db/chroma.sqlite3`, read collections, documents from `embedding_metadata`, and float vectors from `embeddings_queue`, inserting into `VectorIndex`
    - _Requirements: 4.4, H11_

  - [x]* 5.3 Write unit and property tests for vector index and Chroma ingest
    - Create `tests/unit/vector_index_test.cpp`
    - **Property 5: Exact Nearest Neighbor** — query vector always scores 1.0 against its own stored document; scores remain monotonically ordered
    - Test Chroma import over a fixture subset from `F:\Users\myfri\agent-projects\vector_db\chroma.sqlite3`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 6. Implement `HtmlCleaner` and `WebFetcher`
  - [x] 6.1 Implement C++20 HTML text extractor
    - Create `src/core/include/aquila/knowledge/html_cleaner.hpp` and `src/core/knowledge/html_cleaner.cpp`
    - Implement streaming state-machine parser: strip `<script>`, `<style>`, `<noscript>`, `<svg>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<form>`, and comments
    - Convert block elements (`<p>`, `<div>`, `<h1>`-`<h6>`, `<li>`, `<tr>`) to clean line breaks
    - Decode HTML entities (`&quot;`, `&amp;`, `&lt;`, `&gt;`, `&#39;`, `&nbsp;`, numeric decimal/hex)
    - Normalize whitespace and redundant blank lines
    - _Requirements: 5.2_

  - [x] 6.2 Implement `WebFetcher`
    - Create `src/core/knowledge/web_fetcher.cpp` using `cpp-httplib`
    - Support HTTP/HTTPS (via cpp-httplib), redirect following (max 5 hops), 10s timeout, 2MB size cap, User-Agent header
    - Reject non-text Content-Types with typed error `unsupported_content_type`
    - _Requirements: 5.1_

  - [x]* 6.3 Write unit and property tests for HTML cleaner
    - Create `tests/unit/html_cleaner_test.cpp`
    - **Property 6: HTML Cleaner Safety** — arbitrary fuzzed or malformed HTML never crashes or hangs; script/style content is completely removed
    - Test real HTML snapshots from documentation sites
    - _Requirements: 5.1, 5.2_

- [x] 7. Implement `PageCache`
  - [x] 7.1 Implement URL canonicalization and persistent cache
    - Create `src/core/include/aquila/knowledge/page_cache.hpp` and `src/core/knowledge/page_cache.cpp`
    - Implement table `page_cache (url_hash, url, clean_text, title, content_hash, fetched_at, status_code)`
    - Implement `canonicalize_url()` (lowercase host, sorted query, strip fragment) and SHA256 hashing
    - Implement `fetch_and_clean(url, bypass_cache)`: return from SQLite on hit (0 network calls); on miss, invoke `WebFetcher` + `HtmlCleaner`, cache in SQLite, and return
    - _Requirements: 6.1, 6.2_

  - [x]* 7.2 Write unit tests for page cache
    - In `tests/unit/page_cache_test.cpp`: verify cache hit uses 0 network calls (tested with mock server); verify `bypass_cache=true` updates the cache
    - _Requirements: 6.1, 6.2_

- [x] 8. Implement `DocumentChunker` and hybrid local document search
  - [x] 8.1 Implement structural markdown chunking and indexing
    - Create `src/core/include/aquila/knowledge/document_chunker.hpp` and `src/core/knowledge/document_chunker.cpp`
    - Implement header hierarchy parser (`#`, `##`, `###`), maintaining breadcrumbs (e.g. `Doc > Section > Subsection`)
    - Sliding window token chunks for sections exceeding 512 tokens
    - Index chunks into SQLite table `doc_chunks` and FTS5 virtual table `doc_chunks_fts`
    - _Requirements: 7.1, 7.2_

  - [x] 8.2 Implement hybrid retrieval (Dense Vector + FTS5 BM25)
    - Implement `search_local_docs(query, max_results)`: run dense vector search via `HashingEmbedder` and sparse lexical search via FTS5 `MATCH`
    - Merge results via Reciprocal Rank Fusion (RRF: `score = 1/(60 + r_dense) + 1/(60 + r_sparse)`)
    - _Requirements: 7.3_

  - [x]* 8.3 Write unit tests for document chunker and hybrid search
    - Create `tests/unit/document_chunker_test.cpp`: index sample markdown documents, assert correct breadcrumbs and hybrid ranking quality
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 9. Implement `KnowledgeModule` and register in `ModuleRegistry`
  - [x] 9.1 Implement `KnowledgeModule` actions and state snapshot
    - Create `src/core/include/aquila/knowledge/knowledge_module.hpp` and `src/core/knowledge/knowledge_module.cpp`
    - Inherit `ModuleBase`, expose actions: `search_local_docs`, `fetch_and_clean_url`, `store_fact`, `recall_experiences`, `get_all_facts`
    - Implement `execute_action()` routing to underlying `FactStore`, `VectorIndex`, `PageCache`, and `DocumentChunker`
    - Implement `export_state_snapshot()` and `restore_state_snapshot()` for context condensing
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 9.2 Register `KnowledgeModule` in `ModuleRegistry`
    - In `src/core/modules/builtin.cpp`: register `"KnowledgeModule"` in `ModuleRegistry::builtin()`
    - _Requirements: 8.5_

  - [x]* 9.3 Write unit tests for `KnowledgeModule` actions and snapshots
    - Create `tests/unit/knowledge_module_test.cpp`: verify all action schemas validate, actions execute correctly, error codes are typed, and snapshots serialize/restore faithfully
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 10. Update `ContextCondenser` with SAC Strategy (Llama bake-off winner)
  - [x] 10.1 Wire `SacStrategy` into the loop condenser
    - Update `ContextCondenser` (`src/core/agent/context_condenser.cpp` and `aquila/agent/context_condenser.hpp`) to default to SAC (Single-Action-per-Context, Option A)
    - Enforce single-turn tail with running summary accumulation across actions, with clean wipe semantics
    - Wire `CondenserStrategy::sac` as default in `LoopConfig` and `AgentLoop::run()`
    - _Requirements: 9.1_

  - [x]* 10.2 Verify updated loop condenser tests
    - Run `context_condenser_test.cpp` and `agent_loop_test.cpp` asserting clean passes under SAC and EoCC
    - _Requirements: 9.1_

- [x] 11. Add end-to-end recipe cartridge test (`knowledge_smoke`)
  - Create `src/core/agent/recipes/knowledge_smoke.recipe.json`: recipe cartridge exercising `KnowledgeModule` (`search_local_docs`, `store_fact`, `get_all_facts`)
  - Create `tests/unit/knowledge_recipe_test.cpp` verifying the agent loop runs the recipe successfully with deterministic assertions
  - _Requirements: 8.5_

- [x] 12. Final verification across all presets, sanitizers, CI, and RECON_MAP accounting
  - Verify clean build and test pass on all 4 local presets (`msvc-release`, `msvc-asan`, `msvc-release-cuda`, `mingw-san`)
  - Push branch and confirm GitHub Actions CI (`windows-msvc`, `mingw-san`, `linux-san`) is 100% green
  - Update `docs/recon/RECON_MAP.md` section 8.6 with per-feature verdicts, R20 line count accounting, and mark M6 complete
  - _Requirements: 9.4_

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "4.2", "6.1"] },
    { "id": 3, "tasks": ["3.2", "5.1", "6.2"] },
    { "id": 4, "tasks": ["5.2", "5.3", "6.3", "7.1"] },
    { "id": 5, "tasks": ["7.2", "8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3", "10.1"] },
    { "id": 7, "tasks": ["9.1", "10.2"] },
    { "id": 8, "tasks": ["9.2", "9.3"] },
    { "id": 9, "tasks": ["11"] },
    { "id": 10, "tasks": ["12"] }
  ]
}
```

