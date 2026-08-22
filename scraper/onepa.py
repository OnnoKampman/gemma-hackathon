"""Scraper for onepa.gov.sg (People's Association) course, event and interest-group pages.

onePA is the only source found (see events_seed.csv research) that reliably
publishes structured, real dates/times/fees/registration status for individual
listings. Each page is a Next.js app, but ships its full product record
server-side inside a `__NEXT_DATA__` JSON blob -- no headless browser needed.

Discovery uses onePA's public sitemap (course / event / interest-group), which
lists every live listing URL. There is no public API to filter server-side by
"seniors", so relevance is determined client-side after fetching each page:
  - Class / InterestGroup pages carry a structured `TargetCustomerSegments`
    field -- checked directly for "Senior Citizens".
  - Event pages do not carry that field; relevance falls back to keyword
    matching against the title/description/URL slug.

To keep the request count sane (the course sitemap alone lists ~4,600 URLs),
callers should pass `slug_keywords` to pre-filter sitemap URLs before any page
is fetched. This trades a small false-negative rate (a senior-relevant course
whose slug happens not to contain any keyword) for not fetching thousands of
irrelevant pages every run. Widen or drop `slug_keywords` for a more
exhaustive (slower) pass.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

import requests

from .models import Event

USER_AGENT = "JioEventScraper/1.0 (+hackathon research bot; contact via project README)"
SITEMAP_INDEX = "https://www.onepa.gov.sg/sitemap.xml"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

# Sitemaps we care about -- facility (venue booking) and outlets/content are
# not event listings and are skipped.
RELEVANT_SITEMAPS = ("sitemap-course.xml", "sitemap-event.xml", "sitemap-ig.xml")

DEFAULT_SLUG_KEYWORDS = (
    "senior",
    "elderly",
    "active-ager",
    "healthiersg",  # PA's senior-health course line found in research
    "qigong",
    "tai-chi",
    "taichi",
    "line-dance",
    "chi-kung",
)

SENIOR_TEXT_KEYWORDS = (
    "senior",
    "elderly",
    "active ager",
    "50 year",
    "50+",
    "55 year",
    "60 year",
    "aged 50",
    "aged 55",
    "aged 60",
)


class FetchError(Exception):
    pass


class BotChallengeError(FetchError):
    """onePA is served behind Imperva Incapsula. Under suspected bot traffic it
    returns a 200 OK containing a JS challenge page instead of real content --
    a plain status-code check does not catch this, so it's detected by body
    signature instead. Seen in practice after a burst of rapid, repeated runs
    against the same IP in a short window; the fix is to wait (tens of
    minutes, not seconds) and resume at a conservative pace, not to retry
    immediately -- retrying into an active challenge just extends it."""


def _is_bot_challenge(resp: requests.Response) -> bool:
    if len(resp.content) > 2000:
        return False
    return "_Incapsula_Resource" in resp.text or "noindex,nofollow" in resp.text


def _get(
    session: requests.Session, url: str, timeout: int = 20, retries: int = 3
) -> requests.Response:
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if resp.status_code in (403, 429, 502, 503, 504):
                raise requests.HTTPError(f"{resp.status_code} on {url}", response=resp)
            if _is_bot_challenge(resp):
                raise BotChallengeError(
                    f"Incapsula bot challenge served for {url} -- back off and retry later, "
                    "not immediately."
                )
            resp.raise_for_status()
            return resp
        except (requests.RequestException, BotChallengeError) as exc:
            last_error = exc
            if isinstance(exc, BotChallengeError):
                raise  # no point retrying a challenge page within the same run
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)  # 2s, 4s, 8s
    assert last_error is not None
    raise last_error


def discover_sitemap_urls(session: requests.Session) -> list[str]:
    """Return the concrete sitemap URLs (with cache-busting `rev` query) from the index."""
    resp = _get(session, SITEMAP_INDEX)
    locs = re.findall(r"<loc>(.*?)</loc>", resp.text)
    return [loc for loc in locs if any(name in loc for name in RELEVANT_SITEMAPS)]


def discover_listing_urls(
    session: requests.Session,
    slug_keywords: Optional[Iterable[str]] = DEFAULT_SLUG_KEYWORDS,
) -> Iterator[str]:
    """Yield onePA listing URLs from the course/event/ig sitemaps.

    If `slug_keywords` is given, only URLs whose slug contains at least one
    keyword (case-insensitive) are yielded. Pass `None` for an exhaustive
    (much slower) crawl of every listing on the site.
    """
    for sitemap_url in discover_sitemap_urls(session):
        resp = _get(session, sitemap_url, timeout=30)
        urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
        for url in urls:
            if slug_keywords is None or any(kw in url.lower() for kw in slug_keywords):
                yield url


def _find_current_product(node) -> Optional[dict]:
    """Depth-first search for the `currentProduct` field embedded by Sitecore/PACES."""
    if isinstance(node, dict):
        if "currentProduct" in node:
            return node["currentProduct"]
        for value in node.values():
            found = _find_current_product(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_current_product(value)
            if found is not None:
                return found
    return None


def fetch_product(session: requests.Session, url: str) -> Optional[dict]:
    """Fetch a listing page and return its raw product dict, or None if not found."""
    resp = _get(session, url)
    match = NEXT_DATA_RE.search(resp.text)
    if not match:
        return None
    data = json.loads(match.group(1))
    current_product = _find_current_product(data)
    if current_product is None:
        return None
    return current_product.get("value")


def _fees_summary(product: dict) -> str:
    fees = product.get("PriceSchedule", {}).get("PriceBreaks") if product.get("PriceSchedule") else None
    class_fees = product.get("xp", {}).get("ClassFees")
    if class_fees:
        parts = [f"{f['ClassFeeName']}: ${f['ClassFeeAmount']}" for f in class_fees]
        return "; ".join(parts)
    if fees:
        prices = [str(b["Price"]) for b in fees if b.get("Price") is not None]
        if prices:
            return "$" + "/".join(prices)
    min_price = product.get("xp", {}).get("MinPrice")
    max_price = product.get("xp", {}).get("MaxPrice")
    if min_price is not None and max_price is not None:
        if min_price == max_price == 0:
            return "free"
        return f"${min_price}-${max_price}"
    return "not stated"


def _is_senior_relevant(product: dict) -> bool:
    xp = product.get("xp", {})
    segments = xp.get("TargetCustomerSegments")
    if segments:
        return any("senior" in str(s).lower() for s in segments)
    text = " ".join(
        str(v)
        for v in (
            product.get("Name"),
            product.get("Description"),
            xp.get("SummaryBox"),
            xp.get("Slug"),
        )
        if v
    ).lower()
    return any(kw in text for kw in SENIOR_TEXT_KEYWORDS)


_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _parse_local(iso_str: Optional[str]) -> Optional[dt.datetime]:
    """Parse an onePA timestamp as Singapore local (wall-clock) time.

    onePA's API tags every timestamp with a `+00:00` UTC offset, but the
    wall-clock value is already Singapore time, not real UTC: a course
    published (and separately confirmed by research) as running "3:00-5:00 PM"
    carries StartDate/EndDate of 15:00/17:00 -- true UTC would place that at
    11 PM-1 AM SGT, which no community course runs. The offset is therefore
    dropped and the naive value is treated as SGT directly, rather than
    converted (which would shift every displayed time by 8 hours and make the
    output actively wrong).
    """
    if not iso_str:
        return None
    naive = iso_str.split("+")[0].split("Z")[0]
    try:
        return dt.datetime.fromisoformat(naive)
    except ValueError:
        return None


def _fmt_date(d: dt.datetime) -> str:
    return f"{_WEEKDAYS[d.weekday()][:3]}, {d.day} {d.strftime('%b %Y')}"


def _fmt_time(d: dt.datetime) -> str:
    hour12 = d.hour % 12 or 12
    ampm = "AM" if d.hour < 12 else "PM"
    return f"{hour12}:{d.minute:02d} {ampm}"


def _fmt_datetime(iso_str: Optional[str]) -> str:
    d = _parse_local(iso_str)
    return f"{_fmt_date(d)}, {_fmt_time(d)} SGT" if d else ""


def _clean_text(text: Optional[str], max_len: int = 200) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[: max_len - 1] + "…" if len(text) > max_len else text


def _course_recurrence(xp: dict) -> str:
    start, end = _parse_local(xp.get("StartDate")), _parse_local(xp.get("EndDate"))
    sessions = xp.get("TotalSessions")
    if not start or not end:
        return "schedule not published"
    weekday = _WEEKDAYS[start.weekday()] + "s"
    span = (
        f"{start.day} {start.strftime('%b')} - {end.strftime('%d %b %Y')}"
        if start.year == end.year
        else f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"
    )
    time_range = f"{_fmt_time(start)}-{_fmt_time(end)} SGT"
    sess = f" ({sessions} sessions)" if sessions else ""
    return f"{weekday}, {span}, {time_range}{sess}"


def _event_recurrence(xp: dict) -> str:
    start, end = _parse_local(xp.get("StartDate")), _parse_local(xp.get("EndDate"))
    time_range = f"{_fmt_time(start)}-{_fmt_time(end)} SGT per session" if start and end else ""
    pattern = _clean_text(xp.get("SummaryBox"))
    if time_range and pattern:
        return f"{time_range}; {pattern}"
    return pattern or time_range or "schedule not published"


def _ig_recurrence(product: dict, xp: dict) -> str:
    desc = _clean_text(product.get("Description"))
    sessions = xp.get("TotalSessions")
    start = _parse_local(xp.get("StartDate"))
    parts = [p for p in [desc] if p]
    if sessions:
        parts.append(f"{sessions} sessions to date")
    if start:
        parts.append(f"group active since {start.strftime('%b %Y')}")
    return "; ".join(parts) if parts else "schedule not published"


def _registration_status(xp: dict) -> str:
    if xp.get("CanRegisterOnline") is False:
        return "registration closed"
    closing = _parse_local(xp.get("OnlineRegistrationClosingDate"))
    if closing:
        return f"registration open (closes {_fmt_date(closing)})"
    return "registration open" if xp.get("CanRegisterOnline") else "not stated"


def product_to_event(url: str, product: dict, accessed_at: str) -> Event:
    xp = product.get("xp", {})
    product_type = xp.get("ProductType", "")

    if product_type == "Event":
        title = xp.get("Event", {}).get("Name") or product.get("Name", "")
        organisation = "People's Association"
        outlet = xp.get("Outlet", {}).get("Name", "")
        address = xp.get("Address") or xp.get("Venue", "") or ""
        # StartDate/EndDate on Event pages bound a whole listing season (e.g.
        # 1 Jan-31 Dec), not one occurrence -- only their time-of-day is
        # meaningful, so `datetime` is left blank rather than showing a
        # misleading single date.
        event_datetime = ""
        recurrence = _event_recurrence(xp)
        group_size = str(xp.get("AttendeeCount", "")) or "not stated"
        cost = _fees_summary(product)
        languages = "not stated"
    elif product_type == "InterestGroup":
        ig = xp.get("Ig", {})
        title = ig.get("Name") or product.get("Name", "")
        organisation = xp.get("OriginalOutlet", {}).get("Name") or xp.get("Outlet", {}).get("Name", "People's Association")
        outlet = xp.get("Outlet", {}).get("Name", "")
        address = ""
        # StartDate here is when the group was founded, not the next meeting
        # -- the actual recurring day/time (e.g. "every Friday 6:30pm") comes
        # from the group's own description, used in _ig_recurrence.
        event_datetime = ""
        recurrence = _ig_recurrence(product, xp)
        group_size = str(xp.get("TotalMembers", "")) or "not stated"
        cost = "free" if not xp.get("MinPrice") else _fees_summary(product)
        languages = "not stated"
    else:  # Class / course, or unrecognised -- treat as a course
        course = xp.get("Course", {})
        title = course.get("Title") or product.get("Name", "")
        organisation = "People's Association"
        outlet = xp.get("Outlet", {}).get("Name", "")
        address = ""
        event_datetime = _fmt_datetime(xp.get("StartDate"))  # first session
        recurrence = _course_recurrence(xp)
        max_vac = xp.get("Maxvacancy")
        group_size = f"max {max_vac}" if max_vac else "not stated"
        cost = _fees_summary(product)
        languages = xp.get("Language", "not stated")

    status = _registration_status(xp)
    recurrence = f"{recurrence}; {status}".strip("; ")

    product_code = xp.get("ProductCode") or product.get("ID") or url
    event_id = f"PA-{product_code}"

    return Event(
        id=event_id,
        title=title,
        organisation=organisation,
        block=outlet,
        address=address or outlet,
        datetime=event_datetime,
        recurrence=recurrence,
        cost=cost,
        languages=languages,
        group_size=group_size,
        has_role="no",  # onePA courses/events/IGs are attendance-based, not volunteer roles
        source=url,
        source_verified_at=accessed_at,
    )


def _fetch_one(session: requests.Session, url: str, accessed_at: str) -> Optional[Event]:
    try:
        product = fetch_product(session, url)
    except (requests.RequestException, json.JSONDecodeError):
        return None
    if product is None or not _is_senior_relevant(product):
        return None
    return product_to_event(url, product, accessed_at)


def iter_scrape(
    slug_keywords: Optional[Iterable[str]] = DEFAULT_SLUG_KEYWORDS,
    limit: Optional[int] = None,
    accessed_at: str = "",
    workers: int = 6,
) -> Iterator[Event]:
    """Discover, fetch and normalise onePA listings, yielding senior-relevant Events as found.

    Pages are fetched concurrently (default 6 workers) -- onePA page loads are
    each dominated by server-side render time (multi-second), not by request
    volume, so a small worker pool cuts wall-clock time roughly N-fold without
    materially increasing requests/second per connection. `_get`'s retry/backoff
    still applies per request, and each worker reuses a shared session/connection
    pool sized to match.
    """
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=workers, pool_maxsize=workers)
    session.mount("https://", adapter)

    urls = []
    seen: set[str] = set()
    for url in discover_listing_urls(session, slug_keywords=slug_keywords):
        if url not in seen:
            seen.add(url)
            urls.append(url)

    yielded = 0
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, session, url, accessed_at): url for url in urls}
        for future in as_completed(futures):
            if limit is not None and yielded >= limit:
                break
            event = future.result()
            if event is not None:
                yielded += 1
                yield event


def scrape(
    slug_keywords: Optional[Iterable[str]] = DEFAULT_SLUG_KEYWORDS,
    limit: Optional[int] = None,
    delay_seconds: float = 0.3,
    accessed_at: str = "",
) -> list[Event]:
    """Same as iter_scrape but collects into a list (kept for simple callers/tests)."""
    return list(iter_scrape(slug_keywords=slug_keywords, limit=limit, accessed_at=accessed_at))
