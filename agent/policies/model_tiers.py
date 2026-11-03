"""Model tier registry for Code Mode reliability gating."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from agent.storage.runtime_settings import active_ollama_config, model_tag_base, model_tag_matches

ModelTier = Literal["capable", "degraded", "unknown"]
CodeSurface = Literal["gui", "cli", "harness"]

# Harness-verified models (expand after eval promotion).
CODE_CAPABLE_MODELS = frozenset({
    "aquila",
    "aquila:latest",
})

CODE_DEGRADED_MODELS = frozenset({
    "aquila-qwopus-standard",
    "aquila-qwopus-standard:latest",
    "aquila_qwopus",
    "aquila-qwopus",
})


def _gate_enabled() -> bool:
    return os.getenv("AQUILA_CODE_MODEL_GATE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _allow_degraded_override() -> bool:
    return os.getenv("AQUILA_CODE_ALLOW_DEGRADED_MODEL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def normalize_model_tag(tag: str) -> str:
    """Lowercase base name without :latest suffix."""
    base = model_tag_base((tag or "").strip())
    return base.lower()


def get_active_model_id() -> str:
    return str(active_ollama_config().get("model") or os.getenv("OLLAMA_MODEL", "aquila")).strip()


def _matches_set(model_id: str, names: frozenset[str]) -> bool:
    for name in names:
        if model_tag_matches(name, model_id):
            return True
    return normalize_model_tag(model_id) in {normalize_model_tag(n) for n in names}


def code_model_tier(model_id: str | None = None) -> ModelTier:
    mid = (model_id or get_active_model_id()).strip()
    if not mid:
        return "unknown"
    if _matches_set(mid, CODE_CAPABLE_MODELS):
        return "capable"
    if _matches_set(mid, CODE_DEGRADED_MODELS):
        return "degraded"
    return "unknown"


@dataclass(frozen=True)
class CodeModelCheckResult:
    ok: bool
    blocked: bool
    tier: ModelTier
    model_id: str
    message: str = ""
    warn: bool = False


def _recommendation_message(model_id: str) -> str:
    return (
        f"Model `{model_id}` is not recommended for Code Mode. "
        "Set OLLAMA_MODEL=aquila:latest (or another capable model) for reliable coding."
    )


def check_code_model(
    *,
    surface: CodeSurface = "cli",
    strict: bool = False,
    model_id: str | None = None,
) -> CodeModelCheckResult:
    """Check whether the active model may run Code Mode."""
    mid = (model_id or get_active_model_id()).strip()
    tier = code_model_tier(mid)

    if not _gate_enabled():
        return CodeModelCheckResult(ok=True, blocked=False, tier=tier, model_id=mid)

    if tier == "capable":
        return CodeModelCheckResult(ok=True, blocked=False, tier=tier, model_id=mid)

    if _allow_degraded_override():
        msg = _recommendation_message(mid) if tier == "degraded" else ""
        return CodeModelCheckResult(
            ok=True,
            blocked=False,
            tier=tier,
            model_id=mid,
            message=msg,
            warn=bool(msg),
        )

    if tier == "degraded":
        msg = _recommendation_message(mid)
        if surface == "gui":
            return CodeModelCheckResult(
                ok=False,
                blocked=True,
                tier=tier,
                model_id=mid,
                message=f"🛑 Code Mode blocked: {msg}",
            )
        if strict:
            return CodeModelCheckResult(
                ok=False,
                blocked=True,
                tier=tier,
                model_id=mid,
                message=f"Degraded model `{mid}` not allowed (use --allow-degraded or capable model).",
            )
        return CodeModelCheckResult(
            ok=True,
            blocked=False,
            tier=tier,
            model_id=mid,
            message=f"⚠️ Warning: {msg}",
            warn=True,
        )

    # unknown tier: warn but allow
    return CodeModelCheckResult(
        ok=True,
        blocked=False,
        tier=tier,
        model_id=mid,
        message=(
            f"⚠️ Model `{mid}` is not in the code-capable registry. "
            "Results may be unreliable."
        ),
        warn=True,
    )
