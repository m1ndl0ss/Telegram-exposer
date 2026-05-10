# Telegram-Exposer

**Academic OSINT research tool** — master's thesis proof-of-concept showing what a stranger can learn about a Telegram account from a username or phone number alone, using only publicly available data.

> **Ethical notice:** Only use this tool on accounts you own or have explicit written consent to analyse. Unauthorised use may violate the CFAA, GDPR, and equivalent local laws.

---

## What it does

Given a Telegram username or phone number, the tool:

1. Resolves the account via the Telegram MTProto API (Telethon) and shows every public profile field, explicitly marking each as **VISIBLE**, **RESTRICTED**, or **NOT SET**.
2. Runs [Sherlock](https://github.com/sherlock-project/sherlock) to enumerate other platforms where the same username appears.
3. Saves a timestamped JSON dump of everything collected to `/reports/`.

No scoring, no interpretation — just the raw data a stranger could find.

---

## Modules

| File | Purpose |
|---|---|
| `src/telegram_osint.py` | Resolves username/phone to a public Telegram profile via Telethon |
| `src/username_enum.py` | Runs Sherlock as a subprocess, parses results into structured data |
| `src/data_display.py` | Formats output for human review and saves the JSON report |
| `main.py` | CLI entrypoint |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd Telegram-exposer
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install sherlock-project   # optional, for cross-platform username search
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in TELEGRAM_API_ID and TELEGRAM_API_HASH
```

| Variable | Where to get it |
|---|---|
| `TELEGRAM_API_ID` | https://my.telegram.org/apps |
| `TELEGRAM_API_HASH` | https://my.telegram.org/apps |

### 3. First run — Telethon login

On the first run Telethon will prompt for your phone number and a login code to create a local session file (`osint_session.session`). This is a standard MTProto authentication step.

---

## Usage

```
python main.py (--username USERNAME | --phone PHONE) [--skip-sherlock] --consent
```

The `--consent` flag is **mandatory**.

### Examples

```bash
# Lookup by username
python main.py --username johndoe --consent

# Lookup by phone number, skip Sherlock
python main.py --phone +1234567890 --consent --skip-sherlock
```

---

## Output

### CLI display

```
══════════════════════════════════════════════════════════════
  TELEGRAM EXPOSER — DATA DISPLAY
══════════════════════════════════════════════════════════════
  Identifier : johndoe
  Generated  : 2026-05-10T12:00:00+00:00

  ──────────────────────────────────────────────────────────
  [TELEGRAM PROFILE]
  ──────────────────────────────────────────────────────────
  Display name          [VISIBLE]       John Doe
  Username              [VISIBLE]       johndoe
  User ID               [VISIBLE]       123456789
  Bio                   [NOT SET]
  Phone                 [RESTRICTED]
  Last seen             [RESTRICTED]
  Profile photo         [VISIBLE]       reports/profile_photo.jpg
  Is bot                [VISIBLE]       no

  ──────────────────────────────────────────────────────────
  [CROSS-PLATFORM PRESENCE]
  ──────────────────────────────────────────────────────────
  Username found on 4 platform(s):

  GitHub                        https://github.com/johndoe
  Twitter                       https://twitter.com/johndoe
  ...
```

### Visibility labels

| Label | Meaning |
|---|---|
| `VISIBLE` | Value was returned by Telegram and is readable by anyone |
| `RESTRICTED` | Field exists on every account but is hidden by the owner's privacy settings |
| `NOT SET` | Optional field the account owner never populated |

### JSON report

Saved to `reports/report_<identifier>_<timestamp>.json`. Contains the full profile dict and Sherlock results. No other data is written.

---

## Project structure

```
Telegram-exposer/
├── main.py
├── requirements.txt
├── .env.example
├── reports/               # JSON reports saved here
└── src/
    ├── telegram_osint.py
    ├── username_enum.py
    └── data_display.py
```

---

## References

- Telethon documentation: https://docs.telethon.dev
- Sherlock project: https://github.com/sherlock-project/sherlock
