"""Web search enrichment: URL ranking, auto-scrape, and research source registry."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

from context_budget import ContextProfile, get_context_profile

SourceVia = Literal["auto_scrape", "read_webpage"]

_URL_LINE_RE = re.compile(r"URL:\s+(https?://[^\s]+)", re.I)
_TITLE_BEFORE_URL_RE = re.compile(
    r"(\d+\.\s+[^\n]+)\nURL:\s+(https?://[^\s]+)", re.I
)
_REFERENCES_HEADING_RE = re.compile(
    r"\n##\s+(References|Bibliography)\b[\s\S]*$", re.I
)


@dataclass
class SourceRecord:
    url: str
    title: str | None = None
    via: SourceVia = "auto_scrape"
    step_index: int | None = None


@dataclass
class SourceRegistry:
    records: list[SourceRecord] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set, repr=False)

    def register(
        self,
        url: str,
        *,
        title: str | None = None,
        via: SourceVia = "auto_scrape",
        step_index: int | None = None,
    ) -> bool:
        normalized = normalize_url(url)
        if not normalized or normalized in self._seen:
            return False
        self._seen.add(normalized)
        display_title = (title or "").strip() or _title_from_url(url)
        self.records.append(
            SourceRecord(url=url.strip(), title=display_title, via=via, step_index=step_index)
        )
        return True

    def format_bibliography_markdown(self) -> str:
        if not self.records:
            return (
                "## References\n\n"
                "*No web sources were retrieved during this research run.*"
            )
        lines = ["## References", ""]
        via_label = {"auto_scrape": "auto-scrape", "read_webpage": "read_webpage"}
        for i, rec in enumerate(self.records, start=1):
            label = rec.title or _title_from_url(rec.url)
            lines.append(
                f"{i}. [{label}]({rec.url}) — *retrieved via {via_label.get(rec.via, rec.via)}*"
            )
        return "\n".join(lines)

    def summary_for_prompt(self) -> str:
        if not self.records:
            return ""
        parts = [f"[{i}] {rec.url}" for i, rec in enumerate(self.records, start=1)]
        return (
            f"Sources retrieved so far ({len(self.records)}): "
            + "; ".join(parts[:12])
            + ("\nThe OS will append the full References section to your deliverable." if parts else "")
        )


def normalize_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path.rstrip("/")
    query = parsed.query
    normalized = f"{parsed.scheme.lower()}://{host}{path}"
    if query:
        normalized += f"?{query}"
    return normalized


def _title_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host or url
    except Exception:
        return url


def score_url(url: str) -> int:
    score = 0
    lower = url.lower()
    if ".edu" in lower or ".gov" in lower:
        score += 50
    if ".org" in lower:
        score += 20
    if "arxiv.org" in lower or "github.com" in lower:
        score += 30
    if "reddit.com" in lower or "quora.com" in lower:
        score -= 30
    if "pinterest.com" in lower:
        score -= 50
    if lower.startswith("https://"):
        score += 2
    if any(x in lower for x in ("/login", "/signup", "/cart", "utm_source=")):
        score -= 10
    return score


def extract_urls_from_search_result(text: str) -> list[str]:
    return [m.group(1).strip() for m in _URL_LINE_RE.finditer(text or "")]


def extract_titles_by_url(text: str) -> dict[str, str]:
    titles: dict[str, str] = {}
    for match in _TITLE_BEFORE_URL_RE.finditer(text or ""):
        title = re.sub(r"^\d+\.\s+", "", match.group(1)).strip()
        url = match.group(2).strip()
        if title and url:
            titles[normalize_url(url)] = title
    return titles


def pick_urls_to_scrape(
    urls: list[str],
    scrape_seen: set[str],
    max_count: int,
) -> list[tuple[str, int]]:
    if max_count <= 0:
        return []
    ranked: list[tuple[str, int]] = []
    for url in urls:
        normalized = normalize_url(url)
        if not normalized or normalized in scrape_seen:
            continue
        ranked.append((url.strip(), score_url(url)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:max_count]


def _is_successful_page_content(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    if "❌ Error" in text:
        return False
    if str(text).strip().startswith("❌"):
        return False
    return True


def enrich_search_result(
    result: str,
    scrape_seen: set[str],
    source_registry: SourceRegistry | None,
    profile: ContextProfile | None = None,
    *,
    step_index: int | None = None,
    console=None,
) -> str:
    profile = profile or get_context_profile()
    if not profile.auto_scrape_enabled:
        return result

    urls = extract_urls_from_search_result(result)
    if not urls:
        return result

    titles = extract_titles_by_url(result)
    picks = pick_urls_to_scrape(urls, scrape_seen, profile.auto_scrape_urls)
    if not picks:
        result += "\n\n(OS Note: No new high-quality URLs found to auto-scrape.)"
        return result

    from tool_library import web_tools

    for url, url_score in picks:
        normalized = normalize_url(url)
        scrape_seen.add(normalized)
        if console:
            console.print(
                f"[dim cyan]🔗 OS Smart-Scrape: Selected high-value URL "
                f"(Score: {url_score}) -> {url}[/dim cyan]"
            )
        try:
            scrape_data = web_tools.read_webpage(url, max_chars=profile.scrape_char_cap)
        except Exception as exc:
            result += f"\n\n(OS Auto-Scrape failed for {url}: {exc})"
            continue

        if _is_successful_page_content(scrape_data):
            if source_registry is not None:
                source_registry.register(
                    url,
                    title=titles.get(normalized),
                    via="auto_scrape",
                    step_index=step_index,
                )
            result += (
                f"\n\n--- OS AUTO-SCRAPED TEXT FROM {url} (score={url_score}) ---\n"
                f"{scrape_data}\n--- END AUTO-SCRAPE ---"
            )
        else:
            result += f"\n\n(OS Auto-Scrape failed for {url}: {scrape_data})"

    return result


def register_read_webpage_source(
    source_registry: SourceRegistry | None,
    url: str,
    result: str,
    *,
    step_index: int | None = None,
) -> None:
    if source_registry is None or not url:
        return
    if not _is_successful_page_content(result):
        return
    source_registry.register(url, via="read_webpage", step_index=step_index)


def strip_existing_references_section(report_text: str) -> str:
    text = (report_text or "").rstrip()
    return _REFERENCES_HEADING_RE.sub("", text).rstrip()


def append_bibliography_to_report(
    report_text: str,
    source_registry: SourceRegistry | None,
    *,
    mode: str,
) -> str:
    body = strip_existing_references_section(report_text)
    if mode != "research":
        return body
    bib = (
        source_registry.format_bibliography_markdown()
        if source_registry is not None
        else "## References\n\n*No web sources were retrieved during this research run.*"
    )
    if not body:
        return bib
    return f"{body}\n\n{bib}"
