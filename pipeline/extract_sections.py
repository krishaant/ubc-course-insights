"""Step 2 (EXTRACT) for the UBC course-schedule source.

Pulls sections from courses.students.ubc.ca's public JSON:API (the same
endpoint the official course search page calls — no login required) for the
given UBC Vancouver term(s), and saves the raw data+included payload
untouched to data/raw/sections/<date>/<term_id>.json.

Respects the site's own robots.txt: Crawl-delay: 10. Full pull of two terms
is ~282 requests (confirmed against live meta.count), ~47 minutes. No
building/room field exists in this API (confirmed) — don't go looking for
one in clean.py either.
"""

import datetime
import json
import sys
import time
from pathlib import Path

import requests

# Flush progress line-by-line even when stdout is redirected to a file/log,
# so a long-running crawl shows live progress instead of appearing stuck.
sys.stdout.reconfigure(line_buffering=True)

BASE_URL = "https://courses.students.ubc.ca/jsonapi/node/section"
PAGE_SIZE = 50  # server-enforced hard cap, confirmed by live test
CRAWL_DELAY_SECONDS = 10
USER_AGENT = "ubc-course-insights-research/0.1 (contact: krishaant; github.com/krishaant/ubc-course-insights)"

# UBC Vancouver term IDs, confirmed live against /jsonapi/taxonomy_term/term
TERM_IDS = {
    "2025-26 Winter Term 1": 1449,
    "2025-26 Winter Term 2": 1450,
    "2026 Summer Session": 1452,
    "2026-27 Winter Term 1": 1453,
    "2026-27 Winter Term 2": 1454,
}


def _fetch_page(url: str, params: dict | None = None) -> dict:
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


def extract_term(term_id: int, run_date: str, max_pages: int | None = None) -> Path:
    params = {
        "filter[field_academic_term.meta.drupal_internal__target_id]": term_id,
        "filter[field_is_visible]": 1,
        "include": "field_course,field_status,field_delivery_mode,field_instructional_method",
        "page[limit]": PAGE_SIZE,
        "sort": "drupal_internal__nid",
    }

    all_data = []
    included_by_key = {}  # dedupe across pages by (type, id)

    url = BASE_URL
    page_num = 0
    total_count = None

    while url:
        page_num += 1
        payload = _fetch_page(url, params if page_num == 1 else None)

        if total_count is None:
            total_count = payload.get("meta", {}).get("count")
            print(f"term {term_id}: {total_count} visible sections, "
                  f"{-(-total_count // PAGE_SIZE)} pages expected")

        all_data.extend(payload.get("data", []))
        for inc in payload.get("included", []):
            included_by_key[(inc["type"], inc["id"])] = inc

        print(f"  page {page_num}: +{len(payload.get('data', []))} sections "
              f"(running total {len(all_data)})")

        next_link = payload.get("links", {}).get("next", {}).get("href")
        url = next_link
        params = None  # next_link already carries all query params

        if max_pages is not None and page_num >= max_pages:
            print(f"  stopping early: max_pages={max_pages} (test mode)")
            break

        if url:
            time.sleep(CRAWL_DELAY_SECONDS)

    out_dir = Path("data/raw/sections") / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{term_id}.json"
    with open(out_path, "w") as f:
        json.dump({"data": all_data, "included": list(included_by_key.values())}, f)

    print(f"term {term_id}: saved {len(all_data)} sections to {out_path}")
    return out_path


def extract_sections(term_ids: list[int], max_pages: int | None = None) -> list[Path]:
    # Stamp the whole run with one date, computed once up front — a run that
    # spans midnight (this crawl takes ~47 minutes) would otherwise split
    # terms across two different date folders.
    run_date = datetime.date.today().isoformat()
    return [extract_term(term_id, run_date, max_pages=max_pages) for term_id in term_ids]


if __name__ == "__main__":
    import sys

    # Default to the current + next UBC-V winter terms (per spec: field data
    # is only meaningfully "now"/"upcoming" for current/near-future terms).
    current_and_next = [TERM_IDS["2026-27 Winter Term 1"], TERM_IDS["2026-27 Winter Term 2"]]

    test_mode = "--test" in sys.argv
    extract_sections(current_and_next, max_pages=3 if test_mode else None)
