# Requirements Document: M6 — KnowledgeModule (SQLite, Vector Store, Embeddings, Page Cache)

## Introduction

Milestone M6 builds the third core module specified in R11 (`docs/design/aquila-cpp-design.md:422`): **`KnowledgeModule`**. It equips Aquila-cpp with persistent structured memory, semantic vector search, deterministic embeddings, local document indexing, and a zero-I/O web page cache.

Scope, from the M6 row of `docs/recon/RECON_MAP.md` section 8:
> **`KnowledgeModule`** (SQLite + vector + embeddings + page cache)

Proof of done, from the same row:
> Reads existing `fact_graph.db`; recall@k on fixture matches Python within tolerance.

### Governing Principles & Architectural Directives

- **R1 (Strict C++20 & RAII):** Zero raw owning pointers. RAII wrappers manage all SQLite connection handles (`sqlite3*`) and statement handles (`sqlite3_stmt*`), transaction scopes (`SqliteTx`), and memory buffers.
- **R2 (Single-Threaded Deterministic Core):** Synchronous operations over an embedded SQLite engine. No background async runtimes or complex multi-threaded lock queues.
- **R9 / R11 (Coarse-Grained Module Boundary):** KnowledgeModule owns persistent database handles, cached documents/pages, and query history. It exposes three primary actions to the LLM:
  1. `search_local_docs(query, max_results)`
  2. `fetch_and_clean_url(url, bypass_cache)`
  3. `store_fact(topic, fact)`
  plus auxiliary memory actions (`recall_experiences`, `get_all_facts`, `save_scratchpad_note`).
