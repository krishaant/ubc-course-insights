"""Step 3 (CLEAN) — one tidy table per source, written to data/clean/.

Per the architecture: this step only normalizes each source on its own
(course keys, one-row-per-instructor, type coercion, obvious junk removal).
Cross-source professor matching (prof_id, ambiguous-name resolution, the
overrides file) is step 4 (MATCH) — a separate, harder problem — and is
deliberately NOT done here.
"""

import glob
import json
import re
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/clean")


def course_key(subject: str, course) -> str:
    """STAT_V 344 / STAT344 / stat 344 / (STAT, 344) -> 'STAT 344'."""
    subject = re.sub(r"_V$", "", str(subject).strip().upper())
    course = str(course).strip().upper()
    return f"{subject} {course}"


def split_instructors(raw: str, sep: str) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return [None]
    return [name.strip() for name in raw.split(sep) if name.strip()]


# ---------------------------------------------------------------------------
# Grades
# ---------------------------------------------------------------------------

def clean_grades(raw_root: str) -> pd.DataFrame:
    files = sorted(glob.glob(f"{raw_root}/tableau-dashboard-v2/UBCV/*/*.csv"))
    if not files:
        raise RuntimeError(f"No grade CSVs found under {raw_root}")

    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)

    before = len(df)
    df = df[df["Detail"].astype(str) != "OVERALL"].copy()
    df = df[df["Section"].astype(str) != "OVERALL"].copy()
    dropped_overall = before - len(df)

    df["course_key"] = [course_key(s, c) for s, c in zip(df["Subject"], df["Course"])]
    df["term"] = df["Year"].astype(str) + df["Session"].astype(str)

    rows = []
    for _, row in df.iterrows():
        instructors = split_instructors(row["Professor"], sep=";")
        for instructor in instructors:
            r = row.to_dict()
            r["instructor"] = instructor
            rows.append(r)
    out = pd.DataFrame(rows)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / "grade_sections.csv"
    out.to_csv(out_path, index=False)

    print(f"grades: {before} raw rows -> {len(out)} clean rows "
          f"({dropped_overall} OVERALL rows dropped, expanded for multi-instructor sections)")
    print(f"  saved to {out_path}")
    return out


# ---------------------------------------------------------------------------
# Course schedule
# ---------------------------------------------------------------------------

def clean_sections(term_id_to_path: dict[int, str]) -> pd.DataFrame:
    rows = []
    for term_id, path in term_id_to_path.items():
        payload = json.loads(Path(path).read_text())

        courses = {i["id"]: i["attributes"] for i in payload["included"] if i["type"] == "node--course"}
        statuses = {i["id"]: i["attributes"] for i in payload["included"] if i["type"] == "taxonomy_term--status"}
        delivery_modes = {i["id"]: i["attributes"] for i in payload["included"] if i["type"] == "taxonomy_term--delivery_mode"}
        instr_methods = {i["id"]: i["attributes"] for i in payload["included"] if i["type"] == "taxonomy_term--instructional_method"}

        for section in payload["data"]:
            a = section["attributes"]
            rel = section["relationships"]

            def resolve(rel_name, lookup):
                ref = rel.get(rel_name, {}).get("data")
                if not ref:
                    return {}
                return lookup.get(ref["id"], {})

            course = resolve("field_course", courses)
            status = resolve("field_status", statuses)
            delivery = resolve("field_delivery_mode", delivery_modes)
            method = resolve("field_instructional_method", instr_methods)

            base = {
                "term_id": term_id,
                "course_key": course_key(*course.get("field_course_code", " ").split(" ", 1))
                              if course.get("field_course_code") else None,
                "course_title": course.get("title"),
                "section_number": a.get("field_section_number"),
                "days": a.get("field_days"),
                "start_time_sec": a.get("field_start_time"),
                "end_time_sec": a.get("field_end_time"),
                "start_date": a.get("field_start_date"),
                "end_date": a.get("field_end_date"),
                "credits": a.get("field_credits"),
                "status": status.get("name"),
                "delivery_mode": delivery.get("name"),
                "instructional_method": method.get("name"),
            }

            instructors = a.get("field_instructors") or [None]
            for instructor in instructors:
                rows.append({**base, "instructor": instructor})

    out = pd.DataFrame(rows)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / "upcoming_sections.csv"
    out.to_csv(out_path, index=False)

    print(f"sections: {len(out)} clean rows (expanded for multi-instructor sections) -> {out_path}")
    return out


