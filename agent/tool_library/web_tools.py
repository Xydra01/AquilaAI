# Tools related to surfing the internet or getting information via web searches



import inspect

import io



import cloudscraper

from pdf_text import extract_pdf_text

import markdownify

import requests

from bs4 import BeautifulSoup



from context_budget import get_context_profile
from web_content_quality import analyze_fetched_page, format_tool_result_for_quality
from web_search_query import clean_research_query, low_quality_results_note



_DEFAULT_SCRAPE_CAP = 15_000





def _scrape_cap(max_chars: int | None) -> int:

    if max_chars is not None and max_chars > 0:

        return max_chars

    return get_context_profile().scrape_char_cap





def web_search(query: str, max_results: int = 5) -> str:

    """Searches the web locally using your private SearXNG instance."""

    url = "http://localhost:8080/search"



    try:

        limit = int(max_results)

        stripped = query.replace('"', '').replace("'", "")
        clean_query, rewrite_note = clean_research_query(stripped)
        if rewrite_note:
            try:
                from run_logger import get_active_run_logger

                logger = get_active_run_logger()
                if logger:
                    logger.event(
                        "tool_start",
                        tool="web_search",
                        query_original=stripped[:200],
                        query_cleaned=clean_query[:200],
                        rewrite_note=rewrite_note,
                    )
            except Exception:
                pass



        params = {

            "q": clean_query,

            "format": "json",

            "engines": "google,bing,duckduckgo,wikipedia",

            "language": "en",

        }



        response = requests.get(url, params=params, timeout=15)

        response.raise_for_status()

        data = response.json()



        results = data.get("results", [])

        if not results:

            return f"No results found for '{clean_query}'."



        output = f"Search Results for '{clean_query}':\n\n"

        for i, res in enumerate(results[:limit]):

            output += f"{i+1}. {res.get('title', 'No Title')}\n"

            output += f"URL: {res.get('url', 'No URL')}\n"

            output += f"Snippet: {res.get('content', 'No Snippet')}\n\n"



        quality_note = low_quality_results_note(output)
        if quality_note:
            output += f"\n{quality_note}\n"
        return output

    except ValueError:

        return "❌ Error: max_results must be a number."

    except Exception as e:

        return f"❌ Error executing local web search: {e}"





def read_webpage(url: str, max_chars: int | None = None) -> str:

    """Fetches a webpage or PDF and extracts clean text. After web_search the OS auto-scrapes top URLs; use this for a specific URL not yet scraped."""

    cap = _scrape_cap(max_chars)

    try:

        scraper = cloudscraper.create_scraper()

        headers = {

            "User-Agent": (

                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "

                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

            )

        }

        response = scraper.get(url, headers=headers, timeout=15)

        response.raise_for_status()



        content_type = response.headers.get("Content-Type", "").lower()



        if "application/pdf" in content_type or url.lower().endswith(".pdf"):

            pdf_text = extract_pdf_text(response.content)

            if len(pdf_text) > cap:

                return (

                    f"Content of {url} (PDF Truncated):\n\n"

                    f"{pdf_text[:cap]}\n\n...[CONTENT TRUNCATED]"

                )

            return f"Content of {url} (PDF):\n\n{pdf_text}"



        soup = BeautifulSoup(response.text, "html.parser")



        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):

            element.decompose()



        raw_markdown = markdownify.markdownify(str(soup), heading_style="ATX")

        clean_markdown = "\n".join(

            [line for line in raw_markdown.splitlines() if line.strip()]

        )



        analysis = analyze_fetched_page(url, clean_markdown, raw_html=response.text)

        if len(clean_markdown) > cap:

            full_body = (

                f"Content of {url} (Truncated):\n\n"

                f"{clean_markdown[:cap]}\n\n...[CONTENT TRUNCATED]"

            )

        else:

            full_body = f"Content of {url}:\n\n{clean_markdown}"

        if analysis.quality != "full":

            return format_tool_result_for_quality(url, full_body, analysis)

        return full_body



    except Exception as e:

        return f"❌ Error reading URL: {str(e)}"





WEB_TOOLS = {

    "web_search": {"func": web_search, "description": inspect.getdoc(web_search)},

    "read_webpage": {"func": read_webpage, "description": inspect.getdoc(read_webpage)},

}

