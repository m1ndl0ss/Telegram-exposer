"""
data_display.py
~~~~~~~~~~~~~~~
Format and save all collected OSINT data.

Terminal output uses Rich (panels, tables, colour-coded badges).
Two report files are saved per run:
  - reports/report_<id>_<ts>.json  — raw data for programmatic use
  - reports/report_<id>_<ts>.html  — styled self-contained HTML for human review

Telegram visibility labels:
  VISIBLE    – value was returned and is publicly readable.
  RESTRICTED – field always exists on every account but is hidden by privacy settings.
  NOT SET    – optional field the account owner never populated.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
_ALWAYS_EXISTS = {"phone", "last_seen"}

console = Console()

# ── Visibility helpers ────────────────────────────────────────────────────────

def _visibility(field: str, value: Any) -> str:
    if value is not None and value is not False and value != "" and value != "hidden":
        return "VISIBLE"
    if field in _ALWAYS_EXISTS or value == "hidden":
        return "RESTRICTED"
    return "NOT SET"


def _badge_rich(vis: str) -> Text:
    colours = {"VISIBLE": "bold green", "RESTRICTED": "bold yellow", "NOT SET": "dim white"}
    return Text(f" {vis} ", style=colours.get(vis, "white"))


def _badge_html(vis: str) -> str:
    styles = {
        "VISIBLE":    "background:#198754;color:#fff",
        "RESTRICTED": "background:#fd7e14;color:#fff",
        "NOT SET":    "background:#6c757d;color:#fff",
    }
    return (
        f'<span style="padding:2px 8px;border-radius:4px;'
        f'font-size:.8em;font-weight:600;{styles.get(vis, "")}">{vis}</span>'
    )


def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    return obj

# ── Data assembly ─────────────────────────────────────────────────────────────

def build_data(
    identifier: str,
    tg=None,
    enum=None,
    dorks=None,
    wayback=None,
    github=None,
    reddit=None,
    bio_link=None,
) -> dict:
    """Assemble all module outputs into a single report dict."""
    return {
        "meta": {
            "tool": "Telegram-Exposer (academic research)",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "identifier": identifier,
        },
        "telegram_profile":     _to_dict(tg),
        "username_enumeration": _to_dict(enum),
        "bio_link":             _to_dict(bio_link),
        "google_dorks":         _to_dict(dorks),
        "wayback":              _to_dict(wayback),
        "github":               _to_dict(github),
        "reddit":               _to_dict(reddit),
    }

# ── Persistence ───────────────────────────────────────────────────────────────

def _report_stem(identifier: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_+" else "_" for c in identifier)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"report_{safe}_{ts}"


def save_json(data: dict, identifier: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{_report_stem(identifier)}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_html(data: dict, identifier: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{_report_stem(identifier)}.html"
    path.write_text(_render_html(data), encoding="utf-8")
    return path

# ── HTML rendering ────────────────────────────────────────────────────────────

_PROFILE_FIELDS = [
    ("display_name",      "Display name"),
    ("username",          "Username"),
    ("user_id",           "User ID"),
    ("bio",               "Bio"),
    ("phone",             "Phone"),
    ("last_seen",         "Last seen"),
    ("profile_photo_url", "Profile photo"),
    ("is_bot",            "Is bot"),
]


def _h2(title: str, section_id: str) -> str:
    return f'<section id="{section_id}"><h2>{title}</h2>'


def _html_telegram_section(tg: dict) -> str:
    rows = ""
    for key, label in _PROFILE_FIELDS:
        raw = tg.get(key)
        if key == "is_bot":
            vis, val = "VISIBLE", "yes" if raw else "no"
        else:
            vis = _visibility(key, raw)
            val = str(raw) if vis == "VISIBLE" else ""
        rows += (
            f"<tr><td>{label}</td>"
            f"<td style='text-align:center'>{_badge_html(vis)}</td>"
            f"<td>{val}</td></tr>\n"
        )
    if tg.get("restricted"):
        reasons = ", ".join(tg.get("restriction_reasons") or ["unspecified"])
        rows += f"<tr><td colspan='3' class='warn'>⚠ Platform-restricted: {reasons}</td></tr>\n"
    for err in tg.get("raw_errors") or []:
        rows += f"<tr><td colspan='3' class='warn'>⚠ {err}</td></tr>\n"
    return (
        _h2("Telegram Profile", "telegram") +
        "<table><thead><tr><th>Field</th><th>Visibility</th><th>Value</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _html_bio_link_section(bio: dict) -> str:
    if not bio:
        return ""
    if bio.get("error"):
        return (
            _h2("Biography Link", "bio-link") +
            f"<p class='note'>Source: <span class='mono'>{bio.get('source_url','')}</span></p>"
            f"<p class='warn'>{bio['error']}</p></section>"
        )
    rows = ""
    for label, val in [
        ("Source URL",       bio.get("source_url")),
        ("Final URL",        bio.get("final_url")),
        ("Page title",       bio.get("page_title")),
        ("Meta description", bio.get("meta_description")),
    ]:
        if val:
            rows += f"<tr><td>{label}</td><td>{val}</td></tr>\n"
    for label, items in [
        ("Emails found",  bio.get("emails") or []),
        ("Phones found",  bio.get("phones") or []),
    ]:
        if items:
            joined = ", ".join(str(i) for i in items)
            rows += f"<tr><td class='warn'>{label}</td><td>{joined}</td></tr>\n"
    social = bio.get("social_links") or []
    if social:
        links = " &nbsp; ".join(
            f"<a href='{s['url']}' target='_blank'>{s['platform']}</a>" for s in social
        )
        rows += f"<tr><td>Social links</td><td>{links}</td></tr>\n"
    return (
        _h2("Biography Link", "bio-link") +
        "<table><thead><tr><th>Field</th><th>Value</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _html_dorks_section(dorks: dict) -> str:
    if not dorks:
        return ""
    if dorks.get("error"):
        return _h2("Google Dork Results", "dorks") + f"<p class='note'>{dorks['error']}</p></section>"
    out = _h2("Google Dork Results", "dorks")
    for q in dorks.get("queries") or []:
        out += f"<h3 class='query'>{q['query']}</h3>"
        hits = q.get("hits") or []
        if not hits:
            out += "<p class='note'>No results.</p>"
        else:
            out += "<table><thead><tr><th>Title</th><th>URL</th><th>Snippet</th></tr></thead><tbody>"
            for h in hits:
                out += (
                    f"<tr><td>{h['title']}</td>"
                    f"<td><a href='{h['url']}' target='_blank'>{h['url']}</a></td>"
                    f"<td class='snippet'>{h['snippet']}</td></tr>\n"
                )
            out += "</tbody></table>"
    return out + "</section>"


def _html_wayback_section(wb: dict) -> str:
    if not wb:
        return ""
    if wb.get("error"):
        return _h2("Wayback Machine", "wayback") + f"<p class='note'>{wb['error']}</p></section>"
    records = wb.get("records") or []
    if not records:
        return _h2("Wayback Machine", "wayback") + "<p class='note'>No records found.</p></section>"
    rows = ""
    for r in records:
        earliest = r.get("earliest_date") or "—"
        latest   = r.get("latest_snapshot_url") or ""
        latest_cell = f"<a href='{latest}' target='_blank'>view</a>" if latest else "—"
        rows += (
            f"<tr><td>{r['platform']}</td>"
            f"<td><span class='mono'>{r['checked_url']}</span></td>"
            f"<td>{earliest}</td><td>{latest_cell}</td>"
            f"<td style='text-align:center'>{r.get('total_sampled', 0)}</td></tr>\n"
        )
    return (
        _h2("Wayback Machine", "wayback") +
        "<table><thead><tr>"
        "<th>Platform</th><th>Checked URL</th><th>Earliest</th>"
        "<th>Latest (sampled)</th><th>Snapshots</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _html_github_section(gh: dict) -> str:
    if not gh:
        return ""
    if gh.get("not_found"):
        return _h2("GitHub Profile", "github") + "<p class='note'>Account not found on GitHub.</p></section>"
    if gh.get("error"):
        return _h2("GitHub Profile", "github") + f"<p class='note'>{gh['error']}</p></section>"
    fields = [
        ("name", "Name"), ("email", "Email"), ("bio", "Bio"),
        ("company", "Company"), ("location", "Location"), ("blog", "Blog / Website"),
        ("public_repos", "Public repos"), ("followers", "Followers"),
    ]
    empty = "<span class='note'>—</span>"
    rows = "".join(
        f"<tr><td>{label}</td><td>{gh.get(key) or empty}</td></tr>\n"
        for key, label in fields
    )
    commit_emails = gh.get("commit_emails") or []
    if commit_emails:
        joined = "<br>".join(commit_emails)
        rows += f"<tr><td>Emails (commits)</td><td>{joined}</td></tr>\n"
    return (
        _h2("GitHub Profile", "github") +
        "<table><thead><tr><th>Field</th><th>Value</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _html_reddit_section(reddit: dict) -> str:
    if not reddit:
        return ""
    if reddit.get("not_found"):
        return _h2("Reddit Profile", "reddit") + "<p class='note'>Account not found on Reddit.</p></section>"
    if reddit.get("error"):
        return _h2("Reddit Profile", "reddit") + f"<p class='note'>{reddit['error']}</p></section>"
    stats = [
        ("Account age",    f"{reddit.get('account_age_days', '—')} days"),
        ("Comment karma",  reddit.get("comment_karma", "—")),
        ("Post karma",     reddit.get("post_karma", "—")),
        ("Verified email", "yes" if reddit.get("verified_email") else "no"),
    ]
    rows = "".join(
        f"<tr><td>{label}</td><td>{val}</td></tr>\n" for label, val in stats
    )
    pii_rows = ""
    for label, items in [
        ("Emails found",    reddit.get("found_emails") or []),
        ("Phones found",    reddit.get("found_phones") or []),
        ("Locations found", reddit.get("found_locations") or []),
    ]:
        if items:
            pii_rows += f"<tr><td class='warn'>{label}</td><td>{'<br>'.join(str(i) for i in items)}</td></tr>\n"
    if not pii_rows:
        pii_rows = "<tr><td colspan='2' class='note'>No PII patterns found in recent comments.</td></tr>\n"
    return (
        _h2("Reddit Profile", "reddit") +
        "<h3 class='subhead'>Account Stats</h3>"
        f"<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table>"
        "<h3 class='subhead'>PII in Comments</h3>"
        f"<table><thead><tr><th>Type</th><th>Values</th></tr></thead><tbody>{pii_rows}</tbody></table>"
        "</section>"
    )


_HTML_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117;
         color: #c9d1d9; line-height: 1.6; padding: 2rem; max-width: 1100px; margin: 0 auto; }
  header { border-bottom: 1px solid #30363d; padding-bottom: 1.5rem; margin-bottom: 2rem; }
  header h1 { font-size: 2rem; color: #e63946; letter-spacing: .15em; }
  header .tagline { color: #8b949e; font-size: .9rem; margin-top: .25rem; }
  header .meta { margin-top: .75rem; font-size: .85rem; color: #8b949e; display: flex;
                 gap: 2rem; flex-wrap: wrap; }
  section { margin-bottom: 2.5rem; }
  h2 { font-size: 1.05rem; text-transform: uppercase; letter-spacing: .1em; color: #58a6ff;
       border-bottom: 1px solid #30363d; padding-bottom: .4rem; margin-bottom: 1rem; margin-top: .5rem; }
  h3.subhead { font-size: .9rem; color: #8b949e; margin: 1rem 0 .5rem; font-weight: 600; }
  h3.query { font-size: .85rem; color: #8b949e; margin: 1.2rem 0 .4rem;
             font-family: monospace; background: #161b22; padding: .3rem .6rem;
             border-left: 3px solid #58a6ff; }
  table { width: 100%; border-collapse: collapse; font-size: .875rem; margin-bottom: .5rem; }
  th { text-align: left; padding: .5rem .75rem; background: #161b22;
       color: #8b949e; font-weight: 600; border-bottom: 1px solid #30363d; }
  td { padding: .5rem .75rem; border-bottom: 1px solid #21262d; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .note { color: #8b949e; font-style: italic; }
  .warn { color: #f85149; }
  .snippet { color: #8b949e; font-size: .8rem; }
  .mono { font-family: monospace; font-size: .8rem; color: #8b949e; }
  code { font-family: monospace; font-size: .8rem; background: #161b22;
         padding: 1px 5px; border-radius: 3px; color: #e2a96e; }
  footer { margin-top: 3rem; border-top: 1px solid #30363d; padding-top: 1rem;
           font-size: .8rem; color: #484f58; }
"""