# ---------------------------------------------------------------------------
# Salaries
# ---------------------------------------------------------------------------

DISCLOSURE_THRESHOLD = 75000  # SOFI only discloses remuneration above this


def clean_salaries(raw_root: str) -> pd.DataFrame:
    frames = []
    for year_dir in sorted(Path(raw_root).iterdir()):
        if not year_dir.is_dir():
            continue
        parsed_path = year_dir / "parsed.csv"
        if not parsed_path.exists():
            continue
        df = pd.read_csv(parsed_path)
        df["fiscal_year"] = year_dir.name
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    before = len(df)

    df["salary_num"] = (
        df["Salary"].astype(str).str.replace(",", "", regex=False).astype(float)
    )
    df = df[df["salary_num"] >= DISCLOSURE_THRESHOLD].copy()
    dropped = before - len(df)

    split_names = df["Name"].str.split(",", n=1, expand=True)
    df["last_name"] = split_names[0].str.strip()
    df["first_name"] = split_names[1].str.strip()

    # Real names in this document are always capitalized ("Aamodt", "Adams").
    # A lowercase-starting match ("grants, contracts", "dinger, LLC") is
    # financial-statement boilerplate text the regex coincidentally matched,
    # not a person — and it can coincidentally clear the $75k threshold too.
    is_real_name = df["last_name"].str[0].str.isupper() & df["first_name"].str[0].str.isupper()
    noise_count = (~is_real_name).sum()
    df = df[is_real_name]

    out = df[["fiscal_year", "last_name", "first_name", "salary_num"]].rename(
        columns={"salary_num": "salary"}
    )

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / "salaries.csv"
    out.to_csv(out_path, index=False)

    print(f"salaries: {before} raw rows -> {len(out)} clean rows "
          f"({dropped} dropped below ${DISCLOSURE_THRESHOLD:,} threshold, "
          f"{noise_count} dropped as non-name regex noise)")
    print(f"  saved to {out_path}")
    return out


# ---------------------------------------------------------------------------
# RateMyProfessors (professor gist only — see note in __main__)
# ---------------------------------------------------------------------------

def clean_rmp_professors(raw_path: str) -> pd.DataFrame:
    professors = json.loads(Path(raw_path).read_text())
    df = pd.DataFrame(professors)

    df["school_name"] = df["school"].apply(lambda s: s.get("name") if isinstance(s, dict) else None)

    out = df[[
        "legacy_id", "first_name", "last_name", "department",
        "avg_rating", "avg_difficulty", "num_ratings", "would_take_again_percent",
    ]].copy()

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / "rmp_professors.csv"
    out.to_csv(out_path, index=False)

    print(f"rmp professors: {len(out)} clean rows -> {out_path}")
    print("  NOTE: this is professor-gist data only (ratings aggregate). No "
          "review-level rows exist yet — fetch_a_professor() hasn't been "
          "called per-professor, so there's no reviews.csv / review text / "
          "per-review course text to fuzzy-match against yet.")
    return out


if __name__ == "__main__":
    clean_grades("data/raw/grades/2026-10-07/ubc-pair-grade-data")
    clean_salaries("data/raw/salaries")
    clean_rmp_professors("data/raw/rmp/2026-10-07/professors.json")

    # This run's two term files landed in different date folders because the
    # crawl spanned midnight (see extract_sections.py's run_date fix) — a
    # normal future run will have both under one date.
    clean_sections({
        1453: "data/raw/sections/2026-10-07/1453.json",
        1454: "data/raw/sections/2026-10-08/1454.json",
    })
