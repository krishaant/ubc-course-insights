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

# Era precedence where terms overlap: newer methodology wins. pair-reports
# covers 1996-2018, tableau_v1 covers 2014-2021, tableau_v2 covers 2021-2025.
# Keep pair-reports only where v1 doesn't cover it, and v1 only where v2
# doesn't cover it.
ERA_YEAR_CUTOFFS = {
    "pair_reports": lambda year: year <= 2013,
    "tableau_v1": lambda year: year <= 2020,
    "tableau_v2": lambda year: True,
}

ERA_SPARSE_PATHS = {
    "pair_reports": "pair-reports/UBC",
    "tableau_v1": "tableau-dashboard/UBCV",
    "tableau_v2": "tableau-dashboard-v2/UBCV",
}


def clean_grades(raw_root: str) -> pd.DataFrame:
    era_frames = []
    for era, sparse_path in ERA_SPARSE_PATHS.items():
        files = sorted(glob.glob(f"{raw_root}/{sparse_path}/*/*.csv"))
        if not files:
            raise RuntimeError(f"No grade CSVs found under {raw_root}/{sparse_path}")
        df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
        df = df[df["Year"].apply(ERA_YEAR_CUTOFFS[era])].copy()
        df["era"] = era
        if "Enrolled" in df.columns:
            df = df.rename(columns={"Enrolled": "Reported"})
        era_frames.append(df)
        print(f"grades/{era}: {len(df)} rows kept after era-precedence cutoff")

    df = pd.concat(era_frames, ignore_index=True)

    before = len(df)
    detail = df["Detail"].astype(str).str.strip()
    section = df["Section"].astype(str).str.strip()
    df = df[(detail != "OVERALL") & (section != "OVERALL")].copy()
    dropped_overall = before - len(df)

    df["course_key"] = [course_key(s, c) for s, c in zip(df["Subject"], df["Course"])]
    df["term"] = df["Year"].astype(str) + df["Session"].astype(str)

    # Vectorized instructor split (';'-joined across all three eras,
    # confirmed) -- iterrows was too slow once pair-reports' ~300k rows
    # joined the mix.
    df["instructor"] = df["Professor"].apply(
        lambda raw: split_instructors(raw, sep=";")
    )
    out = df.explode("instructor", ignore_index=True)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / "grade_sections.csv"
    out.to_csv(out_path, index=False)

    print(f"grades: {before} raw rows -> {len(out)} clean rows "
          f"({dropped_overall} OVERALL rows dropped, expanded for multi-instructor sections)")
    print(f"  era breakdown: {df['era'].value_counts().to_dict()}")
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

    before_dedup = len(out)
    # Cursor-based pagination can return the same professor twice across
    # page boundaries (confirmed: 18 professors / 36 rows duplicated in the
    # raw pull, identical on every field). Keep one row per legacy_id.
    out = out.drop_duplicates(subset="legacy_id", keep="first")
    duped = before_dedup - len(out)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / "rmp_professors.csv"
    out.to_csv(out_path, index=False)

    print(f"rmp professors: {before_dedup} raw rows -> {len(out)} clean rows "
          f"({duped} duplicate-legacy_id rows dropped) -> {out_path}")
    return out


# ---------------------------------------------------------------------------
# RateMyProfessors reviews (per-professor detail pull, extract_rmp_reviews.py)
# ---------------------------------------------------------------------------

def _review_course_key(raw_class: str) -> str | None:
    """RMP's free-text course field has no space/campus code: 'MATH100',
    'BIO213'. Not a real course_key match (that's still unresolved fuzzy
    matching, deliberately not attempted) -- just a best-effort normalize
    so an exact match against course_summary.course_key is at least
    possible for the common case.
    """
    if not isinstance(raw_class, str) or not raw_class.strip():
        return None
    match = re.match(r"^([A-Za-z]+)[_\s]*(\d.*)$", raw_class.strip())
    if not match:
        return None
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def clean_reviews(raw_dir: str) -> pd.DataFrame:
    files = sorted(Path(raw_dir).glob("*.json"))
    files = [f for f in files if f.stem != "_errors"]
    if not files:
        raise RuntimeError(f"No review files found under {raw_dir}")

    rows = []
    for f in files:
        professor = json.loads(f.read_text())
        legacy_id = professor.get("legacy_id")
        for rating in professor.get("ratings", []):
            rows.append({
                "legacy_id": legacy_id,
                "raw_class": rating.get("class"),
                "course_key_guess": _review_course_key(rating.get("class")),
                "date": rating.get("date"),
                "comment": rating.get("comment"),
                "clarity_rating": rating.get("clarityRating"),
                "difficulty_rating": rating.get("difficultyRating"),
                "helpful_rating": rating.get("helpfulRating"),
                "is_online": rating.get("isForOnlineClass"),
                "is_for_credit": rating.get("isForCredit"),
                "attendance_mandatory": rating.get("attendanceMandatory"),
                "flag_status": rating.get("flagStatus"),
            })

    out = pd.DataFrame(rows)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    # Parquet, not CSV -- free-text review comments (embedded newlines,
    # quotes, unicode) broke the CSV round-trip: pandas wrote 41646 rows but
    # reading it back disagreed on the row count depending on parser engine,
    # and the C engine outright crashed with a buffer overflow. Parquet has
    # no delimiter/escaping ambiguity for this kind of content.
    out_path = CLEAN_DIR / "reviews.parquet"
    out.to_parquet(out_path, index=False)

    matched_course = out["course_key_guess"].notna().sum()
    print(f"reviews: {len(files)} professor files -> {len(out)} review rows "
          f"({matched_course} with a guessed course_key, {len(out) - matched_course} without) -> {out_path}")
    return out


if __name__ == "__main__":
    clean_grades("data/raw/grades/2026-10-08/ubc-pair-grade-data")
    clean_salaries("data/raw/salaries")
    clean_rmp_professors("data/raw/rmp/2026-10-07/professors.json")
    clean_reviews("data/raw/rmp_reviews/2026-10-08")

    # This run's two term files landed in different date folders because the
    # crawl spanned midnight (see extract_sections.py's run_date fix) — a
    # normal future run will have both under one date.
    clean_sections({
        1453: "data/raw/sections/2026-10-07/1453.json",
        1454: "data/raw/sections/2026-10-08/1454.json",
    })
