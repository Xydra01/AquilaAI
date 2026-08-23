"""Query cleanup and result-quality hints for research web_search."""
from __future__ import annotations

import re

_DICTIONARY_HOSTS = (
    "dictionary.com",
    "merriam-webster.com",
    "thesaurus.com",
    "cambridge.org",
    "dictionary.cambridge.org",
    "wiktionary.org",
)
_NOISE_HOSTS = (
    "bartleby.com",
    "chegg.com",
    "signup",
    "sign-up",
    "alpinepools.com",
)
_TECHNICAL_HOSTS = (
    "github.com",
    "hub.docker.com",
    "docker.com/r/",
    "doc.",
    "docs.",
)
_TRUSTED_HINTS = (".gov", ".edu", ".nasa", "wikipedia.org", "arxiv.org")
_TECH_QUERY_RE = re.compile(
    r"\b(docker|compose|caldav|carddav|imap|smtp|container|radicale|dovecot|mailpit|cron)\b",
    re.I,
)
_POISON_TOKENS = ("lightweight", "privacy", "security")


def is_dictionary_host(url: str) -> bool:
    lower = (url or "").lower()
    return any(host in lower for host in _DICTIONARY_HOSTS)


def is_noise_host(url: str) -> bool:
    lower = (url or "").lower()
    return any(host in lower for host in _NOISE_HOSTS)


def is_technical_host(url: str) -> bool:
    lower = (url or "").lower()
    return any(host in lower for host in _TECHNICAL_HOSTS)


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

    if _TECH_QUERY_RE.search(lower):
        stripped_poison = False
        for token in _POISON_TOKENS:
            if re.search(rf"\b{re.escape(token)}\b", cleaned, re.I):
                cleaned = re.sub(rf"\b{re.escape(token)}\b", "", cleaned, flags=re.I)
                stripped_poison = True
        if stripped_poison:
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
            note_parts.append("dropped generic token (lightweight/privacy/security)")
        if not re.search(r"\b(docker|container|image)\b", cleaned, re.I):
            cleaned = f"{cleaned} docker container".strip()
            note_parts.append("appended 'docker container'")

    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    if cleaned != original:
        return cleaned, "; ".join(note_parts) if note_parts else "query rewritten"
    return original, None


def low_quality_results_note(results_text: str) -> str | None:
    """Suggest query rewrite when hits are dictionary-heavy without technical sources."""
    text = (results_text or "").lower()
    if not text or "search results for" not in text:
        return None
    has_dict = any(host in text for host in _DICTIONARY_HOSTS)
    has_technical = any(host in text for host in _TECHNICAL_HOSTS)
    has_trusted = any(hint in text for hint in _TRUSTED_HINTS)
    if has_dict and not has_technical and not has_trusted:
        return (
            "⚠️ OS NOTE: Search results look low-quality (dictionary/generic sites). "
            "Rewrite: drop 'lightweight', use concrete product names, or one site filter "
            "e.g. site:github.com dovecot docker OR site:hub.docker.com radicale."
        )
    return None
