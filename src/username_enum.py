"""
username_enum.py
~~~~~~~~~~~~~~~~
Run Sherlock (https://github.com/sherlock-project/sherlock) as a subprocess
to enumerate social-media platforms where a username is registered.

Also generates and searches leet-speak variations of the username:
  o→0  i→1  a→4  e→3  s→5

Results from all variants are merged and deduplicated by URL.  Each
PlatformResult carries a ``variant`` field recording which username found it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

# ── Leet-speak variant generation ─────────────────────────────────────────────

_LEET: dict[str, str] = {"o": "0", "i": "1", "a": "4", "e": "3", "s": "5"}


def _leet_variants(username: str) -> list[str]:
    """
    Return a deduplicated list of leet-speak variations that differ from
    *username* (lowercased).

    Strategy:
      - One variant per applicable character *type* (all occurrences of that
        character substituted at once), e.g. "alice" → "4lice" (a-only).
      - One fully-leetified variant (all applicable chars substituted).
    """
    u = username.lower()
    applicable_types = {ch for ch in u if ch in _LEET}
    if not applicable_types:
        return []

    variants: set[str] = set()

    # Single-type substitutions
    for ch in applicable_types:
        v = u.replace(ch, _LEET[ch])
        if v != u:
            variants.add(v)

    # Full substitution
    full = u
    for ch, leet in _LEET.items():
        full = full.replace(ch, leet)
    if full != u:
        variants.add(full)

    return sorted(variants)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class PlatformResult:
    """Presence of a username on one platform."""

    platform: str
    url: str
    found: bool
    variant: str = ""   # which username string produced this result


@dataclass
class EnumResult:
    """Aggregated Sherlock results across the primary username and all variants."""

    username: str
    platforms: list[PlatformResult] = field(default_factory=list)
    variants_searched: list[str] = field(default_factory=list)
    error: Optional[str] = None


# ── Sherlock invocation ────────────────────────────────────────────────────────

# Patterns emitted by Sherlock on stdout
_FOUND_RE     = re.compile(r"\[✓\]\s+(.+?):\s+(https?://\S+)")
_NOT_FOUND_RE = re.compile(r"\[✗\]\s+(.+?):\s+")


def _parse_output(username: str, stdout: str) -> list[PlatformResult]:
    """Parse raw Sherlock stdout into a list of PlatformResult objects."""
    results: list[PlatformResult] = []
    for line in stdout.splitlines():
        m = _FOUND_RE.search(line)
        if m:
            results.append(PlatformResult(
                platform=m.group(1).strip(),
                url=m.group(2).strip(),
                found=True,
                variant=username,
            ))
            continue
        m = _NOT_FOUND_RE.search(line)
        if m:
            results.append(PlatformResult(
                platform=m.group(1).strip(),
                url="",
                found=False,
                variant=username,
            ))
    return results


def _invoke_sherlock(username: str, timeout: int) -> tuple[list[PlatformResult], Optional[str]]:
    """
    Run Sherlock for one *username* and return ``(platforms, error_or_None)``.
    Only ``--print-found`` is passed so stdout is concise.
    """
    cmd = [sys.executable, "-m", "sherlock", username, "--print-found", "--no-color"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return [], "Sherlock not found. Install with: pip install sherlock-project"
    except subprocess.TimeoutExpired:
        return [], f"Sherlock timed out after {timeout}s for '{username}'."
    except Exception as exc:
        return [], str(exc)

    if proc.returncode not in (0, 1):
        snippet = proc.stderr[:200] if proc.stderr else ""
        return [], f"Sherlock exited {proc.returncode} for '{username}'. {snippet}"

    return _parse_output(username, proc.stdout), None


def run_sherlock(username: str, timeout: int = 120) -> EnumResult:
    """
    Run Sherlock for a single *username* and return an :class:`EnumResult`.

    Kept for backward-compatibility.  Prefer :func:`run_sherlock_all` for the
    full leet-variant pipeline.
    """
    username = username.lstrip("@")
    platforms, err = _invoke_sherlock(username, timeout)
    return EnumResult(username=username, platforms=platforms, error=err)


def run_sherlock_all(username: str, timeout: int = 120) -> EnumResult:
    """
    Run Sherlock on *username* and on all leet-speak variants, then merge.

    Deduplication is by URL — if a URL was already found by the primary run,
    the variant entry is dropped.  Not-found entries from variant runs are
    discarded (they carry no signal about the primary identity).

    Parameters
    ----------
    username:
        Primary username (no ``@`` prefix).
    timeout:
        Per-invocation timeout in seconds passed to Sherlock.

    Returns
    -------
    :class:`EnumResult`
        Merged platforms across all searched variants.
    """
    username = username.lstrip("@")

    # Primary run — keep all results (found and not-found)
    primary_platforms, err = _invoke_sherlock(username, timeout)
    if err:
        return EnumResult(username=username, error=err)

    seen_urls: set[str] = {p.url for p in primary_platforms if p.url}
    merged: list[PlatformResult] = list(primary_platforms)
    variants = _leet_variants(username)

    for variant in variants:
        v_platforms, _ = _invoke_sherlock(variant, timeout)
        # Only add found results that aren't already in the merged list
        for p in v_platforms:
            if p.found and p.url and p.url not in seen_urls:
                seen_urls.add(p.url)
                merged.append(p)

    return EnumResult(
        username=username,
        platforms=merged,
        variants_searched=variants,
        error=None,
    )
