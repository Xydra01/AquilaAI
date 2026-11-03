"""Capability argument shape hints for prompts (Tier B)."""
from __future__ import annotations

from agent.capabilities.registry import get_capability


def format_capability_argument_hints(
    cap_ids: list[str] | frozenset[str] | set[str],
    *,
    max_caps: int = 6,
    prioritize: str | None = None,
) -> str:
    """One-line-per-cap summary of required and optional argument fields."""
    ids = [str(x).strip() for x in cap_ids if str(x).strip()]
    if prioritize and prioritize in ids:
        ids = [prioritize] + [item for item in ids if item != prioritize]
    lines: list[str] = []
    for cap_id in ids[:max_caps]:
        spec = get_capability(cap_id)
        if spec is None:
            continue
        required: list[str] = []
        optional: list[str] = []
        for name, field in spec.input_model.model_fields.items():
            if field.is_required():
                required.append(name)
            else:
                optional.append(name)
        parts: list[str] = []
        if required:
            parts.append("required " + ", ".join(required))
        if optional:
            parts.append("optional " + ", ".join(optional[:5]))
        if parts:
            lines.append(f"- `{cap_id}`: {'; '.join(parts)}")
    return "\n".join(lines)
