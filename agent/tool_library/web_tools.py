#Tools related to surfing the internet or getting information via web searches

import requests
import os
import inspect
from tavily import TavilyClient

def web_search(query: str, max_results: int = 5) -> str:
    """Searches the web/internet using Tavily API."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "System Error: TAVILY_API_KEY environment variable is missing."
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)
        results = response.get("results", [])
        if not results:
            return f"No results found for '{query}'."
        output = f"Search Results for '{query}':\n\n"
        for i, res in enumerate(results):
            output += f"{i+1}. {res.get('title', 'No Title')}\nURL: {res.get('url', 'No URL')}\nSnippet: {res.get('content', 'No Content')}\n\n"
        return output
    except Exception as e:
        return f"Error searching the web: {e}"

def read_webpage(url: str) -> str:
    """Fetches a webpage and extracts clean Markdown text using Jina Reader."""
    try:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(jina_url, headers=headers, timeout=15)
        response.raise_for_status()
        content = response.text
        if len(content) > 15000:
            return f"Content of {url} (Truncated):\n\n{content[:15000]}\n\n...[CONTENT TRUNCATED]"
        return f"Content of {url}:\n\n{content}"
    except Exception as e:
        return f"Error reading webpage: {e}"
    

WEB_TOOLS = {
    "web_search": {"func": web_search, "description": inspect.getdoc(web_search)},
    "read_webpage": {"func": read_webpage, "description": inspect.getdoc(read_webpage)},
}