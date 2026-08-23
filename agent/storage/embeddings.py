"""Offline-safe embedding helpers for Aquila Chroma collections.

Preference order (``AQUILA_EMBEDDING=auto``):
1. Bundled MiniLM ONNX shipped with Aquila (``runtime/embeddings/…``)
2. Existing user Chroma cache (already downloaded once)
3. Local hashing embedder (always available, no network)

Network download is never performed unless ``AQUILA_ALLOW_EMBEDDING_DOWNLOAD=1``.
"""
from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence, cast

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_MODEL_NAME = "all-MiniLM-L6-v2"
_ONNX_SHA256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"


def user_onnx_model_path() -> Path:
    return (
        Path.home()
        / ".cache"
        / "chroma"
        / "onnx_models"
        / _MODEL_NAME
        / "onnx"
        / "model.onnx"
    )


def onnx_cache_model_path() -> Path:
    """Backward-compatible alias for the user Chroma cache model path."""
    return user_onnx_model_path()


def bundled_onnx_root() -> Path | None:
    """Directory containing ``all-MiniLM-L6-v2/onnx/model.onnx`` if shipped with Aquila."""
    candidates: list[Path] = []
    env = os.getenv("AQUILA_EMBEDDINGS_DIR", "").strip()
    if env:
        candidates.append(Path(env))
    try:
        from agent.aquila_runtime.paths import get_bundled_path, get_install_root

        candidates.append(get_bundled_path("runtime", "embeddings"))
        candidates.append(get_install_root() / "runtime" / "embeddings")
    except Exception:
        pass
    # Dev checkout: packaging cache or staged dist
    try:
        from agent.aquila_runtime.paths import REPO_ROOT

        candidates.append(REPO_ROOT / "packaging" / "cache" / "chroma-onnx")
        candidates.append(REPO_ROOT / "dist" / "Aquila" / "runtime" / "embeddings")
    except Exception:
        pass

    for root in candidates:
        model = root / _MODEL_NAME / "onnx" / "model.onnx"
        if model.is_file():
            return root
    return None


def bundled_onnx_model_path() -> Path | None:
    root = bundled_onnx_root()
    if root is None:
        return None
    path = root / _MODEL_NAME / "onnx" / "model.onnx"
    return path if path.is_file() else None


def onnx_model_ready() -> bool:
    return bundled_onnx_model_path() is not None or user_onnx_model_path().is_file()


def onnx_model_cached() -> bool:
    """True when a local ONNX MiniLM is available without downloading."""
    return onnx_model_ready()


