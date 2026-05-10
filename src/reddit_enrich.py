"""
reddit_enrich.py
~~~~~~~~~~~~~~~~
Fetch a Reddit user's public profile stats and scan their recent comment
history for PII patterns (emails, phone numbers, location disclosures).

Uses Reddit's public JSON API — no API key required.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA}

# PII patterns
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]\d{4}(?!\d)"
)
_LOCATION_RE = re.compile(
    r"(?:I(?:'m| am) (?:from|in)|based in|live in|living in|located in|from)\s+"
    r"([A-Z][a-zA-Z\-]+(?:[\s,]+[A-Z][a-zA-Z\-]+)?)",
)


@dataclass
class RedditProfile:
    account_age_days: Optional[int] = None
    comment_karma: Optional[int] = None
    post_karma: Optional[int] = None
    verified_email: Optional[bool] = None
    found_emails: list[str] = field(default_factory=list)
    found_phones: list[str] = field(default_factory=list)
    found_locations: list[str] = field(default_factory=list)
    not_found: bool = False
    error: Optional[str] = None


def fetch_reddit(username: str) -> RedditProfile:
    """
    Fetch *username*'s Reddit profile stats and scan up to 100 recent
    comments for email addresses, phone numbers, and location disclosures.

    Returns a :class:`RedditProfile`.  Non-existent accounts set
    ``not_found = True``; errors populate ``error`` without raising.
    """
    profile = RedditProfile()

    # ── Account stats ─────────────────────────────────────────────────────────
    time.sleep(2)
    try:
        resp = httpx.get(
            f"https://www.reddit.com/user/{username}/about.json",
            headers=_HEADERS,
            timeout=15,
        )
    except httpx.RequestError as exc:
        profile.error = f"Network error: {exc}"
        return profile

    if resp.status_code == 404:
        profile.not_found = True
        return profile
    if resp.status_code == 429:
        profile.error = "Reddit rate limited — try again later."
        return profile
    if resp.status_code != 200:
        profile.error = f"Reddit API returned HTTP {resp.status_code}."
        return profile

    data = resp.json().get("data", {})
    created_utc = data.get("created_utc", 0)
    if created_utc:
        age_days = (datetime.now(timezone.utc).timestamp() - created_utc) / 86_400
        profile.account_age_days = int(age_days)
    profile.comment_karma = data.get("comment_karma")
    profile.post_karma    = data.get("link_karma")
    profile.verified_email = data.get("verified")

    # ── Comment PII scan ──────────────────────────────────────────────────────
    time.sleep(2)
    try:
        resp = httpx.get(
            f"https://www.reddit.com/user/{username}/comments.json",
            params={"limit": 100},
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            emails: set[str] = set()
            phones: set[str] = set()
            locations: set[str] = set()
            for child in resp.json().get("data", {}).get("children", []):
                body = child.get("data", {}).get("body", "")
                emails.update(_EMAIL_RE.findall(body))
                phones.update(_PHONE_RE.findall(body))
                for m in _LOCATION_RE.finditer(body):
                    locations.add(m.group(1).strip())
            profile.found_emails    = sorted(emails)
            profile.found_phones    = sorted(phones)
            profile.found_locations = sorted(locations)
    except (httpx.RequestError, ValueError):
        pass  # PII scan is non-fatal

    return profile
