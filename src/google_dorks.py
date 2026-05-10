"""
google_dorks.py
~~~~~~~~~~~~~~~
Run targeted dork queries against the DuckDuckGo HTML endpoint.
No API key required — uses the public HTML interface.

Returns structured results: {query, hits: [{title, url, snippet}]}
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

_DDG_URL = "https://html.duckduckgo.com/html/"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


@dataclass
class DorkHit:
    title: str
    url: str
    snippet: str


@dataclass
class DorkQuery:
    query: str
    hits: list[DorkHit] = field(default_factory=list)


@dataclass
class DorkReport:
    queries: list[DorkQuery] = field(default_factory=list)
    error: Optional[str] = None


def _extract_url(href: str) -> str:
    """Unwrap DuckDuckGo redirect (/l/?uddg=...) to the real URL."""
    if not href:
        return ""
    if href.startswith("http"):
        return href
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    return unquote(qs.get("uddg", [""])[0])


def _run_single_dork(query: str) -> DorkQuery:
    """POST one query to DuckDuckGo and parse up to 5 results."""
    time.sleep(2)
    result = DorkQuery(query=query)
    try:
        resp = httpx.post(
            _DDG_URL,
            data={"q": query, "kl": "us-en"},
            headers=_HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return result
        soup = BeautifulSoup(resp.text, "html.parser")
        for div in soup.select(".result")[:5]:
            a = div.select_one(".result__a")
            snippet_el = div.select_one(".result__snippet")
            if not a:
                continue
            url = _extract_url(a.get("href", ""))
            if not url:
                continue
            result.hits.append(DorkHit(
                title=a.get_text(strip=True),
                url=url,
                snippet=snippet_el.get_text(strip=True) if snippet_el else "",
            ))
    except httpx.RequestError:
        pass  # network error — return empty result
    return result


def run_dorks(username: str, display_name: Optional[str] = None) -> DorkReport:
    """
    Execute five dork queries for *username* / *display_name* against
    DuckDuckGo's HTML endpoint and return structured results.
    """
    dn = display_name or username
    queries = [
        f'"{username}" site:linkedin.com',
        f'"{username}" site:github.com',
        f'"{dn}" email',
        f'"{username}" filetype:pdf',
        f'"{dn}" "{username}"',
    ]
    report = DorkReport()
    for q in queries:
        report.queries.append(_run_single_dork(q))
    return report
