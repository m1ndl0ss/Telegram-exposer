"""
telegram_osint.py
~~~~~~~~~~~~~~~~~
Resolve a Telegram username or phone number to a public profile via
Telethon (MTProto).  Only publicly visible fields are fetched; privacy
restrictions are handled gracefully.

Environment variables required:
    TELEGRAM_API_ID   – integer app ID from my.telegram.org
    TELEGRAM_API_HASH – hex string app hash from my.telegram.org
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import UserFull

load_dotenv()

SESSION_NAME = "osint_session"


@dataclass
class TelegramProfile:
    """Public-facing Telegram profile fields."""

    user_id: Optional[int] = None
    display_name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None          # only visible if mutually saved
    bio: Optional[str] = None
    profile_photo_url: Optional[str] = None
    last_seen: Optional[str] = None
    is_bot: bool = False
    restricted: bool = False
    restriction_reasons: list[str] = field(default_factory=list)
    raw_errors: list[str] = field(default_factory=list)


async def _download_photo(client: TelegramClient, entity) -> Optional[str]:
    """Download profile photo to a temp path and return local path, or None."""
    try:
        path = await client.download_profile_photo(entity, file="reports/profile_photo")
        return str(path) if path else None
    except Exception:
        return None


async def fetch_profile(identifier: str) -> TelegramProfile:
    """
    Resolve *identifier* (``@username`` or ``+phonenumber``) to a public
    Telegram profile.

    Returns a :class:`TelegramProfile` dataclass; fields that are hidden by
    the account's privacy settings are left as ``None``.
    """
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    profile = TelegramProfile()

    async with TelegramClient(SESSION_NAME, api_id, api_hash) as client:
        try:
            entity = await client.get_entity(identifier)
        except (UsernameInvalidError, UsernameNotOccupiedError) as exc:
            profile.raw_errors.append(f"Resolution error: {exc}")
            return profile
        except FloodWaitError as exc:
            profile.raw_errors.append(f"Rate-limited; retry after {exc.seconds}s")
            return profile
        except Exception as exc:
            profile.raw_errors.append(f"Unexpected error: {exc}")
            return profile

        profile.user_id = entity.id
        profile.is_bot = getattr(entity, "bot", False)
        profile.username = getattr(entity, "username", None)
        profile.restricted = getattr(entity, "restricted", False)

        reasons = getattr(entity, "restriction_reason", []) or []
        profile.restriction_reasons = [r.reason for r in reasons]

        first = getattr(entity, "first_name", "") or ""
        last = getattr(entity, "last_name", "") or ""
        profile.display_name = (first + " " + last).strip() or None

        # Phone is only exposed when the account is in your contacts
        profile.phone = getattr(entity, "phone", None)

        # Last seen – may be hidden by privacy settings
        status = getattr(entity, "status", None)
        if status is not None:
            profile.last_seen = type(status).__name__  # e.g. UserStatusOnline
        else:
            profile.last_seen = "hidden"

        # Bio requires a full-user fetch
        try:
            full: UserFull = (await client(GetFullUserRequest(entity))).full_user
            profile.bio = getattr(full, "about", None)
        except Exception as exc:
            profile.raw_errors.append(f"Bio fetch failed: {exc}")

        profile.profile_photo_url = await _download_photo(client, entity)

    return profile
