"""Heuristic paywall / thin-page detection for web fetches (no extra LLM call)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

PageQuality = Literal["full", "thin", "paywall", "error"]

_PAYWALL_PHRASES = (
    "preview of subscription",
    "log in via an institution",
    "log in via institution",
    "subscribe to read",
    "subscription content",
    "institutional access",
    "access this chapter",
    "buy ebook",
    "buy e-book",
    "purchase access",
    "sign in to access",
    "create an account to read",
    "this content is available to subscribers",
    "you have full access through",
    "check access",
)

_PAYWALL_DOMAINS = (
    "springer.com",
    "link.springer.com",
    "sciencedirect.com",
    "elsevier.com",
    "tandfonline.com",
    "wiley.com",
    "onlinelibrary.wiley.com",
    "jstor.org",
    "nature.com",
    "academic.oup.com",
    "wayf.springernature.com",
)

_THIN_MIN_SUBSTANTIVE_CHARS = 400
_EXCERPT_MAX = 800


@dataclass(frozen=True)
class PageAnalysis:
    quality: PageQuality
    usable_excerpt: str
    log_summary: str
    paywall_score: int = 0
    substantive_chars: int = 0

    def is_usable_for_context(self) -> bool:
        return self.quality in ("full", "thin")


def _substantive_text(markdown: str) -> str:
    """Strip markdown noise and collapse whitespace for length heuristics."""
    text = markdown or ""
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#*_>`|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _count_phrase_hits(lower: str, phrases: tuple[str, ...]) -> int:
    return sum(1 for p in phrases if p in lower)


def analyze_fetched_page(
    url: str,
    markdown: str,
    *,
    raw_html: str | None = None,
) -> PageAnalysis:
    """
    Classify fetched page content before injecting into agent context.

    Returns quality, a short excerpt for paywall/thin pages, and a one-line log summary.
    """
    if not markdown or not str(markdown).strip():
        return PageAnalysis(
            quality="error",
            usable_excerpt="",
            log_summary="empty content",
        )
    if "❌ Error" in markdown or str(markdown).strip().startswith("❌"):
        return PageAnalysis(
            quality="error",
            usable_excerpt=markdown[:_EXCERPT_MAX],
            log_summary="fetch error",
        )

    lower = markdown.lower()
    url_lower = (url or "").lower()
    substantive = _substantive_text(markdown)
    substantive_chars = len(substantive)

    score = 0
    parsed = urlparse(url_lower)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    for domain in _PAYWALL_DOMAINS:
        if domain in host or domain in url_lower:
            score += 3
            break

    if any(p in url_lower for p in ("/login", "/signup", "/subscribe", "/purchase")):
        score += 2

    phrase_hits = _count_phrase_hits(lower, _PAYWALL_PHRASES)
    score += phrase_hits * 2

    if "subscribe and save" in lower and "buy now" in lower:
        score += 2
    if "this is a preview" in lower or "preview of subscription" in lower:
        score += 3
    if "log in via an institution" in lower:
        score += 3

    link_density = 0.0
    if substantive_chars > 0:
        link_markers = lower.count("](") + lower.count("http://") + lower.count("https://")
        link_density = link_markers / max(substantive_chars / 80, 1)
        if link_density > 2.5 and substantive_chars < 2500:
            score += 2

    if substantive_chars < _THIN_MIN_SUBSTANTIVE_CHARS:
        score += 2

    if raw_html and substantive_chars < 800:
        html_lower = raw_html.lower()
        if phrase_hits >= 1 and (
            "captcha" in html_lower or "cloudflare" in html_lower
        ):
            score += 1

    if score >= 5:
        quality: PageQuality = "paywall"
    elif substantive_chars < _THIN_MIN_SUBSTANTIVE_CHARS or (
        phrase_hits >= 2 and substantive_chars < 1500
    ):
        quality = "thin"
    else:
        quality = "full"

    excerpt = substantive[:_EXCERPT_MAX] if substantive else markdown[:_EXCERPT_MAX]
    log_summary = (
        f"quality={quality} score={score} substantive_chars={substantive_chars} "
        f"phrase_hits={phrase_hits}"
    )

    return PageAnalysis(
        quality=quality,
        usable_excerpt=excerpt,
        log_summary=log_summary,
        paywall_score=score,
        substantive_chars=substantive_chars,
    )


def format_tool_result_for_quality(
    url: str,
    full_body: str,
    analysis: PageAnalysis,
) -> str:
    """Shrink tool output when page is paywalled or too thin."""
    if analysis.quality == "full":
        return full_body
    if analysis.quality == "error":
        return full_body

    banner = (
        f"(OS Note: Page classified as {analysis.quality} — {analysis.log_summary}. "
        f"Full body withheld to save context. Use search snippets or an open-access source.)"
    )
    excerpt = analysis.usable_excerpt.strip()
    if not excerpt:
        excerpt = "(no substantive excerpt)"
    return (
        f"Content of {url} ({analysis.quality}):\n\n"
        f"{excerpt}\n\n"
        f"{banner}"
    )
