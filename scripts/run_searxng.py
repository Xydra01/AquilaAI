#!/usr/bin/env python3
"""
run_searxng.py - Local SearXNG-compatible Multi-Source Metasearch Server for Aquila AI Framework
(Zero Docker, 100% Python stdlib)

Listens on http://127.0.0.1:8888 (configurable via --host / --port)
Serves:
  GET /search?q=<query>&format=json
  GET /health
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888
ENGINE_TIMEOUT_SEC = 4.5

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API_UA = "AquilaLocalSearXNG/2.0 (Research Metasearch; +local)"

STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "exist", "for", "from", "guide", "how", "in", "into", "is", "it", "make",
    "making", "of", "on", "or", "other", "out", "process", "sorts", "that", "the",
    "their", "this", "to", "tutorial", "types", "using", "vs", "what", "when",
    "where", "which", "who", "why", "with", "comprehensive", "overview", "methods",
    "research", "tools", "techniques", "best",
}

ACTIVE_ENGINES = [
    "duckduckgo",
    "github",
    "arxiv",
    "wikipedia",
    "hackernews",
    "reddit",
]


def simplify_keywords(query: str, max_terms: int = 5) -> str:
    cleaned = re.sub(r"\bsite:\S+", " ", query, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\"']", " ", cleaned)
    cleaned = re.sub(r"\b(?:19|20)\d{2}\b", " ", cleaned)
    tokens = re.findall(r"[A-Za-z0-9_+#.-]+", cleaned)
    kept: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        low = tok.lower().strip(".-")
        if len(low) < 2 or low in STOPWORDS or low in seen:
            continue
        seen.add(low)
        kept.append(tok)
        if len(kept) >= max_terms:
            break
    return " ".join(kept) if kept else query.strip()


def _stem_token(tok: str) -> str:
    t = tok.lower().strip(".-_\"'")
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith("ing"):
        return t[:-3]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _extract_query_stems(query: str) -> list[str]:
    kw = simplify_keywords(query, max_terms=6)
    stems: list[str] = []
    for tok in kw.split():
        st = _stem_token(tok)
        if len(st) >= 2 and st not in stems:
            stems.append(st)
    return stems


def score_result_relevance(item: dict, query_stems: list[str]) -> tuple[int, int, float]:
    """Return (title_hits, total_hits, weighted_score) for query-term overlap."""
    if not query_stems:
        return (1, 1, 1.0)
    title_low = (item.get("title") or "").lower()
    body_low = ((item.get("content") or "") + " " + (item.get("url") or "")).lower()
    title_hits = 0
    total_hits = 0
    for st in query_stems:
        in_title = st in title_low
        in_body = st in body_low
        if in_title:
            title_hits += 1
        if in_title or in_body:
            total_hits += 1
    weighted = (title_hits * 3.0) + (total_hits * 1.5)
    return (title_hits, total_hits, weighted)


def clean_snippet(text: str, max_len: int = 280) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def canonical_url_key(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url.strip())
        qs = urllib.parse.parse_qsl(p.query, keep_blank_values=False)
        filtered = [(k, v) for k, v in qs if not k.lower().startswith("utm_")]
        path = p.path.rstrip("/")
        return f"{p.scheme.lower()}://{p.netloc.lower()}{path}?{urllib.parse.urlencode(filtered)}"
    except Exception:
        return url.strip().rstrip("/").lower()


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: float = ENGINE_TIMEOUT_SEC) -> str:
    req_headers = {"User-Agent": API_UA, "Accept": "application/json, text/xml, text/html;q=0.9"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if getattr(resp, "status", 200) != 200:
            return ""
        return resp.read().decode("utf-8", errors="replace")


def search_github(query: str, max_results: int = 4) -> list[dict]:
    results: list[dict] = []
    for q in (simplify_keywords(query, 4), simplify_keywords(query, 3)):
        if not q:
            continue
        try:
            encoded = urllib.parse.quote(q)
            url = (
                f"https://api.github.com/search/repositories"
                f"?q={encoded}&sort=stars&order=desc&per_page={max_results}"
            )
            body = http_get_text(
                url,
                headers={"Accept": "application/vnd.github+json", "User-Agent": API_UA},
            )
            if not body:
                continue
            data = json.loads(body)
            for item in data.get("items", [])[:max_results]:
                html_url = item.get("html_url", "")
                if not html_url.startswith("http"):
                    continue
                full_name = item.get("full_name", html_url)
                stars = item.get("stargazers_count", 0)
                lang = item.get("language") or ""
                desc = clean_snippet(item.get("description") or "")
                meta = f"[{stars} stars" + (f", {lang}]" if lang else "]")
                results.append({
                    "title": f"{full_name} (GitHub)",
                    "url": html_url,
                    "content": f"{meta} {desc}".strip(),
                    "engine": "github",
                })
            if results:
                break
        except Exception as exc:
            print(f"[SearXNG Runner] GitHub search error: {exc}", file=sys.stderr)
            break
    return results


def search_arxiv(query: str, max_results: int = 4) -> list[dict]:
    results: list[dict] = []
    kw = simplify_keywords(query, 5)
    if not kw:
        return results
    terms = kw.split()
    # Try strict AND across up to 4 terms, then relax to top 2-3 most specific terms.
    term_sets = [terms[:4]]
    if len(terms) > 2:
        # Prefer longer / more technical words (e.g. decompile, LLM) over generic ones.
        ranked = sorted(terms, key=lambda t: (-len(t), terms.index(t)))
        term_sets.append(ranked[:2])
        if len(terms) >= 3:
            term_sets.append(terms[:2])
    tried: set[tuple[str, ...]] = set()
    for tset in term_sets:
        key = tuple(t.lower() for t in tset)
        if not tset or key in tried:
            continue
        tried.add(key)
        try:
            expr = "+AND+".join(f"all:{urllib.parse.quote(t)}" for t in tset)
            url = (
                f"https://export.arxiv.org/api/query"
                f"?search_query={expr}&start=0&max_results={max_results}"
                f"&sortBy=relevance&sortOrder=descending"
            )
            body = http_get_text(url, headers={"Accept": "application/atom+xml", "User-Agent": API_UA})
            if not body:
                continue
            root = ET.fromstring(body)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns)[:max_results]:
                raw_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
                title = clean_snippet(entry.findtext("atom:title", default="", namespaces=ns) or "", 180)
                summary = clean_snippet(entry.findtext("atom:summary", default="", namespaces=ns) or "", 260)
                published = (entry.findtext("atom:published", default="", namespaces=ns) or "")[:10]
                if not raw_id.startswith("http"):
                    continue
                paper_url = raw_id.replace("http://arxiv.org/", "https://arxiv.org/")
                results.append({
                    "title": f"{title} (arXiv {published})" if published else f"{title} (arXiv)",
                    "url": paper_url,
                    "content": summary,
                    "engine": "arxiv",
                })
            if results:
                break
        except Exception as exc:
            print(f"[SearXNG Runner] arXiv search error: {exc}", file=sys.stderr)
            break
    return results


def search_hackernews(query: str, max_results: int = 4) -> list[dict]:
    results: list[dict] = []
    kw = simplify_keywords(query, 4)
    candidates = [kw]
    if len(kw.split()) > 2:
        candidates.append(" ".join(kw.split()[:2]))
    for q in candidates:
        if not q:
            continue
        try:
            encoded = urllib.parse.quote(q)
            url = (
                f"https://hn.algolia.com/api/v1/search"
                f"?query={encoded}&tags=story&hitsPerPage={max_results}"
            )
            body = http_get_text(url)
            if not body:
                continue
            data = json.loads(body)
            for hit in data.get("hits", [])[:max_results]:
                title = clean_snippet(hit.get("title") or "", 180)
                oid = hit.get("objectID", "")
                target_url = (hit.get("url") or "").strip()
                if not target_url.startswith("http") and oid:
                    target_url = f"https://news.ycombinator.com/item?id={oid}"
                if not target_url.startswith("http") or not title:
                    continue
                points = hit.get("points") or 0
                comments = hit.get("num_comments") or 0
                snippet = f"Hacker News story ({points} pts, {comments} comments)"
                if oid and "news.ycombinator.com" not in target_url:
                    snippet += f" — discussion: https://news.ycombinator.com/item?id={oid}"
                results.append({
                    "title": title,
                    "url": target_url,
                    "content": snippet,
                    "engine": "hackernews",
                })
            if results:
                break
        except Exception as exc:
            print(f"[SearXNG Runner] HackerNews search error: {exc}", file=sys.stderr)
            break
    return results


def search_reddit(query: str, max_results: int = 4) -> list[dict]:
    results: list[dict] = []
    kw = simplify_keywords(query, 5)
    if not kw:
        return results
    try:
        encoded = urllib.parse.quote(kw)
        url = f"https://www.reddit.com/search.json?q={encoded}&sort=relevance&t=all&limit={max_results}"
        body = http_get_text(url, headers={"User-Agent": API_UA, "Accept": "application/json"})
        if not body:
            return results
        data = json.loads(body)
        children = data.get("data", {}).get("children", [])
        for child in children[:max_results]:
            post = child.get("data", {})
            permalink = post.get("permalink", "")
            if not permalink:
                continue
            post_url = f"https://www.reddit.com{permalink}"
            title = clean_snippet(post.get("title") or "", 180)
            sub = post.get("subreddit_name_prefixed") or "r/reddit"
            score = post.get("score") or 0
            comments = post.get("num_comments") or 0
            selftext = clean_snippet(post.get("selftext") or "", 180)
            snippet = f"{sub} ({score} pts, {comments} comments)"
            if selftext:
                snippet += f": {selftext}"
            results.append({
                "title": f"{title} ({sub})",
                "url": post_url,
                "content": snippet,
                "engine": "reddit",
            })
    except Exception as exc:
        print(f"[SearXNG Runner] Reddit search error: {exc}", file=sys.stderr)
    return results


def search_wikipedia(query: str, max_results: int = 4) -> list[dict]:
    results: list[dict] = []
    candidates = [query.strip(), simplify_keywords(query, 4), simplify_keywords(query, 2)]
    tried: set[str] = set()
    for q in candidates:
        if not q or q.lower() in tried:
            continue
        tried.add(q.lower())
        try:
            encoded = urllib.parse.quote(q)
            url = (
                f"https://en.wikipedia.org/w/api.php"
                f"?action=query&list=search&srsearch={encoded}&srlimit={max_results}&utf8=1&format=json"
            )
            body = http_get_text(url, headers={"User-Agent": API_UA})
            if not body:
                continue
            data = json.loads(body)
            hits = data.get("query", {}).get("search", [])
            for item in hits[:max_results]:
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                slug = urllib.parse.quote(title.replace(" ", "_"))
                results.append({
                    "title": f"{title} - Wikipedia",
                    "url": f"https://en.wikipedia.org/wiki/{slug}",
                    "content": clean_snippet(item.get("snippet") or "", 240),
                    "engine": "wikipedia",
                })
            if results:
                break
        except Exception as exc:
            print(f"[SearXNG Runner] Wikipedia search error: {exc}", file=sys.stderr)
            break
    return results


def search_duckduckgo_lite(query: str, max_results: int = 4) -> list[dict]:
    """Best-effort DuckDuckGo Lite fetch; skips cleanly on any challenge or non-200 status."""
    results: list[dict] = []
    try:
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": BROWSER_UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html",
            },
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if getattr(resp, "status", 200) != 200:
                return results
            content = resp.read().decode("utf-8", errors="replace")

        low = content.lower()
        if "anomaly-modal" in low or "verify you are human" in low or "captcha" in low:
            return results

        link_matches = list(re.finditer(
            r"<a\s+[^>]*class=['\"]result-link['\"][^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>|"
            r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>",
            content,
            re.IGNORECASE | re.DOTALL,
        ))
        snippet_matches = list(re.finditer(
            r"<td\s+[^>]*class=['\"]result-snippet['\"][^>]*>(.*?)</td>",
            content,
            re.IGNORECASE | re.DOTALL,
        ))

        for idx, match in enumerate(link_matches[:max_results]):
            raw_url = (match.group(1) or match.group(3) or "").strip()
            raw_title = clean_snippet(match.group(2) or match.group(4) or "", 180)
            if "uddg=" in raw_url:
                parsed = urllib.parse.urlparse(raw_url)
                params = urllib.parse.parse_qs(parsed.query)
                if "uddg" in params:
                    raw_url = params["uddg"][0]
            snippet = clean_snippet(snippet_matches[idx].group(1), 240) if idx < len(snippet_matches) else ""
            if raw_url.startswith("http://") or raw_url.startswith("https://"):
                results.append({
                    "title": raw_title or raw_url,
                    "url": raw_url,
                    "content": snippet,
                    "engine": "duckduckgo",
                })
    except Exception:
        # Silently fall back to public API engines when DDG Lite rate-limits/challenges.
        pass
    return results


def aggregate_search(query: str, limit: int = 12) -> list[dict]:
    engine_fns = {
        "duckduckgo": lambda: search_duckduckgo_lite(query, max_results=8),
        "github": lambda: search_github(query, max_results=4),
        "arxiv": lambda: search_arxiv(query, max_results=4),
        "wikipedia": lambda: search_wikipedia(query, max_results=4),
        "hackernews": lambda: search_hackernews(query, max_results=4),
        "reddit": lambda: search_reddit(query, max_results=4),
    }

    raw_buckets: dict[str, list[dict]] = {name: [] for name in ACTIVE_ENGINES}
    with ThreadPoolExecutor(max_workers=len(engine_fns)) as pool:
        future_map = {pool.submit(fn): name for name, fn in engine_fns.items()}
        for fut in as_completed(future_map, timeout=ENGINE_TIMEOUT_SEC + 2.0):
            name = future_map[fut]
            try:
                raw_buckets[name] = fut.result(timeout=0.5)
            except Exception as exc:
                print(f"[SearXNG Runner] Engine '{name}' timed out or failed: {exc}", file=sys.stderr)

    # Filter off-topic noise (especially from tech/academic engines on non-tech queries)
    # and rank each bucket by query-term overlap.
    query_stems = _extract_query_stems(query)
    has_general_web = len(raw_buckets.get("duckduckgo", [])) > 0
    if not query_stems:
        min_secondary_hits = 0
    elif has_general_web and len(query_stems) >= 4:
        min_secondary_hits = max(2, (len(query_stems) + 1) // 2)
    else:
        min_secondary_hits = min(2, len(query_stems))

    buckets: dict[str, list[dict]] = {name: [] for name in ACTIVE_ENGINES}
    for name in ACTIVE_ENGINES:
        scored: list[tuple[float, int, dict]] = []
        for idx, item in enumerate(raw_buckets.get(name, [])):
            t_hits, tot_hits, weight = score_result_relevance(item, query_stems)
            if name in ("github", "arxiv", "hackernews"):
                # Require genuine topical overlap so Bee Movie / Swiss-Cheese physics / ATC radar get dropped.
                if tot_hits < min_secondary_hits:
                    continue
                if t_hits == 0 and tot_hits < 3:
                    continue
            elif name == "wikipedia":
                if has_general_web and len(query_stems) >= 3 and tot_hits < 2:
                    continue
            elif name == "duckduckgo":
                # Keep DDG Lite results in engine order with a mild relevance boost.
                weight += max(0.0, 2.0 - 0.15 * idx)
            scored.append((weight, -idx, item))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        buckets[name] = [t[2] for t in scored]

    # Round-robin interleave across engines that produced relevant hits, deduplicated by URL.
    merged: list[dict] = []
    seen_keys: set[str] = set()
    max_depth = max((len(v) for v in buckets.values()), default=0)
    for depth in range(max_depth):
        for name in ACTIVE_ENGINES:
            items = buckets.get(name, [])
            if depth >= len(items):
                continue
            item = items[depth]
            key = canonical_url_key(item.get("url", ""))
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class SearxngRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stdout.write(f"[SearXNG Server] {self.address_string()} - {format % args}\n")
        sys.stdout.flush()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path in ("/", "/health"):
            payload = {
                "status": "ok",
                "service": "Aquila Local SearXNG",
                "engines": ACTIVE_ENGINES,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if parsed.path == "/search":
            query = params.get("q", [""])[0].strip()
            if not query:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing query parameter 'q'"}).encode("utf-8"))
                return

            try:
                limit = int(params.get("limit", ["12"])[0])
                limit = max(1, min(limit, 30))
            except ValueError:
                limit = 12

            results = aggregate_search(query, limit=limit)
            payload = {
                "query": query,
                "number_of_results": len(results),
                "results": results,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def run_server(host: str, port: int):
    httpd = ReusableThreadingHTTPServer((host, port), SearxngRequestHandler)
    print("=========================================================")
    print(f"  Aquila Local SearXNG Server Running on http://{host}:{port}")
    print(f"  Zero Docker Required - Multi-Source Metasearch ({', '.join(ACTIVE_ENGINES)})")
    print(f"  Endpoint: http://{host}:{port}/search?q=<query>&format=json")
    print("=========================================================")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[SearXNG Server] Shutting down...")
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser(description="Aquila Local SearXNG Multi-Source Metasearch Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port (default: 8888)")
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
