"""Web tools: search and fetch."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx
from banana.tools.base import Tool, tool_parameters

FETCH_TIMEOUT = 60.0
MAX_URL_LENGTH = 2000
MAX_MARKDOWN_LENGTH = 100_000


def _html_to_markdown(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@tool_parameters({
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query"},
        "max_results": {"type": "integer", "description": "Max results (default: 5)"},
    },
    "required": ["query"],
})
class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web. Set tavily_api_key in config.json tools section."
    read_only = True

    def __init__(self, api_key: str = ""):
        super().__init__()
        self._api_key = api_key

    def set_api_key(self, key: str):
        self._api_key = key

    async def execute(self, query: str, max_results: int = 5) -> str:
        import os
        from loguru import logger
        api_key = self._api_key or os.environ.get("TAVILY_API_KEY", "")
        logger.debug(f"WebSearchTool execute: api_key from config={bool(self._api_key)}, from env={bool(os.environ.get('TAVILY_API_KEY'))}")
        if not api_key:
            return "web_search:\n[FAILED] Set tavily_api_key in config.json tools section or TAVILY_API_KEY env var."

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            result = await asyncio.to_thread(
                client.search, query, max_results=max_results,
            )
            lines = []
            for r in result.get("results", []):
                lines.append(f"- [{r.get('title', 'No title')}]({r.get('url', '')}): {r.get('content', '')[:200]}")
            return f"web_search:\n[OK] ({len(lines)} results)\n\n" + "\n".join(lines)
        except ImportError:
            return "web_search:\n[FAILED] Install tavily-python to use web search."
        except Exception as e:
            return f"web_search:\n[FAILED] {e}"


@tool_parameters({
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to fetch"},
    },
    "required": ["url"],
})
class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch and convert a web page to text."
    read_only = True

    async def execute(self, url: str) -> str:
        if len(url) > MAX_URL_LENGTH:
            return f"web_fetch:\n[FAILED] URL exceeds {MAX_URL_LENGTH} chars"

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return f"web_fetch:\n[FAILED] Invalid URL: {url}"
        if parsed.scheme == "http":
            url = url.replace("http://", "https://", 1)

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=FETCH_TIMEOUT, max_redirects=10,
                headers={"User-Agent": "BananaCoder/1.0"},
            ) as client:
                resp = await client.get(url)
        except httpx.TimeoutException:
            return f"web_fetch:\n[FAILED] Timeout after {FETCH_TIMEOUT}s"
        except Exception as e:
            return f"web_fetch:\n[FAILED] {e}"

        content_type = resp.headers.get("content-type", "")
        if any(t in content_type.lower() for t in ("image/", "video/", "audio/", "application/pdf")):
            return f"web_fetch:\n[FAILED] Binary content ({content_type}), cannot extract text."

        text = _html_to_markdown(resp.text) if "text/html" in content_type else resp.text
        if len(text) > MAX_MARKDOWN_LENGTH:
            text = text[:MAX_MARKDOWN_LENGTH] + "\n\n[Content truncated...]"
        return f"web_fetch:\n[OK] ({resp.status_code}, {len(text)} chars)\n\n{text}"
