"""Step 2 (EXTRACT), deferred piece: individual RMP reviews per professor.

Held off on this originally (see commit history) -- the earlier extract_rmp
only pulled the professor-gist aggregate via fetch_all_professors_from_a_school.
This pulls per-professor detail via fetch_a_professor(legacy_id), scoped to
the professors already in our master list (data/final/ubc.duckdb's
prof_summary, legacy_id IS NOT NULL) -- not all 5363 RMP-UBC profiles, just
the ~4100 actually matched to a grades/schedule teaching record.

Known package limitation, confirmed via live testing, not fixable without
reverse-engineering RMP's cursor pagination: fetch_a_professor() hardcodes
`ratings(first: 20)` in its GraphQL query -- every professor caps at their
20 most recent reviews, regardless of how many they actually have.

Resumable: skips any legacy_id whose output file already exists, so this
can be killed and rerun without re-fetching everything. Designed to run
unattended for a long stretch (~4100 professors * ~2s politeness delay
= ~2.3 hours) -- logs progress every 50 professors and keeps going past
individual failures (dead profile, transient network error) rather than
crashing the whole run.
"""

import datetime
import json
import re
import signal
import sys
import time
from pathlib import Path

import duckdb
import requests
from lxml import html

import RateMyProfessor_Database_APIs as rmp
import RateMyProfessor_Database_APIs.main as rmp_main

DB_PATH = Path("data/final/ubc.duckdb")
DELAY_SECONDS = 2.0

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    )
}


def _fixed_get_professor_unique_id(url_professor_id):
    """Same fix as extract_rmp.py's school-id patch: the package's own
    version sends no User-Agent on this particular lookup, gets 403'd by
    RMP's bot protection, and silently returns None instead of raising --
    which then makes fetch_a_professor() crash downstream on a NoneType
    instead of failing clearly. This version fails loudly instead.
    """
    url = f"https://www.ratemyprofessors.com/professor/{url_professor_id}"
    response = requests.get(url, headers=_HEADERS, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"status {response.status_code} resolving professor id {url_professor_id}")
    tree = html.fromstring(response.content)
    script_content = tree.xpath("//script[contains(text(), 'window.__RELAY_STORE__')]/text()")
    if not script_content:
        raise RuntimeError(f"no RELAY_STORE data for professor id {url_professor_id}")
    match = re.search(r"window\.__RELAY_STORE__ = (.*);", script_content[0])
    json_data = json.loads(match.group(1))
    for key, value in json_data.items():
        if isinstance(value, dict) and value.get("legacyId") == int(url_professor_id):
            return key
    raise RuntimeError(f"unique id for professor {url_professor_id} not found")


rmp_main.get_professor_unique_id = _fixed_get_professor_unique_id


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "__dict__"):
        return to_jsonable(vars(obj))
    return str(obj)


def get_target_legacy_ids() -> list[int]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    ids = con.execute(
        "SELECT DISTINCT legacy_id FROM prof_summary WHERE legacy_id IS NOT NULL ORDER BY legacy_id"
    ).fetchdf()["legacy_id"].astype(int).tolist()
    con.close()
    return ids


class _HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _HardTimeout("hard timeout hit")


def fetch_with_hard_timeout(legacy_id: int, seconds: int = 45):
    """The package's own fetch_a_professor() has NO timeout on its internal
    requests.post() call -- confirmed to actually hang indefinitely on a
    stalled connection (not an error, not a retry, just frozen -- caught
    this overnight: a run sat at 0 CPU usage, no progress, for 15+ minutes
    on one professor). SIGALRM enforces a hard wall-clock ceiling regardless
    of what's blocking inside the library.
    """
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(seconds)
    try:
        return rmp.fetch_a_professor(legacy_id)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def extract_reviews() -> Path:
    legacy_ids = get_target_legacy_ids()
    out_dir = Path("data/raw/rmp_reviews") / datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    already_done = {p.stem for p in out_dir.glob("*.json")}
    todo = [lid for lid in legacy_ids if str(lid) not in already_done]

    print(f"{len(legacy_ids)} target professors, {len(already_done)} already done, "
          f"{len(todo)} remaining. Output: {out_dir}", flush=True)

    errors = []
    for i, legacy_id in enumerate(todo, 1):
        try:
            professor = fetch_with_hard_timeout(legacy_id)
            out_path = out_dir / f"{legacy_id}.json"
            with open(out_path, "w") as f:
                json.dump(to_jsonable(professor), f)
        except Exception as e:
            errors.append((legacy_id, str(e)))
            print(f"  [{i}/{len(todo)}] FAILED legacy_id={legacy_id}: {e}", flush=True)

        if i % 50 == 0:
            print(f"  [{i}/{len(todo)}] {len(errors)} errors so far", flush=True)

        time.sleep(DELAY_SECONDS)

    print(f"Done. {len(todo) - len(errors)} succeeded, {len(errors)} failed.", flush=True)
    if errors:
        error_log = out_dir / "_errors.json"
        with open(error_log, "w") as f:
            json.dump(errors, f, indent=2)
        print(f"Error details: {error_log}", flush=True)

    return out_dir


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    extract_reviews()
