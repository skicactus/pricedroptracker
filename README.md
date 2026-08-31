# Depop Price Tracker

Two tools in one:

1. **Search** — find the cheapest listing on Depop matching a query, with a
   minimum-condition filter (e.g. "cheapest grey Polo Ralph Lauren shirt,
   Used - Good or better"), and get a direct link to it.
2. **Wishlist tracking** — sync your Depop account's liked items (or add
   specific listings by URL) and get alerted when any of them drop in price.

![Dashboard screenshot](docs/dashboard-screenshot.png)

## Why this isn't a generic requests+BeautifulSoup scraper

Depop sits behind Cloudflare's active JS challenge -- plain HTTP requests get
a "just a moment" bot-check page every time, no way around it. A real
browser gets through fine, so this project drives actual (headless) Chromium
via **Playwright** for every Depop interaction. That's heavier than a plain
HTTP scraper (a real browser download, ~3-5s per page instead of
milliseconds) but it's what actually works against a site trying to block
bots.

**Worth knowing:** this is automated interaction with a marketplace that
doesn't want to be scraped. It's the same category of thing as the personal
resale-tracking bots people already run against StockX/Depop/Grailed -- fine
for personal use at a reasonable pace, but it goes against the spirit of
Depop's ToS and could get you rate-limited if you hit it too aggressively.
Request rates here are kept conservative on purpose (see Known limitations).

## Setup

Requires Python 3.11+.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

> **If this folder lives in iCloud Drive** (as it does by default under
> `~/Library/Mobile Documents/com~apple~CloudDocs/...`), don't let the venv's
> thousands of small files sit there -- macOS will eventually evict them to
> free space, and Python will hang trying to read a cloud-only placeholder.
> Create the real venv somewhere local instead and symlink it in:
> ```bash
> python3 -m venv ~/.venvs/pricedroptracker
> ln -s ~/.venvs/pricedroptracker venv
> pip install -r requirements.txt
> playwright install chromium
> ```
> Everything else (`venv/bin/...`, `source venv/bin/activate`) works exactly
> the same through the symlink.

## Usage

### 1. Search for the cheapest listing (no login needed)

```bash
streamlit run dashboard.py
```

Go to the **Search Depop** tab, type what you're looking for, pick a minimum
condition, and hit search. Results are sorted cheapest-first (Depop's own
`sort=priceAscending`); click **Track this** on any result to start
monitoring its price.

### 2. Track your wishlist

To sync your actual Depop "likes" automatically, log in once:

```bash
python depop_login.py
```

This opens a **real, visible browser window on your machine** -- you type
your Depop username/password (and any 2FA) directly into it, never into this
script. Once you're logged in, press Enter in the terminal; your session is
saved to `data/depop_session.json` (gitignored, never committed -- treat it
like a password). Re-run this whenever the dashboard says your session has
expired.

After that, the **My Wishlist** tab's "Sync my Depop wishlist" button pulls
your liked items and starts tracking any new ones (threshold = the price
each item was at when synced, so you're alerted on any further drop). You
can also track a specific listing by pasting its URL, without needing to
have liked it on Depop at all.

### 3. Check prices from the command line / on a schedule

```bash
python tracker.py --once   # sync wishlist + check every tracked listing once
python tracker.py --loop   # repeat every POLL_INTERVAL_HOURS (default 6)
```

Prints a clear `*** PRICE DROP ***` line to the console for anything that's
dropped below its threshold. Optional email alerts via `smtplib` (off by
default):

```bash
export EMAIL_ENABLED=true
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USERNAME=you@gmail.com
export SMTP_PASSWORD=your-app-password
export ALERT_EMAIL_TO=you@gmail.com
```

## Tests

```bash
pytest
```

Covers the currency parser, condition-tier logic (`used_good` -> everything
at or above "Used - Good"), search-URL construction, and search-result-card
text parsing -- all pure logic, no network/browser needed. The live Depop
interaction (`depop_client.search`, `get_listing`, `get_wishlist`) was
verified manually against the real site rather than covered by automated
tests, since that would mean hitting Depop's live servers on every test run.

## Known limitations

- **Depop's own search relevance, not exact matching.** "Search" hands your
  query straight to Depop's search box, so results can include loosely
  related items (e.g. a search for a specific brand surfacing a different
  brand) -- same as searching on depop.com directly.
- **Wishlist sessions expire.** Depop's login cookies don't last forever;
  when they do, `tracker.py`/the dashboard will tell you to re-run
  `depop_login.py`.
- **No CAPTCHA solving.** If Depop serves a harder challenge than the
  standard JS check (e.g. after very heavy use), this won't get through it.
- **Rate limiting.** Don't hammer searches or checks; the default 6-hour
  poll interval for `--loop` is intentionally conservative.
- **Sold listings.** A tracked item that sells out is skipped (logged as
  unavailable) rather than erroring, but it isn't automatically removed from
  your tracked list.
