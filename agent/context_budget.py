"""Context window detection and tiered truncation limits for Aquila OS."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

ContextTier = Literal["compact", "standard", "extended", "max"]

_MODEL_CTX_HINTS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"aquila-tq-96k|96k", re.I), 98304),
    (re.compile(r"aquila-tq-64k|64k", re.I), 65536),
    (re.compile(r"aquila-tq-32k|32k", re.I), 32768),
    (re.compile(r"aquila", re.I), 32768),
]

_TIER_ORDER: tuple[ContextTier, ...] = ("compact", "standard", "extended", "max")
_TIER_BY_NAME: dict[str, ContextTier] = {
    "compact": "compact",
    "standard": "standard",
    "extended": "extended",
    "max": "max",
}

_runtime_profile: "ContextProfile | None" = None


@dataclass(frozen=True)
class ContextProfile:
    num_ctx: int
    tier: ContextTier
    auto_scrape_urls: int
    scrape_char_cap: int
    scratchpad_bytes: int
    read_file_preview_chars: int
    tree_char_cap: int

    @property
    def auto_scrape_enabled(self) -> bool:
        return self.auto_scrape_urls > 0 and os.getenv("AQUILA_AUTO_SCRAPE", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )


def _infer_num_ctx_from_model(model_name: str) -> int:
    for pattern, ctx in _MODEL_CTX_HINTS:
        if pattern.search(model_name or ""):
            return ctx
    return 32768


def _tier_from_num_ctx(num_ctx: int) -> ContextTier:
    if num_ctx <= 16_384:
        return "compact"
    if num_ctx <= 40_960:
        return "standard"
    if num_ctx <= 73_728:
        return "extended"
    return "max"


def _limits_for_tier(tier: ContextTier) -> tuple[int, int, int, int, int]:
    if tier == "compact":
        return 1, 8_000, 8 * 1024, 1_500, 5_000
    if tier == "standard":
        return 1, 15_000, 12 * 1024, 3_000, 5_000
    if tier == "extended":
        return 2, 28_000, 24 * 1024, 6_000, 8_000
    return 3, 40_000, 48 * 1024, 10_000, 12_000


def resolve_context_profile(
    model_name: str | None = None,
    num_ctx_override: int | None = None,
) -> ContextProfile:
    forced_tier = os.getenv("AQUILA_CONTEXT_TIER", "").strip().lower()
    if num_ctx_override is not None and num_ctx_override > 0:
        num_ctx = num_ctx_override
    else:
        env_ctx = os.getenv("OLLAMA_NUM_CTX", "").strip()
        if env_ctx.isdigit() and int(env_ctx) > 0:
            num_ctx = int(env_ctx)
        else:
            num_ctx = _infer_num_ctx_from_model(model_name or os.getenv("OLLAMA_MODEL", "aquila"))

    tier = _TIER_BY_NAME.get(forced_tier) if forced_tier else _tier_from_num_ctx(num_ctx)
    scrape_urls, scrape_cap, scratchpad, read_preview, tree_cap = _limits_for_tier(tier)
    if tier == "compact" and os.getenv("AQUILA_AUTO_SCRAPE", "1").strip().lower() in ("0", "false", "no", "off"):
        scrape_urls = 0

    return ContextProfile(
        num_ctx=num_ctx,
        tier=tier,
        auto_scrape_urls=scrape_urls,
        scrape_char_cap=scrape_cap,
        scratchpad_bytes=scratchpad,
        read_file_preview_chars=read_preview,
        tree_char_cap=tree_cap,
    )


def set_runtime_context(model_name: str | None = None, num_ctx_override: int | None = None) -> ContextProfile:
    global _runtime_profile
    _runtime_profile = resolve_context_profile(model_name, num_ctx_override)
    return _runtime_profile


def get_context_profile() -> ContextProfile:
    global _runtime_profile
    if _runtime_profile is None:
        _runtime_profile = resolve_context_profile()
    return _runtime_profile


def reset_runtime_context() -> None:
    global _runtime_profile
    _runtime_profile = None
