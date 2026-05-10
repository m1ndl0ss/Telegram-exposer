"""
username_enum.py
~~~~~~~~~~~~~~~~
Run Sherlock (https://github.com/sherlock-project/sherlock) as a subprocess
to enumerate social-media platforms where a username is registered.

Sherlock must be installed and available on PATH:
    pip install sherlock-project

Each result is parsed into a structured dict so downstream modules do not
need to understand Sherlock's raw output format.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlatformResult:
    """Presence of a username on one platform."""

    platform: str
    url: str
    found: bool


@dataclass
class EnumResult:
    """Aggregated Sherlock results for a single username."""

    username: str
    platforms: list[PlatformResult]
    error: Optional[str] = None


# Patterns emitted by Sherlock on stdout
_FOUND_RE = re.compile(r"\[✓\]\s+(.+?):\s+(https?://\S+)")
_NOT_FOUND_RE = re.compile(r"\[✗\]\s+(.+?):\s+")
_ERROR_RE = re.compile(r"\[!\]\s+(.+?):\s+")


def _parse_sherlock_output(username: str, stdout: str) -> EnumResult:
    """Convert raw Sherlock stdout into structured :class:`EnumResult`."""
    platforms: list[PlatformResult] = []

    for line in stdout.splitlines():
        m = _FOUND_RE.search(line)
        if m:
            platforms.append(
                PlatformResult(platform=m.group(1).strip(), url=m.group(2).strip(), found=True)
            )
            continue

        m = _NOT_FOUND_RE.search(line)
        if m:
            platforms.append(
                PlatformResult(platform=m.group(1).strip(), url="", found=False)
            )
            continue

        # Error lines (e.g. connection timeout) are silently skipped;
        # they do not affect found/not-found counts.

    return EnumResult(username=username, platforms=platforms)


def run_sherlock(username: str, timeout: int = 120) -> EnumResult:
    """
    Invoke Sherlock for *username* and return parsed results.

    Parameters
    ----------
    username:
        The username string to search (no ``@`` prefix).
    timeout:
        Maximum seconds to wait for Sherlock before aborting.

    Returns
    -------
    :class:`EnumResult`
        Structured list of platform results.  If Sherlock is not installed or
        times out, the ``error`` field is populated instead.
    """
    username = username.lstrip("@")

    # Detect sherlock executable (installed via pip as 'sherlock')
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
        return EnumResult(
            username=username,
            platforms=[],
            error="Sherlock not found. Install with: pip install sherlock-project",
        )
    except subprocess.TimeoutExpired:
        return EnumResult(
            username=username,
            platforms=[],
            error=f"Sherlock timed out after {timeout}s.",
        )
    except Exception as exc:
        return EnumResult(username=username, platforms=[], error=str(exc))

    if proc.returncode not in (0, 1):
        # returncode 1 can mean "nothing found" in some versions; anything
        # higher is unexpected.
        stderr_snippet = proc.stderr[:300] if proc.stderr else ""
        return EnumResult(
            username=username,
            platforms=[],
            error=f"Sherlock exited with code {proc.returncode}. stderr: {stderr_snippet}",
        )

    return _parse_sherlock_output(username, proc.stdout)
