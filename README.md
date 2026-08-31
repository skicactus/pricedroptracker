# Depop Price Tracker

Three tools in one:

1. **Search** — find the cheapest listing on Depop matching a query, with a
   minimum-condition filter (e.g. "cheapest grey Polo Ralph Lauren shirt,
   Used - Good or better"), and get a direct link to it.
2. **Wishlist tracking** — sync your Depop account's liked items (or add
   specific listings by URL) and get alerted when any of them drop in price.
3. **Cheaper alternatives** — for anything you're tracking, search Depop by
   its title and surface other sellers' listings priced lower than what
   you're tracking it at.

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
> `~/Library/Mobile Documents/com~apple~CloudDocs/...`), keep the venv
> **fully outside it** -- don't even symlink one in. Two different failure
> modes were hit building this: with the venv's thousands of small files
> sitting directly in the synced folder, macOS eventually evicts them to
> free space and Python hangs reading a cloud-only placeholder; a symlink
> pointing back out to a local venv avoids that, but iCloud's own
> conflict-resolution for symlinks-vs-directories is buggy -- it can spin up
> a phantom duplicate copy (e.g. a stray "venv 2") that iCloud endlessly
> retries syncing, and the resulting file-coordination locking stalls
> `git status`/`git commit` for the whole repo. The only setup that avoided
> both:
> ```bash
> python3 -m venv ~/.venvs/pricedroptracker
> source ~/.venvs/pricedroptracker/bin/activate
> pip install -r requirements.txt
> playwright install chromium
> ```
> Run everything (`streamlit run dashboard.py`, `pytest`, `python tracker.py`)
> from inside this project folder with that venv activated -- there's just no
> `venv/` inside the project directory at all, nothing for iCloud to trip on.

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

- **Depop's own search relevance, not exact matching.** "Search" and
  "Cheaper alternatives" both hand a text query straight to Depop's search
  box, so results can include loosely related items (e.g. a search for a
  specific brand surfacing a different brand) -- same as searching on
  depop.com directly. There's no SKU/UPC matching on a resale marketplace,
  so "alternatives" means similar listings from other sellers, not
  guaranteed-identical items.
- **Each search drives a fresh headless browser.** Expect roughly 10-40
  seconds per search or alternatives lookup depending on system load --
  there's no shared browser instance kept warm between requests.
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
