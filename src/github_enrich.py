"""
github_enrich.py
~~~~~~~~~~~~~~~~
Fetch a GitHub user's public profile and scan their recent public events
for email addresses in commit author payloads.

Uses GitHub's unauthenticated API (60 requests/hour limit).
No API key required.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

_API = "https://api.github.com"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/vnd.github.v3+json",
}


@dataclass
class GitHubProfile:
    name: Optional[str] = None
    email: Optional[str] = None          # profile email (often hidden)
    bio: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    blog: Optional[str] = None
    public_repos: Optional[int] = None
    followers: Optional[int] = None
    commit_emails: list[str] = field(default_factory=list)  # from push events
    not_found: bool = False
    error: Optional[str] = None


def fetch_github(username: str) -> GitHubProfile:
    """
    Fetch *username*'s public GitHub profile and recent push-event emails.

    Returns a :class:`GitHubProfile`.  If the account does not exist,
    ``not_found`` is set to True.  Rate-limit and network errors populate
    ``error`` without raising.
    """
    profile = GitHubProfile()

    # ── Profile ───────────────────────────────────────────────────────────────
    time.sleep(2)
    try:
        resp = httpx.get(f"{_API}/users/{username}", headers=_HEADERS, timeout=15)
    except httpx.RequestError as exc:
        profile.error = f"Network error: {exc}"
        return profile

    if resp.status_code == 404:
        profile.not_found = True
        return profile
    if resp.status_code == 403:
        profile.error = "GitHub rate limit exceeded (60 req/hr unauthenticated)."
        return profile
    if resp.status_code != 200:
        profile.error = f"GitHub API returned HTTP {resp.status_code}."
        return profile

    data = resp.json()
    profile.name         = data.get("name") or None
    profile.email        = data.get("email") or None
    profile.bio          = data.get("bio") or None
    profile.company      = data.get("company") or None
    profile.location     = data.get("location") or None
    profile.blog         = data.get("blog") or None
    profile.public_repos = data.get("public_repos")
    profile.followers    = data.get("followers")

    # ── Commit emails from public push events ─────────────────────────────────
    time.sleep(2)
    try:
        resp = httpx.get(
            f"{_API}/users/{username}/events/public",
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            emails: set[str] = set()
            for event in resp.json():
                if event.get("type") != "PushEvent":
                    continue
                for commit in event.get("payload", {}).get("commits", []):
                    addr = commit.get("author", {}).get("email", "")
                    # Skip GitHub's no-reply addresses
                    if addr and "noreply.github.com" not in addr:
                        emails.add(addr)
            profile.commit_emails = sorted(emails)
    except (httpx.RequestError, ValueError):
        pass  # events are a bonus — non-fatal if unavailable

    return profile
