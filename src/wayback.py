"""
wayback.py
~~~~~~~~~~
Check URLs against the Wayback Machine CDX API.
No API key required — public endpoint.

For each URL, one CDX request is made (limit=5, ascending order).
Record [0] gives the earliest known snapshot; record [-1] gives the
most recent snapshot within the sampled set.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

_CDX = "https://web.archive.org/cdx/search/cdx"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class WaybackRecord:
    platform: str
    checked_url: str
    earliest_date: Optional[str] = None
    latest_snapshot_url: Optional[str] = None
    total_sampled: int = 0


@dataclass
class WaybackReport:
    records: list[WaybackRecord] = field(default_factory=list)
    error: Optional[str] = None


def _fmt_ts(ts: str) -> str:
    """Convert CDX timestamp YYYYMMDDHHMMSS → YYYY-MM-DD."""
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else ts


def _query(url: str) -> WaybackRecord:
    """Run one CDX lookup for *url* and return a WaybackRecord."""
    time.sleep(2)
    record = WaybackRecord(platform="", checked_url=url)
    try:
        resp = httpx.get(
            _CDX,
            params={
                "url": url,
                "output": "json",
                "fl": "timestamp,original",
                "limit": 5,
                "matchType": "exact",
            },
            headers={"User-Agent": _UA},
            timeout=20,
        )
        if resp.status_code != 200:
            return record
        rows = resp.json()
        # First row is column headers ["timestamp","original"], rest are data
        data = rows[1:]
        if not data:
            return record
        record.total_sampled = len(data)
        record.earliest_date = _fmt_ts(data[0][0])
        latest_ts, latest_orig = data[-1][0], data[-1][1]
        record.latest_snapshot_url = f"https://web.archive.org/web/{latest_ts}/{latest_orig}"
    except (httpx.RequestError, ValueError, IndexError):
        pass
    return record


def check_wayback(username: str, sherlock_platforms: list[dict]) -> WaybackReport:
    """
    Check the Telegram profile page and every Sherlock-found platform URL
    against the Wayback Machine CDX API.

    Parameters
    ----------
    username:
        Bare username (no @) used to build the t.me URL.
    sherlock_platforms:
        List of platform dicts from :mod:`username_enum`, filtered to found=True.
    """
    report = WaybackReport()

    # Always check t.me/{username}
    tg_record = _query(f"https://t.me/{username}")
    tg_record.platform = "Telegram (t.me)"
    report.records.append(tg_record)

    for p in sherlock_platforms:
        if not p.get("found") or not p.get("url"):
            continue
        rec = _query(p["url"])
        rec.platform = p["platform"]
        report.records.append(rec)

    return report