def _render_html(data: dict) -> str:
    meta     = data["meta"]
    tg       = data.get("telegram_profile") or {}
    en       = data.get("username_enumeration") or {}
    dorks    = data.get("google_dorks")
    wb       = data.get("wayback")
    gh       = data.get("github")
    reddit   = data.get("reddit")
    bio_link = data.get("bio_link")

    # Cross-platform presence section
    found = [p for p in (en.get("platforms") or []) if p.get("found")]
    variants_searched = en.get("variants_searched") or []
    if en.get("error"):
        platform_body = f"<p class='note'>{en['error']}</p>"
    elif found:
        rows = "".join(
            f"<tr><td>{p['platform']}</td>"
            f"<td><a href='{p['url']}' target='_blank'>{p['url']}</a></td>"
            f"<td><span class='mono'>{p.get('variant', '')}</span></td></tr>\n"
            for p in found
        )
        variants_note = ""
        if variants_searched:
            variants_note = (
                f"<p class='note' style='margin-bottom:.5rem'>"
                f"Leet variants also searched: "
                + ", ".join(f"<code>{v}</code>" for v in variants_searched)
                + "</p>"
            )
        platform_body = (
            f"{variants_note}"
            f"<p style='margin-bottom:.75rem'>Found on <strong>{len(found)}</strong> platform(s).</p>"
            "<table><thead><tr><th>Platform</th><th>URL</th><th>Found via</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        platform_body = "<p class='note'>No platforms found (or Sherlock was skipped).</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TG-Exposer — {meta['identifier']}</title>
<style>{_HTML_CSS}</style>
</head>
<body>
<header>
  <h1>TG-EXPOSER</h1>
  <p class="tagline">OSINT identity linkage research tool | academic use only</p>
  <div class="meta">
    <span>Identifier: <strong>{meta['identifier']}</strong></span>
    <span>Generated: {meta['generated_at']}</span>
  </div>
</header>

{_html_telegram_section(tg)}

<section id="cross-platform">
  <h2>Cross-Platform Presence</h2>
  {platform_body}
</section>

{_html_bio_link_section(bio_link)}
{_html_dorks_section(dorks)}
{_html_wayback_section(wb)}
{_html_github_section(gh)}
{_html_reddit_section(reddit)}

<footer>Generated by Telegram-Exposer &mdash; academic research only. No liability accepted for misuse.</footer>
</body>
</html>"""

# ── Rich terminal display ─────────────────────────────────────────────────────

def display_rich(data: dict) -> None:
    """Render all collected data to the terminal using Rich panels and tables."""
    meta     = data["meta"]
    tg       = data.get("telegram_profile") or {}
    en       = data.get("username_enumeration") or {}
    dorks    = data.get("google_dorks")
    wb       = data.get("wayback")
    gh       = data.get("github")
    reddit   = data.get("reddit")
    bio_link = data.get("bio_link")

    console.print()
    console.print(Panel(
        f"[dim]Identifier:[/] [bold cyan]{meta['identifier']}[/]\n"
        f"[dim]Generated :[/] {meta['generated_at']}",
        title="[bold red]TG-EXPOSER[/] [dim]— data display[/]",
        border_style="red",
    ))

    # ── Telegram profile ──────────────────────────────────────────────────────
    tbl = Table(show_header=True, header_style="bold cyan", border_style="dim",
                expand=True, show_lines=True)
    tbl.add_column("Field",      style="white",    min_width=16)
    tbl.add_column("Visibility", justify="center", min_width=14)
    tbl.add_column("Value",      style="white")
    for key, label in _PROFILE_FIELDS:
        raw = tg.get(key)
        if key == "is_bot":
            vis, val = "VISIBLE", "yes" if raw else "no"
        else:
            vis = _visibility(key, raw)
            val = str(raw) if vis == "VISIBLE" else ""
        tbl.add_row(label, _badge_rich(vis), val)
    for err in tg.get("raw_errors") or []:
        tbl.add_row("", Text(""), Text(f"⚠ {err}", style="red"))
    console.print(Panel(tbl, title="[bold cyan]TELEGRAM PROFILE[/]", border_style="cyan"))
    if tg.get("restricted"):
        reasons = ", ".join(tg.get("restriction_reasons") or ["unspecified"])
        console.print(f"  [yellow]⚠ Platform-restricted:[/] {reasons}\n")

    # ── Bio link ──────────────────────────────────────────────────────────────
    if bio_link:
        if bio_link.get("error"):
            bl_content: Any = Text(
                f"{bio_link.get('source_url','')}  —  {bio_link['error']}", style="yellow"
            )
        else:
            blt = Table(show_header=True, header_style="bold cyan", border_style="dim",
                        expand=True, show_lines=True)
            blt.add_column("Field", style="white",    min_width=20)
            blt.add_column("Value", style="cyan dim")
            for label, val in [
                ("Source URL",       bio_link.get("source_url")),
                ("Page title",       bio_link.get("page_title")),
                ("Meta description", bio_link.get("meta_description")),
            ]:
                if val:
                    blt.add_row(label, str(val))
            for addr in bio_link.get("emails") or []:
                blt.add_row(Text("Email found", style="bold yellow"), Text(addr, style="bold yellow"))
            for phone in bio_link.get("phones") or []:
                blt.add_row(Text("Phone found", style="bold yellow"), Text(phone, style="bold yellow"))
            for sl in bio_link.get("social_links") or []:
                blt.add_row(sl["platform"], sl["url"])
            bl_content = blt
        console.print(Panel(bl_content, title="[bold cyan]BIOGRAPHY LINK[/]", border_style="cyan"))

    # ── Cross-platform presence ───────────────────────────────────────────────
    found = [p for p in (en.get("platforms") or []) if p.get("found")]
    variants_searched = en.get("variants_searched") or []
    if en.get("error"):
        cp_content: Any = Text(en["error"], style="dim")
    elif found:
        pt = Table(show_header=True, header_style="bold cyan", border_style="dim",
                   expand=True, show_lines=True)
        pt.add_column("Platform",  style="white",   min_width=22)
        pt.add_column("URL",       style="cyan dim")
        pt.add_column("Found via", style="dim",     min_width=14)
        for p in found:
            pt.add_row(p["platform"], p["url"], p.get("variant", ""))
        cp_content = pt
        if variants_searched:
            also = ", ".join(variants_searched)
            console.print(f"  [dim]Leet variants searched:[/] [dim italic]{also}[/]")
    else:
        cp_content = Text("No platforms found (or Sherlock was skipped).", style="dim")
    console.print(Panel(
        cp_content,
        title=f"[bold cyan]CROSS-PLATFORM PRESENCE[/] [dim]({len(found)} found)[/]",
        border_style="cyan",
    ))

    # ── Google dorks ──────────────────────────────────────────────────────────
    if dorks:
        dt = Table(show_header=True, header_style="bold cyan", border_style="dim",
                   expand=True, show_lines=True)
        dt.add_column("Query",   style="dim",      min_width=30)
        dt.add_column("Title",   style="white",    min_width=24)
        dt.add_column("URL",     style="cyan dim")
        for q in dorks.get("queries") or []:
            hits = q.get("hits") or []
            if not hits:
                dt.add_row(q["query"], Text("no results", style="dim"), "")
            for i, h in enumerate(hits):
                dt.add_row(q["query"] if i == 0 else "", h["title"], h["url"])
        console.print(Panel(dt, title="[bold cyan]GOOGLE DORK RESULTS[/]", border_style="cyan"))

    # ── Wayback Machine ───────────────────────────────────────────────────────
    if wb:
        wt = Table(show_header=True, header_style="bold cyan", border_style="dim",
                   expand=True, show_lines=True)
        wt.add_column("Platform",        style="white",   min_width=20)
        wt.add_column("Earliest",        style="green",   min_width=12)
        wt.add_column("Latest (sample)", style="cyan dim")
        for r in wb.get("records") or []:
            earliest = r.get("earliest_date") or Text("none", style="dim")
            latest   = r.get("latest_snapshot_url") or Text("none", style="dim")
            wt.add_row(r["platform"], str(earliest), str(latest))
        console.print(Panel(wt, title="[bold cyan]WAYBACK MACHINE[/]", border_style="cyan"))

    # ── GitHub profile ────────────────────────────────────────────────────────
    if gh:
        if gh.get("not_found"):
            gh_content: Any = Text("Account not found on GitHub.", style="dim")
        elif gh.get("error"):
            gh_content = Text(gh["error"], style="yellow")
        else:
            ght = Table(show_header=True, header_style="bold cyan", border_style="dim",
                        expand=True, show_lines=True)
            ght.add_column("Field", style="white",    min_width=18)
            ght.add_column("Value", style="cyan dim")
            for key, label in [
                ("name","Name"),("email","Email"),("bio","Bio"),
                ("company","Company"),("location","Location"),("blog","Blog"),
                ("public_repos","Public repos"),("followers","Followers"),
            ]:
                val = gh.get(key)
                ght.add_row(label, str(val) if val is not None else Text("—", style="dim"))
            for addr in gh.get("commit_emails") or []:
                ght.add_row("Email (commit)", Text(addr, style="bold yellow"))
            gh_content = ght
        console.print(Panel(gh_content, title="[bold cyan]GITHUB PROFILE[/]", border_style="cyan"))

    # ── Reddit profile ────────────────────────────────────────────────────────
    if reddit:
        if reddit.get("not_found"):
            rd_content: Any = Text("Account not found on Reddit.", style="dim")
        elif reddit.get("error"):
            rd_content = Text(reddit["error"], style="yellow")
        else:
            rdt = Table(show_header=True, header_style="bold cyan", border_style="dim",
                        expand=True, show_lines=True)
            rdt.add_column("Field", style="white",    min_width=20)
            rdt.add_column("Value", style="cyan dim")
            rdt.add_row("Account age (days)", str(reddit.get("account_age_days") or "—"))
            rdt.add_row("Comment karma",      str(reddit.get("comment_karma") or "—"))
            rdt.add_row("Post karma",         str(reddit.get("post_karma") or "—"))
            rdt.add_row("Verified email",     "yes" if reddit.get("verified_email") else "no")
            for label, items in [
                ("Emails found",    reddit.get("found_emails") or []),
                ("Phones found",    reddit.get("found_phones") or []),
                ("Locations found", reddit.get("found_locations") or []),
            ]:
                if items:
                    rdt.add_row(
                        Text(label, style="bold yellow"),
                        Text(", ".join(str(i) for i in items), style="bold yellow"),
                    )
            if not any([reddit.get("found_emails"), reddit.get("found_phones"), reddit.get("found_locations")]):
                rdt.add_row(Text("PII in comments", style="dim"), Text("none found", style="dim"))
            rd_content = rdt
        console.print(Panel(rd_content, title="[bold cyan]REDDIT PROFILE[/]", border_style="cyan"))
