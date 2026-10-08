"""Step 2 (EXTRACT) for the RateMyProfessors source.

Pulls every UBC Vancouver professor via RateMyProfessor_Database_APIs and
saves the raw response untouched to data/raw/rmp/<date>/. No cleaning,
matching, or key normalization happens here — that's pipeline/clean.py.
"""

import dataclasses
import datetime
import json
import re
from pathlib import Path

import requests
from lxml import html

import RateMyProfessor_Database_APIs as rmp
import RateMyProfessor_Database_APIs.main as rmp_main

UBC_VANCOUVER_SCHOOL_ID = 1413

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    )
}


def _get_school_unique_id_fixed(url_school_id):
    """Replacement for the package's get_school_unique_id, which 403s because
    it sends no User-Agent header and then silently returns None on failure —
    causing fetch_all_professors_from_a_school to fall back to an unscoped
    global search instead of raising. This version raises loudly instead.
    """
    url = f"https://www.ratemyprofessors.com/school/{url_school_id}"
    response = requests.get(url, headers=_BROWSER_HEADERS)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to resolve school id {url_school_id}: status {response.status_code}"
        )
    tree = html.fromstring(response.content)
    script_content = tree.xpath(
        "//script[contains(text(), 'window.__RELAY_STORE__')]/text()"
    )
    if not script_content:
        raise RuntimeError(f"No RELAY_STORE data found for school id {url_school_id}")
    match = re.search(r"window\.__RELAY_STORE__ = (.*);", script_content[0])
    json_data = json.loads(match.group(1))
    for key, value in json_data.items():
        if isinstance(value, dict) and value.get("legacyId") == int(url_school_id):
            return key
    raise RuntimeError(f"Unique ID for school id {url_school_id} not found")


rmp_main.get_school_unique_id = _get_school_unique_id_fixed


def to_jsonable(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "__dict__"):
        return to_jsonable(vars(obj))
    return str(obj)


def extract_rmp(school_id: int = UBC_VANCOUVER_SCHOOL_ID) -> Path:
    professors = rmp.fetch_all_professors_from_a_school(school_id)

    schools_seen = {
        p.school["name"] if isinstance(p.school, dict) else p.school.name
        for p in professors
    }
    if schools_seen != {"University of British Columbia"}:
        raise RuntimeError(
            f"Expected only 'University of British Columbia', got schools: {schools_seen}. "
            "Refusing to save — this looks like the unscoped-global-search bug again."
        )

    out_dir = Path("data/raw/rmp") / datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "professors.json"

    with open(out_path, "w") as f:
        json.dump(to_jsonable(professors), f, indent=2)

    print(f"Pulled {len(professors)} professor records for school_id={school_id}")
    print(f"Saved to {out_path}")
    return out_path


if __name__ == "__main__":
    extract_rmp()
