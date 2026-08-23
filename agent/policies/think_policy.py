"""Thinking (Qwen native `think`) policy for Aquila surfaces."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _env_surfaces() -> frozenset[str]:
    raw = os.getenv(
        "AQUILA_THINK_SURFACES",
        "chat,character,learn,act,explore,plan,reflect",
    ).strip()
    if not raw:
        return frozenset()
    return frozenset(s.strip().lower() for s in raw.split(",") if s.strip())


@dataclass(frozen=True)
class ThinkingPolicy:
    enabled: bool
    think: bool | None  # None = omit from payload
    legacy_xml_strip: bool
    surface: str


def resolve_thinking_policy(
    *,
    surface: str = "chat",
    model_name: str | None = None,
    has_format_schema: bool = False,
    force_disabled: bool = False,
) -> ThinkingPolicy:
    """
    Decide whether to send `think: true/false` on native /api/chat.

    When master switch is off, sends think=false explicitly.
    Structured JSON schema turns disable native thinking (JSON must land in content).
    """
    surface_key = (surface or "chat").strip().lower()
    master = _env_bool("AQUILA_ENABLE_THINK", True)
    legacy_strip = _env_bool("AQUILA_THINK_LEGACY_XML", True)
    allowed = surface_key in _env_surfaces()

    if force_disabled or not master or not allowed or has_format_schema:
        return ThinkingPolicy(
            enabled=False,
            think=False,
            legacy_xml_strip=legacy_strip,
            surface=surface_key,
        )

    name = (model_name or os.getenv("OLLAMA_MODEL", "") or "").lower()
    # Do NOT match bare "aquila" — aquila_NSFW / other GGUF tags are often Llama-family
    # and return HTTP 400: "does not support thinking".
    _no_think = (
        "nsfw",
        "hermes",
        "evil-reasoning",
        "dark-planet",
        "llama3",
        "llama3.1",
        "l3.1",
        "mistral",
        "mixtral",
    )
    if any(token in name for token in _no_think):
        thinking_model = False
    elif any(
        token in name
        for token in (
            "qwen",
            "qwopus",
            "deepseek",
            "r1",
            "gpt-oss",
            "heretic",
            "tq",
            "turboquant",
        )
    ):
        thinking_model = True
    elif name.startswith("aquila-lite"):
        thinking_model = False
    elif name.startswith("aquila"):
        # Stock Modelfile (FROM qwen3.5:9b) and context variants (e.g., aquila-96k)
        thinking_model = True
    else:
        thinking_model = False

    if not thinking_model:
        return ThinkingPolicy(
            enabled=False,
            think=False,
            legacy_xml_strip=legacy_strip,
            surface=surface_key,
        )

    return ThinkingPolicy(
        enabled=True,
        think=True,
        legacy_xml_strip=legacy_strip,
        surface=surface_key,
    )