- **R13 (Compile-Time Registry):** `KnowledgeModule` registers into `ModuleRegistry::builtin()` alongside `WorkspaceModule`, `ExecutionModule`, and `OrchestratorModule`.
- **R19 (Improve, Don't Transliterate):** Python's `DualMemorySystem` relied on heavy external Python-only packages (ChromaDB, BeautifulSoup4, cloudscraper, onnxruntime). C++ replaces these with lightweight, in-process, native native C++20 implementations:
  - SQLite with FTS5 replaces ChromaDB's SQLite+HNSW directory structure for local agent scales.
  - Portable Blake2b hashing embedder provides 100% offline, deterministic vector embeddings with zero weights file dependency.
  - High-performance C++ HTML text extractor replaces BeautifulSoup4/markdownify boilerplate.
  - SQLite persistent page cache provides true zero-network-I/O repeat lookups (which Python lacked).
- **R20 (Condense):** Replaces ~4,000 lines of Python across `agent/storage/` and `agent/research/` with a clean, cohesive, typed C++ module.
- **H10 / H11 (Chroma Replacement & Data Compatibility):** Must directly read existing `fact_graph.db` (`facts`, `scratchpad`, `workspace_summaries`) at `Agent-Memory/fact_graph.db`. Must provide a clean reader/migrator for existing `vector_db/chroma.sqlite3` records so existing episodic memories remain accessible.
- **D14 (Context Management Handoff):** Integrate the winning strategy from the M5 bake-off (**EoCC** — End-of-Context Compaction) into the loop's `ContextCondenser` workflow.

---

## Requirements

### Requirement 1: SQLite3 Integration & C++20 RAII Wrappers

1.1 **Dependency Management:** Pinned SQLite 3 (version >= 3.47) fetched via `cmake/AquilaDeps.cmake` (or `cmake/AquilaSqlite.cmake`) by archive URL and SHA256 checksum. Compiled with `SQLITE_ENABLE_FTS5=1` (for full-text search) and `SQLITE_THREADSAFE=0` (or `1` serialized). Must build cleanly on all 5 project presets without compiler warnings.
1.2 **Connection Wrapper (`SqliteDb`):**
  - Owning RAII wrapper managing `sqlite3*`.
  - Move-only semantics (no copies); destructor safely finalizes and calls `sqlite3_close_v2`.
  - Methods: `open(path, flags)`, `open_memory()`, `is_open()`, `execute(sql)`, `last_insert_rowid()`, `changes()`.
  - Configurable busy timeout (default 5000ms) and WAL mode enablement on file databases.
1.3 **Statement Wrapper (`SqliteStmt`):**
  - Owning RAII wrapper managing `sqlite3_stmt*`.
  - Move-only semantics; destructor calls `sqlite3_finalize`.
  - Parameter binding helpers supporting `int`, `int64_t`, `double`, `std::string_view`, `std::span<const uint8_t>` (BLOB), and `std::nullptr_t`.
  - Step execution: `step() -> bool` (returns true on `SQLITE_ROW`, false on `SQLITE_DONE`).
  - Column getters: `column_int(col)`, `column_int64(col)`, `column_double(col)`, `column_text(col)`, `column_blob(col)`, `column_type(col)`, `is_null(col)`.
  - Reset and clear bindings helpers (`reset()`, `clear_bindings()`).
1.4 **Transaction Wrapper (`SqliteTx`):**
  - RAII transaction scope executing `BEGIN IMMEDIATE`.
  - Automatically executes `ROLLBACK` on stack unwind/destruction unless `commit()` was explicitly called.
1.5 **Error Handling:** All SQLite errors must be caught and converted to typed exceptions (`SqliteError`) containing the SQLite error code, extended error code, message, and the SQL string that failed. Never leak raw error strings into LLM context unmanaged.

### Requirement 2: Compatibility with Existing `fact_graph.db`

2.1 **Table Schema Preservation:** Must open and operate upon existing `fact_graph.db` located at `Agent-Memory/fact_graph.db` without altering existing table definitions:
  - `facts (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, fact TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)`
  - `scratchpad (id INTEGER PRIMARY KEY AUTOINCREMENT, task_name TEXT, note TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)`
  - `workspace_summaries (instance_id TEXT NOT NULL, task_name TEXT NOT NULL, summary_text TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (instance_id, task_name))`
2.2 **Facts Access:**
  - `store_fact(topic, fact)` inserts a row into `facts` with lowercased topic.
  - `get_all_facts()` retrieves all facts ordered by topic and formatted identically to Python (`- [TOPIC]: fact`).
  - `query_facts(topic)` retrieves facts matching a specific topic.
2.3 **Scratchpad Access:**
  - `save_scratchpad_note(task_name, note, instance_id)` saves a note with key `instance_id::task_name`.
  - `get_scratchpad_notes(task_name, instance_id)` retrieves all notes in chronological order.
2.4 **Workspace Summaries Access:**
  - `save_workspace_summary(instance_id, task_name, summary_text)` upserts a summary.
  - `get_workspace_summary(instance_id, task_name)` retrieves the summary text.

### Requirement 3: Deterministic Hashing Embedder (`HashingEmbedder`)

3.1 **Interface Definition (`IEmbeddingEngine`):**
  - `virtual std::vector<float> embed(std::string_view text) const = 0;`
  - `virtual std::vector<std::vector<float>> embed_batch(std::span<const std::string> texts) const = 0;`
  - `virtual std::size_t dimension() const noexcept = 0;`
3.2 **Exact Python Algorithm Parity:** `HashingEmbedder` must reproduce Python's `HashingEmbeddingFunction` (`agent/storage/embeddings.py:226-300`) with cosine distance < 1e-6:
  - Output dimension: 384 floats.
  - Text normalization: lowercase, replace `_` and `-` with space.
  - Tokenization: regex `[a-z0-9]+`.
  - Feature extraction:
    - Base word tokens.
    - Character 3-grams and 4-grams for every token of length >= 4 (`ng3:xyz`, `ng4:xyzw`).
    - Adjacent word bigrams: `bg:word1_word2`.
  - Blake2b Hashing: RFC 7693 Blake2b-64 with `digest_size = 8` on UTF-8 token bytes.
  - Vector accumulation:
    - Bucket index: `(uint32_t)(digest[0..3] little-endian) % 384`.
    - Sign: `+1.0` if `(digest[4] % 2 == 0)` else `-1.0`.
  - Normalization: L2 Euclidean norm; if norm > 0, divide each element by norm.
3.3 **Zero Dependencies:** Pure in-tree C++ implementation; requires no network, no external weights file, and no ONNX runtime.

### Requirement 4: Vector Index & Similarity Search (`VectorIndex`)

4.1 **Vector Storage Schema:**
  - Create table `vector_entries (id TEXT PRIMARY KEY, collection TEXT NOT NULL, content TEXT NOT NULL, metadata_json TEXT NOT NULL, vector BLOB NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)`.
  - `vector` stored as 384 contiguous IEEE 754 32-bit floats (1536 bytes).
4.2 **Indexing & Upsert:**
  - Insert or replace entries with collection name, document ID, text content, JSON metadata, and computed float vector.
4.3 **Cosine Similarity Query:**
  - Compute dot product between normalized query vector and stored normalized vectors.
  - Optional SIMD acceleration (AVX2 / SSE / NEON) with scalar fallback.
  - Return top-k matches with score (range [-1.0, 1.0]), ID, content, and metadata.
4.4 **ChromaDB Migration / Ingest:**
  - Capable of reading `chroma.sqlite3` (`embeddings_queue`, `embedding_metadata`, `collections`) to import prior episodic memories (`episodic_experiences`) and tool documents into the native vector store.

### Requirement 5: HTML Boilerplate Cleaner & Web Fetcher

5.1 **HTTP Fetcher (`WebFetcher`):**
  - Built over `cpp-httplib`.
  - Enforce timeout (default 10s), redirect limit (max 5 hops), response size cap (default 2 MB).
  - Set standard User-Agent header; reject non-text Content-Types (`image/*`, `application/octet-stream`, `application/zip`).
5.2 **HTML Cleaner (`HtmlCleaner`):**
  - Streaming or DOM-lite parser in C++20.
  - Strip noise tags completely: `<script>`, `<style>`, `<noscript>`, `<svg>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<form>`, and HTML comments.
  - Convert structural block elements (`<p>`, `<div>`, `<h1>`-`<h6>`, `<li>`, `<tr>`) into newline-separated text.
  - Preserve links as markdown `[text](url)` where text is present.
  - Decode HTML entities (`&amp;`, `&lt;`, `&gt;`, `&quot;`, `&#39;`, `&nbsp;`, and numeric entities).
  - Collapse redundant horizontal whitespace and limit consecutive newlines to two.

### Requirement 6: Persistent Page Cache (`PageCache`)

6.1 **Database Cache Table:**
  - `page_cache (url_hash TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT, clean_text TEXT NOT NULL, content_hash TEXT NOT NULL, fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP, status_code INTEGER NOT NULL)`
6.2 **Cache Invariants:**
  - Keyed by canonical URL hash (SHA256 of lowercase scheme, lowercase host, normalized path/query, stripped fragment).
  - Cache hit returns cleaned text immediately with zero network I/O.
  - Support `bypass_cache = true` to force network re-fetch and update the cache entry.

### Requirement 7: Local Document Chunker & Semantic Search (`DocumentChunker`)

7.1 **Structural Markdown Chunking:**
  - Chunks Markdown files by heading hierarchy (`#`, `##`, `###`).
  - Maintains breadcrumb context for each chunk (e.g. `README.md > Architecture > Storage`).
  - Configurable chunk size target (default ~400-600 tokens) with sliding window overlap (~50 tokens) for long paragraphs.
7.2 **Document Index Table:**
  - `doc_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_path TEXT NOT NULL, chunk_index INTEGER NOT NULL, heading_path TEXT, content TEXT NOT NULL, token_estimate INTEGER NOT NULL, vector BLOB NOT NULL)`
  - FTS5 virtual table `doc_chunks_fts USING fts5(content, heading_path, content='doc_chunks', content_rowid='id')` for BM25 lexical retrieval.
7.3 **Hybrid Retrieval:**
  - Query executes both dense vector cosine similarity (via `HashingEmbedder`) and sparse lexical search (via SQLite FTS5).
  - Combines ranks using Reciprocal Rank Fusion (RRF: `score = 1/(60 + rank_dense) + 1/(60 + rank_sparse)`).
  - Returns top-k distinct chunks with document path, heading path, and matching excerpts.

### Requirement 8: KnowledgeModule (`IAgentModule`) Implementation

8.1 **Module ID:** `get_id() == "KnowledgeModule"`.
8.2 **Exposed Action Schemas:**
  - `search_local_docs`: parameters `{"query": string, "max_results": int (optional, default 5)}`
  - `fetch_and_clean_url`: parameters `{"url": string, "bypass_cache": bool (optional, default false)}`
  - `store_fact`: parameters `{"topic": string, "fact": string}`
  - `recall_experiences`: parameters `{"query": string, "max_results": int (optional, default 3)}`
8.3 **Execution Behavior:**
  - Parameter validation via existing `ModuleBase` schema validation.
  - On failure, returns typed `ActionResult` with specific `error_code` (`invalid_url`, `fetch_failed`, `doc_not_found`, `db_error`).
  - On success, returns structured markdown in `llm_facing_output` and accurate `token_estimate`.
8.4 **Context Condenser Integration:**
  - `export_state_snapshot()`: returns JSON containing recent query history, active cached URL list, and in-memory fact cache summary.
  - `restore_state_snapshot(snapshot)`: restores in-memory caches from JSON.
8.5 **Registry Integration:**
  - Added to `ModuleRegistry::builtin()` so cartridges can load `"KnowledgeModule"`.

### Requirement 9: ContextCondenser EoCC Upgrade & Verification

9.1 **EoCC Integration:** Update `ContextCondenser` to use value-managed compaction (End-of-Context Compaction) based on M5 bake-off results, replacing any leftover mid-sequence KV wipe assumptions.
9.2 **Property-Based Testing:** RapidCheck tests for `SqliteDb`, `HashingEmbedder`, `VectorIndex`, and `HtmlCleaner`.
9.3 **Oracle Parity:** Exact test verifying vector parity against Python `HashingEmbeddingFunction` fixtures and verifying reading from real `Agent-Memory/fact_graph.db`.
9.4 **Sanitizer & Lane Cleanliness:** All 5 build presets (`msvc-release`, `msvc-asan`, `msvc-release-cuda`, `mingw-san`, `linux-san`) configure, compile, and pass with zero warnings, zero sanitizer defects, and clean CI.

