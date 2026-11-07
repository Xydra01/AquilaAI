#!/usr/bin/env python3
"""
run_searxng.py - Local SearXNG-compatible Search Server for Aquila AI Framework (Zero Docker)

Listens on http://127.0.0.1:8888
Serves:
  GET /search?q=<query>&format=json
  GET /health
"""

import sys
import json
import html
import re
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

HOST = "127.0.0.1"
PORT = 8888

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def search_duckduckgo_lite(query: str, max_results: int = 10) -> list[dict]:
    results = []
    try:
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Parse DuckDuckGo Lite HTML:
        # Matches <a ... href="..." ... class='result-link' ...>TITLE</a>
        # or      <a ... class='result-link' ... href="..." ...>TITLE</a>
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

        clean_tag_re = re.compile(r"<[^>]+>")

        for idx, match in enumerate(link_matches[:max_results]):
            raw_url = (match.group(1) or match.group(3) or "").strip()
            raw_title = clean_tag_re.sub("", match.group(2) or match.group(4) or "").strip()
            title = html.unescape(raw_title)

            # DuckDuckGo Lite sometimes wraps urls in /lite/?uddg=...
            if "uddg=" in raw_url:
                parsed = urllib.parse.urlparse(raw_url)
                params = urllib.parse.parse_qs(parsed.query)
                if "uddg" in params:
                    raw_url = params["uddg"][0]

            snippet = ""
            if idx < len(snippet_matches):
                raw_snippet = clean_tag_re.sub("", snippet_matches[idx].group(1)).strip()
                snippet = html.unescape(raw_snippet)

            if raw_url.startswith("http://") or raw_url.startswith("https://"):
                results.append({
                    "title": title or raw_url,
                    "url": raw_url,
                    "content": snippet,
                    "engine": "duckduckgo",
                })
    except Exception as exc:
        print(f"[SearXNG Runner] DuckDuckGo search error: {exc}", file=sys.stderr)

    return results

def search_wikipedia_opensearch(query: str, max_results: int = 5) -> list[dict]:
    results = []
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit={max_results}&namespace=0&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if len(data) >= 4:
            titles = data[1]
            snippets = data[2]
            urls = data[3]
            for t, s, u in zip(titles, snippets, urls):
                if u.startswith("http://") or u.startswith("https://"):
                    results.append({
                        "title": t,
                        "url": u,
                        "content": s,
                        "engine": "wikipedia",
                    })
    except Exception as exc:
        print(f"[SearXNG Runner] Wikipedia search error: {exc}", file=sys.stderr)

    return results

class SearxngRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Clean terminal logging
        sys.stdout.write(f"[SearXNG Server] {self.address_string()} - {format % args}\n")
        sys.stdout.flush()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "Aquila Local SearXNG"}).encode("utf-8"))
            return

        if parsed.path == "/search":
            query = params.get("q", [""])[0].strip()
            format_type = params.get("format", ["json"])[0]

            if not query:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing query parameter 'q'"}).encode("utf-8"))
                return

            # Aggregate DDG Lite + Wikipedia
            results = search_duckduckgo_lite(query, max_results=8)
            if len(results) < 3:
                wiki_results = search_wikipedia_opensearch(query, max_results=3)
                results.extend(wiki_results)

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

def run_server():
    server_address = (HOST, PORT)
    httpd = HTTPServer(server_address, SearxngRequestHandler)
    print(f"=========================================================")
    print(f"  Aquila Local SearXNG Server Running on http://{HOST}:{PORT}")
    print(f"  Zero Docker Required - Native Python Metasearch")
    print(f"  Endpoint: http://{HOST}:{PORT}/search?q=<query>&format=json")
    print(f"=========================================================")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[SearXNG Server] Shutting down...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
