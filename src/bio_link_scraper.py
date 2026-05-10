"""
bio_link_scraper.py
~~~~~~~~~~~~~~~~~~~
Fetch and analyse the URL found in a Telegram bio field.

Extracts:
  - Page title and meta description
  - Email addresses present in the HTML
  - Phone numbers present in the page text
  - Social media links (Twitter/X, Instagram, LinkedIn, GitHub, Facebook,
    TikTok, YouTube, Telegram, VK)

Uses httpx for the HTTP request and BeautifulSoup for HTML parsing.
Timeouts and non-200 responses are handled gracefully.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Regex patterns for PII extraction from page text
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]\d{4}(?!\d)"
)

# URL extraction from bio text (http/https or bare domains with common TLDs)
_BIO_URL_RE = re.compile(
    r"https?://[^\s<>\"')]+|"
    r"(?<!\w)(?:www\.)[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,}(?:/[^\s<>\"')]*)?|"
    r"(?<!\w)[a-zA-Z0-9][a-zA-Z0-9\-]{1,61}[a-zA-Z0-9]\."
    r"(?:com|net|org|io|dev|me|co|app|uk|de|fr|nl|ru|ua)(?:/[^\s<>\"')]*)?(?!\w)"
)

# Social platform → canonical name mapping (longest-match domains first)
_SOCIAL_DOMAINS: list[tuple[str, str]] = [
    ("linkedin.com",   "LinkedIn"),
    ("instagram.com",  "Instagram"),
    ("github.com",     "GitHub"),
    ("facebook.com",   "Facebook"),
    ("twitter.com",    "Twitter"),
    ("x.com",          "Twitter / X"),
    ("tiktok.com",     "TikTok"),
    ("youtube.com",    "YouTube"),
    ("t.me",           "Telegram"),
    ("telegram.me",    "Telegram"),
    ("vk.com",         "VK"),
]


@dataclass
class SocialLink:
    platform: str
    url: str


@dataclass
class BioLinkResult:
    source_url: str
    final_url: Optional[str] = None       # after redirects
    page_title: Optional[str] = None
    meta_description: Optional[str] = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: list[SocialLink] = field(default_factory=list)
    error: Optional[str] = None


def extract_url_from_bio(bio: str) -> Optional[str]:
    """
    Return the first URL found in *bio* text, or ``None`` if no URL is present.

    Bare domains (e.g. ``kandalintsev.com``) are normalised to
    ``https://kandalintsev.com``.
    """
    if not bio:
        return None
    m = _BIO_URL_RE.search(bio)
    if not m:
        return None
    url = m.group(0).rstrip(".,;)")
    if not url.startswith("http"):
        url = "https://" + url
    return url


def _platform_for_url(href: str) -> Optional[str]:
    """Return the canonical social platform name if *href* matches a known domain."""
    href_lower = href.lower()
    for domain, name in _SOCIAL_DOMAINS:
        if domain in href_lower:
            return name
    return None


def scrape_bio_link(url: str) -> BioLinkResult:
    """
    Fetch *url* and extract publicly visible information.

    Parameters
    ----------
    url:
        Fully-qualified URL (must start with http/https).

    Returns
    -------
    :class:`BioLinkResult`
        Extracted fields.  On timeout or non-200 response, ``error`` is set
        and all content fields are empty.
    """
    result = BioLinkResult(source_url=url)

    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": _UA},
            timeout=15,
            follow_redirects=True,
        )
    except httpx.TimeoutException:
        result.error = f"Request timed out: {url}"
        return result
    except httpx.RequestError as exc:
        result.error = f"Network error: {exc}"
        return result

    result.final_url = str(resp.url)

    if resp.status_code != 200:
        result.error = f"HTTP {resp.status_code} from {url}"
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    page_text = soup.get_text(separator=" ", strip=True)

    # Title
    title_tag = soup.find("title")
    if title_tag:
        result.page_title = title_tag.get_text(strip=True) or None

    # Meta description
    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if meta:
        result.meta_description = meta.get("content", "").strip() or None

    # Emails — search both page text and mailto: links
    emails: set[str] = set(_EMAIL_RE.findall(page_text))
    for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
        addr = a["href"].replace("mailto:", "").split("?")[0].strip()
        if addr:
            emails.add(addr)
    result.emails = sorted(emails)

    # Phone numbers
    result.phones = sorted(set(_PHONE_RE.findall(page_text)))

    # Social links — scan all <a href> tags
    seen_social: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        platform = _platform_for_url(href)
        if platform and href not in seen_social:
            seen_social.add(href)
            result.social_links.append(SocialLink(platform=platform, url=href))

    return result
