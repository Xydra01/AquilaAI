"""Heuristic planning for Chat Mode light web research (no extra LLM call)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .web_search_query import clean_research_query

_URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"\'\)\]]+", re.I)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\)]+)\)", re.I)

_FILLER_PREFIX_RE = re.compile(
    r"^(please|can you|could you|i want you to|i need you to|help me|tell me)\s+",
    re.I,
)
_LINK_ONLY_HINTS = re.compile(
    r"\b(read|summarize|summary|check|look at|review|this link|this url|what does this say)\b",
    re.I,
)


@dataclass(frozen=True)
class LightResearchPlan:
    user_urls: tuple[str, ...] = ()
    search_queries: tuple[str, ...] = ()
    skip_search: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


def extract_urls_from_text(text: str, *, max_urls: int = 8) -> list[str]:
    """Pull http(s) URLs from plain text and markdown [label](url) links."""
    seen: set[str] = set()
    out: list[str] = []

    def _add(raw: str) -> None:
        url = (raw or "").strip().rstrip(".,;:!?)\"]'")
        if url and url not in seen:
            seen.add(url)
            out.append(url)

    for match in _MD_LINK_RE.finditer(text or ""):
        _add(match.group(1))
        if len(out) >= max_urls:
            return out[:max_urls]

    for match in _URL_IN_TEXT_RE.finditer(text or ""):
        _add(match.group(0))
        if len(out) >= max_urls:
            break

    return out[:max_urls]


def _strip_urls(text: str) -> str:
    without_md = _MD_LINK_RE.sub(" ", text or "")
    return _URL_IN_TEXT_RE.sub(" ", without_md).strip()


def _compact_query(text: str, *, max_words: int) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = _FILLER_PREFIX_RE.sub("", cleaned).strip()
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words])
    return cleaned.strip()


def _looks_like_research_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "?" in t:
        return True
    return bool(
        re.search(
            r"\b(what|who|when|where|why|how|compare|explain|find|search|latest|current)\b",
            t,
            re.I,
        )
    )


def _extract_questions(body: str) -> list[str]:
    """Pull question sentences; tolerate decimals like 3.12 in the text."""
    if "?" not in body:
        return []
    questions: list[str] = []
    idx = 0
    while True:
        qpos = body.find("?", idx)
        if qpos < 0:
            break
        segment = body[idx:qpos]
        start = 0
        scan_from = 0
        if len(segment) > 160:
            scan_from = len(segment) - 160
        for m in re.finditer(r"(?:^|[.!?]\s+|\n)", segment[scan_from:]):
            start = scan_from + m.end()
        q = body[start : qpos + 1].strip()
        if len(q) >= 8:
            questions.append(q)
        idx = qpos + 1
    return questions


_WEATHER_RE = re.compile(
    r"\b(weather|forecast|temperature|rain|snow|humidity|wind)\b",
    re.I,
)
_PLACE_HINT_RE = re.compile(
    r"\b(?:in|for|near)\s+([A-Za-z][A-Za-z.'-]{1,40}(?:,\s*[A-Z]{2})?)\b"
)


def _weather_focused_queries(body: str, *, max_words: int) -> list[str]:
    """Specialize weather questions so SearXNG hits forecasts, not dictionaries."""
    if not _WEATHER_RE.search(body):
        return []
    place = ""
    m = _PLACE_HINT_RE.search(body)
    if m:
        place = m.group(1).strip(" .,?!")
    horizon = "this week" if re.search(r"\b(week|weekly|7[- ]?day)\b", body, re.I) else "today"
    if place:
        q1 = _compact_query(f"{place} weather forecast {horizon}", max_words=max_words)
        extras = [
            q1,
            _compact_query(f"{place} weather forecast weather.gov", max_words=max_words),
            _compact_query(f"{place} 7 day forecast", max_words=max_words),
        ]
    else:
        extras = [_compact_query(f"weather forecast {horizon}", max_words=max_words)]
    return extras


def derive_light_search_queries(
    user_input: str,
    *,
    max_queries: int = 2,
    max_words: int = 18,
) -> list[str]:
    """
    Build 1–max_queries focused SearXNG queries from a chat message.
    Long prompts: prefer explicit questions and quoted phrases over the full blob.
    """
    body = _strip_urls(user_input)
    body = re.sub(r"\s+", " ", body).strip()
    if not body:
        return []

    max_queries = max(1, max_queries)
    candidates: list[str] = []

    # Domain-specialized first so questions like "what does the weather look like"
    # do not collapse into dictionary-bait single common nouns.
    candidates.extend(_weather_focused_queries(body, max_words=max_words))

    for q in _extract_questions(body):
        candidates.append(_compact_query(q, max_words=max_words))

    for match in re.finditer(r'"([^"]{8,140})"|\'([^\']{8,140})\'', body):
        phrase = (match.group(1) or match.group(2) or "").strip()
        if phrase:
            candidates.append(_compact_query(phrase, max_words=max_words))

    words = body.split()
    if not candidates:
        if len(words) > 45:
            sentences = re.split(r"(?<=[.!?])\s+", body)
            tail = " ".join(sentences[-2:]).strip()
            candidates.append(_compact_query(tail or body, max_words=max_words))
        else:
            candidates.append(_compact_query(body, max_words=max_words))

    seen: set[str] = set()
    queries: list[str] = []
    for raw in candidates:
        cleaned, note = clean_research_query(raw)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        # Drop ultra-short queries that tend to hit dictionary results.
        if len(cleaned.split()) < 2 and not cleaned.startswith("http"):
            continue
        seen.add(key)
        queries.append(cleaned)
        if len(queries) >= max_queries:
            break

    return queries


def plan_light_research(
    user_input: str,
    *,
    max_search_queries: int = 2,
    max_query_words: int = 18,
    max_user_urls: int = 3,
) -> LightResearchPlan:
    """Decide whether to search, which queries to run, and which user URLs to fetch."""
    text = (user_input or "").strip()
    urls = tuple(extract_urls_from_text(text, max_urls=max_user_urls))
    remainder = _strip_urls(text)
    remainder = re.sub(r"\s+", " ", remainder).strip()
    notes: list[str] = []

    link_only = bool(urls) and (
        len(remainder.split()) < 8
        or (_LINK_ONLY_HINTS.search(remainder) and len(remainder.split()) < 20)
    )
    skip_search = link_only and not _looks_like_research_question(remainder)

    if skip_search:
        notes.append("User message is link-first — reading pasted URL(s) without web search.")
        search_queries: tuple[str, ...] = ()
    else:
        derived = derive_light_search_queries(
            text,
            max_queries=max_search_queries,
            max_words=max_query_words,
        )
        search_queries = tuple(derived)
        if derived and derived[0] != remainder[:120]:
            notes.append(f"Search query derived from message: {derived[0]!r}")
        if len(derived) > 1:
            notes.append(f"Additional search: {derived[1]!r}")

    if urls and not skip_search:
        notes.append(f"Also reading {len(urls)} URL(s) from the user message.")

    return LightResearchPlan(
        user_urls=urls,
        search_queries=search_queries,
        skip_search=skip_search,
        notes=tuple(notes),
    )
