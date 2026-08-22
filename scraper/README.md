# Jio event scraper

Keeps a CSV of real, dated, bookable senior activities current, sourced from
**onepa.gov.sg** (People's Association). Output matches the `Event` schema in
[`product-spec.md` §12](../product-spec.md).

## Why onePA only

During manual research (see [`../events_seed.csv`](../events_seed.csv)) we checked
every source named in the product spec plus several national programmes
(ActiveSG, AIC/AAC operators, RSVP Singapore, giving.sg, volunteer.gov.sg,
CDCs). Only onePA reliably publishes, on individual pages, all of: a real
date/time, a fee, a registration status, and a stable public URL — for
thousands of listings, nationwide, via a public sitemap with no login wall.

The others are real gaps, not oversights:
- **NTUC Health, THK, TOUCH, St Luke's ElderCare, Lions Befrienders, the
  CDCs** — describe programme *types* generically; no page publishes a dated,
  linkable calendar entry.
- **ActiveSG** — pricing/membership pages are public, but actual class
  timetables sit behind a SingPass-gated booking portal
  (`members.myactivesg.com`) that can't be scraped anonymously.
- **giving.sg** — has real dated listings, but the page is fully
  React/JS-rendered; a plain HTTP fetch returns an empty shell. Scraping it
  would need a headless browser (e.g. Playwright), not implemented here.
- **volunteer.gov.sg** — server-rendered (old ASP.NET/Sitefinity stack, no
  sitemap, no embedded JSON), so listings must be scraped as HTML per search
  query. Not implemented yet — see "Extending" below.

So this scraper covers **attendance-type activities** (courses, interest
groups, community events) well. It does **not** cover **volunteer/mentoring
roles** — those still need to come from the manually curated rows in
`events_seed.csv` (Lions Befrienders, THK micro-jobbers, SG Cares VCs, RSVP
Singapore, etc.), or a future volunteer.gov.sg/giving.sg scraper.

## How it works

onePA pages are Next.js apps, but each ships its full listing record
server-side inside a `__NEXT_DATA__` JSON blob in the HTML — no JS execution
needed. `scraper/onepa.py`:

1. Reads onePA's public `sitemap.xml` to find the course / event /
   interest-group sub-sitemaps (URLs change on every deploy via a `?rev=`
   query param, so the index is always re-fetched).
2. Pre-filters sitemap URLs by slug keyword (`senior`, `healthiersg`,
   `qigong`, `tai-chi`, ...) so a run doesn't have to fetch all ~4,600+ course
   pages plus events and interest groups every time. Pass `--exhaustive` to
   disable this and crawl everything (slow, but catches senior-relevant
   listings whose slug happens not to contain a keyword).
3. Fetches each candidate page and parses its embedded product record.
4. Confirms relevance: course/interest-group pages carry a structured
   `TargetCustomerSegments` field (checked for "Senior Citizens"); event pages
   don't have that field, so relevance falls back to keyword matching in the
   title/description.
5. Normalises into the `Event` schema and upserts into a CSV, keyed by onePA's
   product code so re-runs update existing rows instead of duplicating them.

**Known data-quality caveat:** onePA's own `TargetCustomerSegments` tag is
broader than "suitable for a 60-70 year old" — e.g. a Krav Maga self-defence
class showed up tagged "Senior Citizens" alongside "Adults" under the
HealthierSG umbrella. Treat the scraper's output as "PA says a senior *could*
book this," not as a pre-vetted, mobility-appropriate list — Jio's suggestion
engine should still filter by activity type before offering it to a specific
profile.

## Usage

```bash
cd event_scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 cli.py --out events_scraped.csv          # normal run (slug pre-filtered)
python3 cli.py --limit 20 --out /tmp/smoke.csv    # quick smoke test
python3 cli.py --exhaustive --out events_scraped.csv   # slow, full crawl
```

Output columns match `events_seed.csv` exactly, so the two can be merged (or
loaded into the same database table) directly.

## Rate limiting (important)

onePA is served behind an Imperva Incapsula WAF. Repeated or rapid runs
against it from the same IP get bot-challenged: Incapsula returns a `200 OK`
containing a small JS challenge page instead of real content -- not a 403 or
429, so a plain status-code check won't catch it. `scraper/onepa.py` detects
this by body signature (`_is_bot_challenge`) and raises `BotChallengeError`
loudly rather than silently returning zero results, which is what happened
the first few times this was hit during development.

**If you see `BotChallengeError`: stop and wait** (tens of minutes, not
seconds/a minute) before the next run. Retrying immediately just extends the
challenge window. Keep runs infrequent (the scheduled nightly job below is
the right cadence) and don't run ad-hoc smoke tests back-to-back against the
live site while developing -- test the parsing logic against a handful of
already-known URLs instead of re-discovering + re-fetching everything.

## Keeping it current

This is a script, not a running service — schedule it to re-run periodically
rather than running once. Two ways to do that:

- **Claude's scheduled-tasks tool** (`mcp__scheduled-tasks__create_scheduled_task`)
  — ask Claude to "run the event scraper daily" and it will wire up a cron
  entry that runs `cli.py` and reports what changed.
- **A plain cron job** on whatever server hosts the bot:
  ```
  0 6 * * * cd /path/to/event_scraper && .venv/bin/python3 cli.py --out /path/to/events_scraped.csv
  ```

Either way, re-running is safe — it upserts by id, so nothing is duplicated,
and rows for listings that later close registration still update in place
(the `recurrence` field's registration-status suffix will flip to "closed").

## Extending to other sources

- **volunteer.gov.sg** — server-rendered HTML, has a search results page per
  query string; would need a BeautifulSoup-based listing-page parser (no
  embedded JSON like onePA). Good next target since it's the best public
  source for actual volunteer *roles*, not just attendance.
- **giving.sg** — needs Playwright (`pip install playwright && playwright
  install chromium`) to render the page before parsing, since content never
  appears in the raw HTML response.
- **ActiveSG class timetables** — not scrapable anonymously; would need a
  logged-in session (SingPass/ActiveSG account) or a manual quarterly export,
  which is a product/ops decision, not just an engineering one.
