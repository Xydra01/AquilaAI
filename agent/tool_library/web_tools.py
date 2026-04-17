# Tools related to surfing the internet or getting information via web searches

import requests
import inspect
from bs4 import BeautifulSoup
import markdownify

def web_search(query: str, max_results: int = 5) -> str:
    """Searches the web locally using your private SearXNG instance."""
    url = "http://localhost:8080/search"
    
    params = {
        "q": query,
        "format": "json",
        "engines": "google,bing,duckduckgo,wikipedia",
        "language": "en"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        if not results:
            return f"No results found for '{query}'."
            
        output = f"Search Results for '{query}':\n\n"
        for i, res in enumerate(results[:max_results]):
            output += f"{i+1}. {res.get('title', 'No Title')}\n"
            output += f"URL: {res.get('url', 'No URL')}\n"
            output += f"Snippet: {res.get('content', 'No Content')}\n\n"
            
        return output
    except Exception as e:
        return f"❌ Error executing local web search: {e}"

def read_webpage(url: str) -> str:
    """Fetches a webpage and extracts clean Markdown text locally."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Strip out useless noise like scripts, styles, and footers
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            element.decompose()
            
        # Convert the remaining clean HTML to Markdown
        raw_markdown = markdownify.markdownify(str(soup), heading_style="ATX")
        
        # Clean up excessive blank lines
        clean_markdown = "\n".join([line for line in raw_markdown.splitlines() if line.strip()])
        
        # Truncate if it's absurdly long to protect the context window
        if len(clean_markdown) > 15000:
            return f"Content of {url} (Truncated):\n\n{clean_markdown[:15000]}\n\n...[CONTENT TRUNCATED]"
            
        return f"Content of {url}:\n\n{clean_markdown}"
        
    except Exception as e:
        return f"❌ Error reading webpage locally: {e}"


WEB_TOOLS = {
    "web_search": {"func": web_search, "description": inspect.getdoc(web_search)},
    "read_webpage": {"func": read_webpage, "description": inspect.getdoc(read_webpage)}
}