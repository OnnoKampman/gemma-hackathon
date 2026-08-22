#!/usr/bin/env python3
"""Refresh the Jio events database from onepa.gov.sg.

Usage:
    python3 cli.py --out events_scraped.csv
    python3 cli.py --exhaustive --out events_scraped.csv   # slower, no slug pre-filter
    python3 cli.py --limit 50 --out events_scraped.csv     # quick smoke test
"""

import argparse
import datetime as dt
import sys

from scraper.onepa import DEFAULT_SLUG_KEYWORDS, iter_scrape
from scraper.store import CsvEventStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="events_scraped.csv", help="CSV file to upsert into")
    parser.add_argument("--limit", type=int, default=None, help="Stop after this many senior-relevant listings")
    parser.add_argument(
        "--exhaustive",
        action="store_true",
        help="Crawl every onePA listing instead of pre-filtering by slug keyword (slow: ~7,800 pages total)",
    )
    parser.add_argument("--workers", type=int, default=6, help="Concurrent page fetches (onePA pages are slow server-side, so this is the main speed lever)")
    parser.add_argument("--checkpoint-every", type=int, default=20, help="Save to --out after this many new events (so a long run is safe to interrupt)")
    args = parser.parse_args()

    slug_keywords = None if args.exhaustive else DEFAULT_SLUG_KEYWORDS
    accessed_at = dt.date.today().isoformat()

    print(f"Discovering onePA listings (exhaustive={args.exhaustive}, workers={args.workers})...", file=sys.stderr)
    store = CsvEventStore(args.out)
    found = 0
    since_checkpoint = 0

    try:
        for event in iter_scrape(
            slug_keywords=slug_keywords,
            limit=args.limit,
            accessed_at=accessed_at,
            workers=args.workers,
        ):
            store.upsert([event])
            found += 1
            since_checkpoint += 1
            print(f"  [{found}] {event.title} -- {event.block}", file=sys.stderr)
            if since_checkpoint >= args.checkpoint_every:
                store.save()
                since_checkpoint = 0
                print(f"  ...checkpoint saved ({len(store)} rows in {args.out})", file=sys.stderr)
    finally:
        store.save()

    print(f"Done. {found} senior-relevant listings found this run. {args.out} now has {len(store)} rows total.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
