"""Offline embedding backend must not download models by default."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_resolve_embedding_defaults_to_hash_without_cache(monkeypatch):
    from agent.storage import embeddings as emb

    emb.reset_embedding_cache()
    monkeypatch.setenv("AQUILA_EMBEDDING", "auto")
    monkeypatch.delenv("AQUILA_ALLOW_EMBEDDING_DOWNLOAD", raising=False)
    monkeypatch.setattr(emb, "bundled_onnx_model_path", lambda: None)
    monkeypatch.setattr(emb, "user_onnx_model_path", lambda: type("P", (), {"is_file": lambda self: False})())
    monkeypatch.setattr(emb, "onnx_model_ready", lambda: False)
    assert emb.resolve_embedding_backend() == "hash"
    ef = emb.get_aquila_embedding_function()
    assert ef.name() == "aquila_hash"


def test_auto_prefers_bundled_onnx(monkeypatch, tmp_path):
    from agent.storage import embeddings as emb

    emb.reset_embedding_cache()
    model_dir = tmp_path / "all-MiniLM-L6-v2" / "onnx"
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"fake")
    (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("AQUILA_EMBEDDING", "auto")
    monkeypatch.setenv("AQUILA_EMBEDDINGS_DIR", str(tmp_path))
    monkeypatch.delenv("AQUILA_ALLOW_EMBEDDING_DOWNLOAD", raising=False)
    emb.reset_embedding_cache()
    assert emb.bundled_onnx_root() == tmp_path
    assert emb.resolve_embedding_backend() == "onnx"


def test_hash_embedding_ranks_related_tools():
    from agent.storage.embeddings import HashingEmbeddingFunction
    import numpy as np

    ef = HashingEmbeddingFunction()
    docs = [
        "Tool Name: web_search. Description: Search the internet for pages.",
        "Tool Name: write_file. Description: Write text content to a disk path.",
    ]
    q = ef(["look up information online"])[0]
    a = ef([docs[0]])[0]
    b = ef([docs[1]])[0]
    sim_a = float(np.dot(q, a))
    sim_b = float(np.dot(q, b))
    assert sim_a > sim_b


def test_index_tools_does_not_call_network_download(tmp_path, monkeypatch):
    from agent.storage import DualMemorySystem
    from agent.storage import embeddings as emb

    emb.reset_embedding_cache()
    monkeypatch.setenv("AQUILA_EMBEDDING", "hash")
    monkeypatch.delenv("AQUILA_ALLOW_EMBEDDING_DOWNLOAD", raising=False)

    download = patch(
        "chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2.ONNXMiniLM_L6_V2._download",
        side_effect=AssertionError("must not download"),
    )
    with download:
        mem = DualMemorySystem(
            storage_dir=str(tmp_path / "mem"),
            chroma_path=str(tmp_path / "chroma"),
            instance_id="default",
        )
        mem.index_tools(
            {
                "web_search": {"description": "Search the web"},
                "write_file": {"description": "Write a file"},
            }
        )
        assert mem._tools_indexed is True
        routed = mem.route_tools("search the web for news", max_tools=1)
        assert routed[0] == "web_search"


def test_keyword_fallback_when_index_times_out(tmp_path, monkeypatch):
    from agent.storage import DualMemorySystem
    from agent.storage import embeddings as emb

    emb.reset_embedding_cache()
    monkeypatch.setenv("AQUILA_EMBEDDING", "hash")
    monkeypatch.setenv("AQUILA_TOOL_INDEX_TIMEOUT_SEC", "0.01")

    mem = DualMemorySystem(
        storage_dir=str(tmp_path / "mem"),
        chroma_path=str(tmp_path / "chroma"),
        instance_id="default",
    )
    assert mem._ensure_chroma()

    def slow_upsert(*_a, **_k):
        import time

        time.sleep(2)

    monkeypatch.setattr(mem.tool_collection, "upsert", slow_upsert)
    mem.index_tools(
        {
            "web_search": {"description": "Search the web"},
            "write_file": {"description": "Write a file"},
        }
    )
    assert mem._tools_indexed is False
    assert mem.route_tools("search online", max_tools=1)[0] == "web_search"
