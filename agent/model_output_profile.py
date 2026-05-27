"""
Model-specific structured output capabilities (stock aquila, heretic, TurboQuant).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelOutputProfile:
    id: str
    strict_ok: bool = True
    prefill_ok: bool = True
    max_tools_in_schema: int = 24
    prefer_json_object: bool = False
    allow_plain_fallback: bool = True
    retry_shrink_schema: bool = True


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def resolve_model_output_profile(model_name: str | None = None) -> ModelOutputProfile:
    """Pick output profile from OLLAMA_MODEL and env overrides."""
    name = (model_name or os.getenv("OLLAMA_MODEL", "aquila") or "aquila").lower()

    if "heretic" in name:
        base = ModelOutputProfile(
            id="heretic",
            strict_ok=True,
            prefill_ok=True,
            max_tools_in_schema=16,
            prefer_json_object=False,
            allow_plain_fallback=True,
            retry_shrink_schema=True,
        )
    elif "tq" in name or "turboquant" in name:
        base = ModelOutputProfile(
            id="turboquant",
            strict_ok=True,
            prefill_ok=True,
            max_tools_in_schema=14,
            prefer_json_object=False,
            allow_plain_fallback=_env_bool("AQUILA_STRUCTURED_NO_PLAIN", False) is False,
            retry_shrink_schema=True,
        )
    else:
        base = ModelOutputProfile(
            id="aquila",
            strict_ok=True,
            prefill_ok=True,
            max_tools_in_schema=24,
            prefer_json_object=False,
            allow_plain_fallback=True,
            retry_shrink_schema=True,
        )

    strict_ok = _env_bool("AQUILA_STRUCTURED_STRICT", base.strict_ok)
    allow_plain = _env_bool(
        "AQUILA_STRUCTURED_NO_PLAIN", not base.allow_plain_fallback
    )
    allow_plain = not allow_plain

    max_tools = _env_int("AQUILA_SCHEMA_MAX_TOOLS", base.max_tools_in_schema)

    return ModelOutputProfile(
        id=base.id,
        strict_ok=strict_ok,
        prefill_ok=base.prefill_ok,
        max_tools_in_schema=max_tools,
        prefer_json_object=base.prefer_json_object,
        allow_plain_fallback=allow_plain,
        retry_shrink_schema=base.retry_shrink_schema,
    )


def format_attempts_for_profile(
    schema: dict | None,
    profile: ModelOutputProfile,
) -> list[dict | str | None]:
    """Ordered response_format attempts for non-streaming chat."""
    if not schema:
        return [None]
    if not profile.strict_ok:
        attempts: list[dict | str | None] = []
        if profile.prefer_json_object:
            attempts.append("json_object")
        if profile.allow_plain_fallback:
            attempts.append(None)
        return attempts or [None]

    attempts = [schema]
    if profile.prefer_json_object:
        attempts.append("json_object")
    elif profile.retry_shrink_schema:
        from structured_schema import shrink_schema_for_retry

        attempts.append(shrink_schema_for_retry(schema))
    attempts.append("json_object")
    if profile.allow_plain_fallback:
        attempts.append(None)
    return attempts
