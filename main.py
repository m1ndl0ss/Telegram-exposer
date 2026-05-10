"""
main.py
~~~~~~~
CLI entrypoint for Telegram-Exposer.

Usage examples:
    python main.py --consent                         # prompts for username
    python main.py --username johndoe --consent
    python main.py --phone +1234567890 --consent
    python main.py --username johndoe --consent --skip-sherlock
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap
import time

from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt

load_dotenv()

console = Console()


# ── Startup animation ─────────────────────────────────────────────────────────

def _startup() -> None:
    """Clear the screen, animate the title, show tagline."""
    console.clear()
    time.sleep(0.05)

    console.print()
    for char in "TG-EXPOSER":
        console.print(f"[bold red on black]{char}[/]", end="", highlight=False)
        time.sleep(0.05)
    console.print("\n")

    console.print(
        "[dim white]OSINT identity linkage research tool | academic use only[/]\n"
    )
    time.sleep(0.2)


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-exposer",
        description="OSINT data display for Telegram accounts (academic use only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python main.py --consent                       (prompts for username)
              python main.py --username johndoe --consent
              python main.py --phone +1234567890 --consent
        """),
    )
    # Both flags are optional — if neither is given, the tool prompts interactively.
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--username", "-u",
        metavar="USERNAME",
        help="Telegram @username to investigate (without the @ symbol).",
    )
    target.add_argument(
        "--phone", "-p",
        metavar="PHONE",
        help="Phone number in E.164 format (e.g. +1234567890).",
    )
    parser.add_argument(
        "--consent",
        action="store_true",
        help=(
            "REQUIRED. You confirm that you have authorisation to analyse "
            "this account and understand the ethical constraints."
        ),
    )
    parser.add_argument(
        "--skip-sherlock",
        action="store_true",
        help="Skip Sherlock username enumeration (useful if not installed).",
    )
    parser.add_argument(
        "--skip-enrich",
        action="store_true",
        help="Skip all enrichment modules (dorks, Wayback, GitHub, Reddit).",
    )
    return parser


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> None:
    """Orchestrate all OSINT modules and display collected data."""
    from src.data_display import build_data, display_rich, save_html, save_json
    from src.telegram_osint import fetch_profile
    from src.username_enum import run_sherlock

    identifier = args.username or args.phone

    # ── Telegram profile ──────────────────────────────────────────────────────
    console.print(f"\n[dim][*] Resolving Telegram profile for:[/] [cyan]{identifier}[/]")
    tg_identifier = f"@{identifier}" if args.username else identifier
    tg_profile = await fetch_profile(tg_identifier)

    # Derive username from resolved profile when a phone was supplied
    effective_username = args.username or (tg_profile.username if tg_profile else None)
    display_name = tg_profile.display_name if tg_profile else None

    # ── Sherlock username enumeration ─────────────────────────────────────────
    enum_result = None
    if effective_username and not args.skip_sherlock:
        console.print(f"[dim][*] Running Sherlock for username:[/] [cyan]{effective_username}[/]")
        enum_result = run_sherlock(effective_username)
    elif args.skip_sherlock:
        console.print("[dim][*] Sherlock skipped (--skip-sherlock).[/]")

    # ── Enrichment modules ────────────────────────────────────────────────────
    dork_result = wayback_result = github_result = reddit_result = None

    if effective_username and not args.skip_enrich:
        from src.github_enrich import fetch_github
        from src.google_dorks import run_dorks
        from src.reddit_enrich import fetch_reddit
        from src.wayback import check_wayback

        console.print(f"[dim][*] Running Google dorks for:[/] [cyan]{effective_username}[/]")
        dork_result = run_dorks(effective_username, display_name)

        sherlock_platforms = []
        if enum_result:
            sherlock_platforms = [
                p for p in (getattr(enum_result, "platforms", None) or [])
                # EnumResult.platforms may be a list of PlatformResult dataclasses
                # or already dicts — handle both
                if (p.found if hasattr(p, "found") else p.get("found"))
            ]
        console.print(
            f"[dim][*] Checking Wayback Machine "
            f"({len(sherlock_platforms) + 1} URL(s))...[/]"
        )
        wayback_result = check_wayback(effective_username, [
            {"platform": p.platform if hasattr(p, "platform") else p["platform"],
             "url": p.url if hasattr(p, "url") else p["url"],
             "found": True}
            for p in sherlock_platforms
        ])

        console.print(f"[dim][*] Fetching GitHub profile for:[/] [cyan]{effective_username}[/]")
        github_result = fetch_github(effective_username)

        console.print(f"[dim][*] Fetching Reddit profile for:[/] [cyan]{effective_username}[/]")
        reddit_result = fetch_reddit(effective_username)

    elif args.skip_enrich:
        console.print("[dim][*] Enrichment skipped (--skip-enrich).[/]")

    # ── Display and save ──────────────────────────────────────────────────────
    data = build_data(
        identifier,
        tg=tg_profile,
        enum=enum_result,
        dorks=dork_result,
        wayback=wayback_result,
        github=github_result,
        reddit=reddit_result,
    )
    display_rich(data)

    json_path = save_json(data, identifier)
    html_path = save_html(data, identifier)
    console.print(f"[dim][+] JSON saved:[/] {json_path}")
    console.print(f"[dim][+] HTML saved:[/] {html_path}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    _startup()

    parser = build_parser()
    args = parser.parse_args()

    # Consent gate — must be passed explicitly on the CLI
    if not args.consent:
        console.print(
            "[bold red]Error:[/] [red]--consent flag is REQUIRED.[/]\n"
            "You must explicitly acknowledge the ethical constraints "
            "before running this tool.\n"
        )
        sys.exit(1)

    # Interactive username prompt when no target was given on the CLI
    if not args.username and not args.phone:
        args.username = Prompt.ask(
            "\n[cyan]Enter Telegram username[/] [dim](without @)[/]"
        ).strip().lstrip("@")
        if not args.username:
            console.print("[red]No username provided. Exiting.[/]")
            sys.exit(1)

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        console.print("\n[yellow][!] Aborted by user.[/]")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[bold red][!] Fatal error:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
