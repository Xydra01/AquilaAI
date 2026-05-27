"""Semantic indexing for Learn Mode archives and course sources."""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from learn_registry import (
    archive_sources_dir,
    course_sources_dir,
    get_archive,
    save_archive,
)
from workspace_paths import get_vector_db_path

CHUNK_CHARS = 2400
CHUNK_OVERLAP = 200
DEFAULT_SEARCH_TOP_K = 5
DEFAULT_RETRIEVAL_MAX_CHARS = 12_000


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


@lru_cache(maxsize=1)
def _get_chroma_client():
    import chromadb

    return chromadb.PersistentClient(path=str(get_vector_db_path()))


@lru_cache(maxsize=1)
def _get_embedding_function():
    from chromadb.utils import embedding_functions

    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


def _collection_name(instance_id: str, scope: str, entity_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in f"{instance_id}_{entity_id}")
    return f"learn_{scope}_{safe}"[:63]


def _chunk_text(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def _read_source_file(path: Path) -> str:
    try:
        from file_parser import extract_indexable_text

        return extract_indexable_text(path)
    except ImportError:
        pass
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _get_collection(name: str):
    return _get_chroma_client().get_or_create_collection(
        name=name,
        embedding_function=_get_embedding_function(),
    )


def index_directory(
    instance_id: str,
    sources_root: Path,
    scope: str,
    entity_id: str,
) -> tuple[int, int, list[str]]:
    """Index all files under sources_root. Returns (file_count, chunk_count, warnings)."""
    name = _collection_name(instance_id, scope, entity_id)
    client = _get_chroma_client()
    try:
        client.delete_collection(name)
    except Exception:
        pass
    collection = _get_collection(name)

    if not sources_root.is_dir():
        return 0, 0, []

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    file_count = 0
    warnings: list[str] = []
    skipped_system = (
        "[system:",
        "could not parse",
        "no extractable text",
        "unsupported or binary",
    )

    for path in sorted(sources_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(sources_root).as_posix()
        text = _read_source_file(path)
        if not text.strip():
            warnings.append(f"{rel}: empty or unreadable")
            continue
        lower = text.lower()
        if any(marker in lower for marker in skipped_system):
            warnings.append(f"{rel}: parser could not extract usable text")
            continue
        file_count += 1
        for i, chunk in enumerate(_chunk_text(text)):
            cid = hashlib.sha256(f"{rel}:{i}:{chunk[:80]}".encode()).hexdigest()[:24]
            ids.append(cid)
            documents.append(chunk)
            metadatas.append({"source": rel, "chunk_index": str(i)})

    if ids:
        batch = 64
        for i in range(0, len(ids), batch):
            collection.add(
                ids=ids[i : i + batch],
                documents=documents[i : i + batch],
                metadatas=metadatas[i : i + batch],
            )
    return file_count, len(ids), warnings


def search_index(
    instance_id: str,
    scope: str,
    entity_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    if not (query or "").strip():
        return []
    name = _collection_name(instance_id, scope, entity_id)
    try:
        collection = _get_collection(name)
        try:
            if collection.count() == 0:
                return []
        except Exception:
            pass
        cap = min(top_k, 12)
        results = collection.query(query_texts=[query.strip()], n_results=cap)
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        out = []
        for doc, meta in zip(docs, metas):
            if doc:
                out.append({"text": doc, "source": (meta or {}).get("source", "?")})
        return out
    except Exception:
        return []


def format_retrieval_block(
    chunks: list[dict],
    label: str = "SOURCES",
    *,
    max_chars: int | None = None,
) -> str:
    if not chunks:
        return ""
    limit = max_chars if max_chars is not None else _env_int(
        "AQUILA_LEARN_RETRIEVAL_MAX_CHARS", DEFAULT_RETRIEVAL_MAX_CHARS
    )
    parts = [f"\n\n--- {label} (retrieved) ---"]
    used = 0
    included = 0
    for i, c in enumerate(chunks, 1):
        src = c.get("source", "?")
        text = (c.get("text") or "").strip()
        if not text:
            continue
        if used + len(text) > limit:
            remain = limit - used
            if remain > 200:
                text = text[:remain] + "\n... [passage truncated]"
                parts.append(f"\n[{i}] ({src})\n{text}")
                included += 1
            break
        parts.append(f"\n[{i}] ({src})\n{text}")
        used += len(text)
        included += 1
    if included < len(chunks):
        parts.append(
            f"\n(showing {included} of {len(chunks)} passages; "
            f"capped at {limit} chars for speed)"
        )
    parts.append(f"\n--- END {label} ---\n")
    return "".join(parts)


def estimate_chars_indexed(chunk_count: int) -> int:
    """Rough character count represented by chunks (for UI messaging)."""
    step = max(1, CHUNK_CHARS - CHUNK_OVERLAP)
    return chunk_count * step


def index_archive(instance_id: str, archive_id: str) -> str:
    root = archive_sources_dir(instance_id, archive_id)
    on_disk = (
        len([p for p in root.rglob("*") if p.is_file()]) if root.is_dir() else 0
    )
    files, chunks, warnings = index_directory(instance_id, root, "archive", archive_id)
    archive = get_archive(instance_id, archive_id)
    if archive:
        archive.source_count = on_disk or files
        archive.chunk_count = chunks
        archive.index_ready = chunks > 0
        save_archive(instance_id, archive)
    if chunks == 0 and on_disk > 0:
        warn = "; ".join(warnings[:5]) if warnings else "no extractable text"
        return (
            f"⚠️ Indexed 0 chunks from {on_disk} file(s) on disk. "
            f"Check PDF/DOCX parsing. Details: {warn}"
        )
    if warnings and chunks > 0:
        return (
            f"✅ Indexed {files} file(s), {chunks} chunk(s). "
            f"Skipped: {'; '.join(warnings[:3])}"
        )
    approx = estimate_chars_indexed(chunks)
    return (
        f"✅ Indexed {files} file(s), {chunks} chunk(s) "
        f"(~{approx // 1000}k chars) for archive '{archive_id}'."
    )


def search_archive(instance_id: str, archive_id: str, query: str, top_k: int = 5) -> str:
    hits = search_index(instance_id, "archive", archive_id, query, top_k=top_k)
    if not hits:
        return "No indexed passages found. Run index_archive_sources first."
    return format_retrieval_block(hits, "ARCHIVE SOURCES")


def index_course_sources(instance_id: str, course_id: str) -> str:
    root = course_sources_dir(instance_id, course_id)
    files, chunks, _warnings = index_directory(instance_id, root, "course", course_id)
    return f"✅ Indexed {files} course source file(s), {chunks} chunk(s)."


def search_course_sources(
    instance_id: str, course_id: str, query: str, top_k: int = 5
) -> str:
    hits = search_index(instance_id, "course", course_id, query, top_k=top_k)
    return format_retrieval_block(hits, "COURSE SOURCES")
