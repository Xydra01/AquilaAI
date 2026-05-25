"""Query cleanup and result-quality hints for research web_search."""
from __future__ import annotations

import re

_DICTIONARY_HOSTS = ("dictionary.com", "merriam-webster.com", "thesaurus.com")
_TRUSTED_HINTS = (".gov", ".edu", ".nasa", "wikipedia.org", "arxiv.org")


def clean_research_query(query: str) -> tuple[str, str | None]:
    """
    Return (cleaned_query, change_note).
    Rewrites tokens that commonly poison SearXNG for scientific catalog queries.
    """
    original = (query or "").strip()
    if not original:
        return original, None

    cleaned = original
    note_parts: list[str] = []

    lower = cleaned.lower()
    if lower.startswith("confirmed ") and re.search(
        r"\b(exoplanet|planet|catalog|archive|earth|habitable|nasa)\b",
        lower,
    ):
        cleaned = re.sub(
            r"^confirmed\s+",
            "catalog of ",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )
        note_parts.append("leading 'confirmed' → 'catalog of'")

    if re.search(r"\ball\s+known\b", lower) and not re.search(
        r"\b(top|sample|representative|list of)\b", lower
    ):
        cleaned = re.sub(
            r"\ball\s+known\b",
            "representative sample of known",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )
        note_parts.append("'all known' → 'representative sample of known'")

    if cleaned != original:
        return cleaned, "; ".join(note_parts)
    return original, None


def low_quality_results_note(results_text: str) -> str | None:
    """Suggest query rewrite when hits are dictionary-heavy without trusted domains."""
    text = (results_text or "").lower()
    if not text or "search results for" not in text:
        return None
    has_dict = any(host in text for host in _DICTIONARY_HOSTS)
    has_trusted = any(hint in text for hint in _TRUSTED_HINTS)
    if has_dict and not has_trusted:
        return (
            "⚠️ OS NOTE: Search results look low-quality (dictionary sites). "
            "Rewrite the query: drop 'confirmed', use 'NASA exoplanet archive Earth-like "
            "habitable zone catalog', or site:nasa.gov."
        )
    return None