def allow_embedding_download() -> bool:
    return os.getenv("AQUILA_ALLOW_EMBEDDING_DOWNLOAD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def embedding_backend_preference() -> str:
    """``hash`` | ``onnx`` | ``auto`` (default)."""
    raw = os.getenv("AQUILA_EMBEDDING", "auto").strip().lower()
    if raw in ("hash", "hashing", "offline"):
        return "hash"
    if raw in ("onnx", "default", "minilm", "bundled"):
        return "onnx"
    return "auto"


def embedding_collection_tag() -> str:
    """Suffix for Chroma collection names so EF switches do not collide."""
    backend = resolve_embedding_backend()
    return "onnx" if backend == "onnx" else "hash"


def resolve_embedding_backend() -> str:
    pref = embedding_backend_preference()
    if pref == "hash":
        return "hash"
    if pref == "onnx":
        if onnx_model_ready() or allow_embedding_download():
            return "onnx"
        return "hash"
    # auto: bundled or cached ONNX only — never surprise-download
    if onnx_model_ready():
        return "onnx"
    return "hash"


def _onnx_download_path() -> Path:
    """Root Chroma expects: ``…/all-MiniLM-L6-v2`` with child ``onnx/``."""
    bundled = bundled_onnx_root()
    if bundled is not None:
        return bundled / _MODEL_NAME
    return Path.home() / ".cache" / "chroma" / "onnx_models" / _MODEL_NAME


class BundledONNXMiniLM:
    """
    Thin wrapper around Chroma's ONNX MiniLM that never hits the network.

    Points ``DOWNLOAD_PATH`` at Aquila's bundled (or already-cached) assets and
    replaces the download hook with a local existence check.
    """

    def __init__(self, preferred_providers: list[str] | None = None):
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import (
            ONNXMiniLM_L6_V2,
        )

        download_path = _onnx_download_path()
        model_file = download_path / "onnx" / "model.onnx"
        if not model_file.is_file() and not allow_embedding_download():
            raise FileNotFoundError(
                f"Bundled embedding model missing at {model_file}. "
                "Run packaging/fetch-chroma-onnx.ps1 or set "
                "AQUILA_ALLOW_EMBEDDING_DOWNLOAD=1."
            )

        class _LocalONNX(ONNXMiniLM_L6_V2):
            DOWNLOAD_PATH = download_path
            _MODEL_SHA256 = _ONNX_SHA256

            def _download_model_if_not_exists(self) -> None:  # type: ignore[override]
                onnx_dir = os.path.join(str(self.DOWNLOAD_PATH), self.EXTRACTED_FOLDER_NAME)
                required = ("model.onnx", "tokenizer.json")
                missing = [
                    f
                    for f in required
                    if not os.path.isfile(os.path.join(onnx_dir, f))
                ]
                if missing:
                    if allow_embedding_download():
                        return super()._download_model_if_not_exists()
                    raise FileNotFoundError(
                        f"Local ONNX embedding incomplete under {onnx_dir}: "
                        f"missing {', '.join(missing)}"
                    )

        self._impl = _LocalONNX(preferred_providers=preferred_providers)

    @staticmethod
    def name() -> str:
        return "aquila_onnx_minilm"

    @staticmethod
    def is_legacy() -> bool:
        return False

    def get_config(self) -> dict[str, Any]:
        return {"model": _MODEL_NAME, "source": "bundled"}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "BundledONNXMiniLM":
        return BundledONNXMiniLM()

    @staticmethod
    def validate_config(config: dict[str, Any]) -> None:
        return None

    @staticmethod
    def validate_config_update(old: dict[str, Any], new: dict[str, Any]) -> None:
        return None

    def default_space(self):  # noqa: ANN201
        return self._impl.default_space()

    def supported_spaces(self):  # noqa: ANN201
        return self._impl.supported_spaces()

    def __call__(self, input: Sequence[str]):
        return self._impl(input)

    def embed_query(self, input: Sequence[str]):
        return self._impl.embed_query(input)

    def embed_documents(self, input: Sequence[str]):
        if hasattr(self._impl, "embed_documents"):
            return self._impl.embed_documents(input)
        return self._impl(input)

    def embed_with_retries(self, input: Sequence[str], **kwargs):
        if hasattr(self._impl, "embed_with_retries"):
            return self._impl.embed_with_retries(input, **kwargs)
        return self._impl(input)


class HashingEmbeddingFunction:
    """Deterministic bag-of-tokens + char-ngram hashing embedder (fully offline)."""

    def __init__(self, dim: int = 384):
        self.dim = max(32, int(dim))

    @staticmethod
    def name() -> str:
        return "aquila_hash"

    @staticmethod
    def is_legacy() -> bool:
        return False

    def get_config(self) -> dict[str, Any]:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "HashingEmbeddingFunction":
        return HashingEmbeddingFunction(dim=int(config.get("dim", 384)))

    @staticmethod
    def validate_config(config: dict[str, Any]) -> None:
        return None

    @staticmethod
    def validate_config_update(
        old: dict[str, Any], new: dict[str, Any]
    ) -> None:
        return None

    def default_space(self):  # noqa: ANN201
        from chromadb.api.types import Space

        return Space.COSINE

    def supported_spaces(self):  # noqa: ANN201
        from chromadb.api.types import Space

        return [Space.COSINE, Space.L2, Space.IP]

    def _tokens(self, text: str) -> list[str]:
        raw = (text or "").lower().replace("_", " ").replace("-", " ")
        words = _TOKEN_RE.findall(raw)
        out: list[str] = []
        for w in words:
            out.append(w)
            if len(w) >= 4:
                for n in (3, 4):
                    for i in range(0, len(w) - n + 1):
                        out.append(f"ng{n}:{w[i : i + n]}")
        for a, b in zip(words, words[1:]):
            out.append(f"bg:{a}_{b}")
        return out

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for tok in self._tokens(text):
            digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def __call__(self, input: Sequence[str]):
        from chromadb.api.types import Embeddings

        return cast(Embeddings, [self._embed_one(t) for t in input])

    def embed_query(self, input: Sequence[str]):
        return self(input)

    def embed_documents(self, input: Sequence[str]):
        return self(input)

    def embed_with_retries(self, input: Sequence[str], **_kwargs):
        return self(input)


@lru_cache(maxsize=1)
def get_aquila_embedding_function():
    """
    Prefer bundled/cached MiniLM ONNX; fall back to hashing. Never downloads
    unless AQUILA_ALLOW_EMBEDDING_DOWNLOAD=1.
    """
    backend = resolve_embedding_backend()
    if backend == "onnx":
        try:
            return BundledONNXMiniLM()
        except Exception:
            if allow_embedding_download():
                try:
                    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

                    return ONNXMiniLM_L6_V2()
                except Exception:
                    pass
    return HashingEmbeddingFunction()


def reset_embedding_cache() -> None:
    get_aquila_embedding_function.cache_clear()
