"""Step 6 (BUILD) — assemble final tables into data/final/ubc.duckdb.

Reviews are excluded for now (holding off on the RMP review pull per the
user) — no reviews table is built. Everything else from the spec's table
list is here: course_summary, course_terms, prof_summary,
prof_course_summary, upcoming_sections, salaries.

Professor identity: per the spec's "Professor master list" decision
(everyone who has taught or will teach at UBC-V), prof_master is built from
distinct match_keys in grades+sections only -- not from salaries (most
salary rows are non-teaching staff) and not from every RMP professor (RMP
has people from other schools' overlap/noise and people not teaching in our
term range). prof_id = the RMP legacy_id when matched "exact"/override,
else a synthetic "local:<match_key>" id so no_rmp professors still get a
stable identity other tables can join against.
"""

from pathlib import Path

import duckdb
import pandas as pd

from pipeline.match import match_key_from_fullname, match_key_from_parts

CLEAN_DIR = Path("data/clean")
FINAL_DIR = Path("data/final")
DB_PATH = FINAL_DIR / "ubc.duckdb"


def _prof_id(legacy_id, match_key) -> str:
    if pd.notna(legacy_id):
        return str(int(legacy_id))
    return f"local:{match_key}"


def build_prof_resolution() -> pd.DataFrame:
    """match_key -> (prof_id, match_label), resolved once, reused everywhere.

    Scoped to grades + sections only, matching the spec's "professor master
    list" decision: everyone who has taught or will teach at UBC-V. Salary
    rows are matched AGAINST this list later, never used to grow it -- most
    salary rows are non-teaching staff (confirmed: 8649 distinct people
    exist only in salary data, not grades/sections) and must not get
    promoted into a synthetic professor identity just because they earn
    above the SOFI disclosure threshold.
    """
    crosswalk = pd.read_csv(CLEAN_DIR / "prof_crosswalk.csv")
    master_source = crosswalk[crosswalk["source"].isin(["grades", "sections"])]

    # Several distinct unparseable names ("TBA", "Staff", ". Manav", ...)
    # all collapse to match_key=NaN. Without dropping them here first,
    # drop_duplicates would keep exactly one of them and give it a prof_id
    # -- which every null/placeholder-instructor row in course_terms would
    # then incorrectly inherit via the merge (confirmed: this previously
    # made 100% of course_terms rows "resolve" to one shared bogus
    # "local:nan" identity, including the ~80k genuinely null-instructor
    # rows that should have no prof_id at all).
    resolution = (
        master_source[["match_key", "legacy_id", "match_label"]]
        .dropna(subset=["match_key"])
        .drop_duplicates(subset="match_key")
    )
    resolution["prof_id"] = [
        _prof_id(lid, mk) for lid, mk in zip(resolution["legacy_id"], resolution["match_key"])
    ]

    # A representative raw name per match_key, for professors with no RMP
    # match -- prof_summary otherwise has no name at all for them (RMP is
    # currently the only source first_name/last_name come from), which
    # breaks both display and name search for ~70% of no_rmp professors.
    raw_name = (
        master_source.groupby("match_key")["raw_name"]
        .agg(lambda names: sorted(names)[0])
        .rename("representative_raw_name")
    )
    resolution = resolution.merge(raw_name, on="match_key", how="left")

    return resolution[["match_key", "prof_id", "legacy_id", "match_label", "representative_raw_name"]]


def build_course_terms(resolution: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_csv(CLEAN_DIR / "grade_sections.csv", low_memory=False)
    df["match_key"] = df["instructor"].apply(match_key_from_fullname)
    df = df.merge(resolution, on="match_key", how="left")
    out = df[[
        "course_key", "term", "Section", "Title", "instructor", "prof_id",
        "Reported", "Avg", "Median", "Percentile (25)", "Percentile (75)", "High", "Low",
        "<50", "50-54", "55-59", "60-63", "64-67", "68-71", "72-75", "76-79", "80-84", "85-89", "90-100",
    ]].rename(columns={
        "Section": "section", "Title": "course_title", "Reported": "reported",
        "Avg": "avg", "Median": "median",
    })

    print(f"course_terms: {len(out)} rows ({out['prof_id'].notna().sum()} with resolved prof_id)")
    return out


def build_course_summary(course_terms: pd.DataFrame) -> pd.DataFrame:
    def weighted_avg(g, col):
        w = g["reported"]
        return (g[col] * w).sum() / w.sum() if w.sum() > 0 else float("nan")

    # course_terms has one row per (section, instructor) -- a co-taught
    # section appears once per instructor (confirmed: ~18% of sections have
    # 2+ instructors, one as high as 65). That's correct for professor-level
    # stats (each instructor should get credit) but wrong here: a
    # course-level average must count each physical section once, not once
    # per instructor, or co-taught sections silently dominate the average.
    one_row_per_section = course_terms.drop_duplicates(subset=["course_key", "term", "section"])

    rows = []
    for course_key, g in one_row_per_section.groupby("course_key"):
        rows.append({
            "course_key": course_key,
            "course_title": g["course_title"].mode().iloc[0] if not g["course_title"].mode().empty else None,
            "overall_avg": weighted_avg(g, "avg"),
            "max_section_avg": g["avg"].max(),
            "min_section_avg": g["avg"].min(),
            "num_terms_offered": g["term"].nunique(),
            "num_sections_total": len(g),
            "first_term": sorted(g["term"].unique())[0],
            "last_term": sorted(g["term"].unique())[-1],
        })
    out = pd.DataFrame(rows)
    print(f"course_summary: {len(out)} rows (deduped {len(course_terms) - len(one_row_per_section)} "
          f"co-instructor rows before aggregating, so course-level stats don't double-count them)")
    return out


def build_prof_course_summary(course_terms: pd.DataFrame, course_summary: pd.DataFrame) -> pd.DataFrame:
    course_avg_lookup = course_summary.set_index("course_key")["overall_avg"].to_dict()

    rows = []
    matched = course_terms.dropna(subset=["prof_id"])
    for (prof_id, course_key), g in matched.groupby(["prof_id", "course_key"]):
        w = g["reported"]
        prof_avg = (g["avg"] * w).sum() / w.sum() if w.sum() > 0 else float("nan")
        course_avg = course_avg_lookup.get(course_key, float("nan"))
        rows.append({
            "prof_id": prof_id,
            "course_key": course_key,
            "num_sections": len(g),
            "total_reported": int(w.sum()),
            "prof_avg": prof_avg,
            "course_avg": course_avg,
            "grade_delta": prof_avg - course_avg if pd.notna(course_avg) else float("nan"),
        })
    out = pd.DataFrame(rows)
    print(f"prof_course_summary: {len(out)} rows")
    return out


def build_prof_master(resolution: pd.DataFrame) -> pd.DataFrame:
    rmp = pd.read_csv(CLEAN_DIR / "rmp_professors.csv")
    rmp["match_key"] = [
        match_key_from_parts(f, l) for f, l in zip(rmp["first_name"], rmp["last_name"])
    ]
    rmp["prof_id_rmp"] = rmp["legacy_id"].astype(int).astype(str)

    out = resolution.copy()
    out = out.merge(
        rmp[["prof_id_rmp", "first_name", "last_name", "department", "avg_rating",
             "avg_difficulty", "num_ratings", "would_take_again_percent"]],
        left_on="prof_id", right_on="prof_id_rmp", how="left",
    ).drop(columns=["prof_id_rmp"])

    had_rmp_name = out["first_name"].notna().sum()

    # Fall back to the representative raw name (from grades/sections) for
    # professors with no RMP match, split the same way match keys are built
    # (first word = first name, last word = last name) so it's at least
    # consistent with how the rest of the pipeline treats names.
    needs_fallback = out["first_name"].isna() & out["representative_raw_name"].notna()
    fallback_parts = out.loc[needs_fallback, "representative_raw_name"].str.split()
    out.loc[needs_fallback, "first_name"] = fallback_parts.str[0]
    out.loc[needs_fallback, "last_name"] = fallback_parts.str[-1]

    out = out.drop(columns=["representative_raw_name"])

    print(f"prof_master: {len(out)} rows ({had_rmp_name} with RMP name, "
          f"{needs_fallback.sum()} using a grades/sections fallback name, "
          f"{out['first_name'].isna().sum()} with no name at all)")
    return out


def build_prof_summary(prof_master: pd.DataFrame, prof_course_summary: pd.DataFrame) -> pd.DataFrame:
    overall_delta = {}
    for prof_id, g in prof_course_summary.dropna(subset=["grade_delta"]).groupby("prof_id"):
        w = g["total_reported"]
        overall_delta[prof_id] = (g["grade_delta"] * w).sum() / w.sum() if w.sum() > 0 else float("nan")

    prof_master = prof_master.copy()
    prof_master["overall_grade_delta"] = prof_master["prof_id"].map(overall_delta)
    print(f"prof_summary: {len(prof_master)} rows "
          f"({prof_master['overall_grade_delta'].notna().sum()} with a computed grade delta)")
    return prof_master


def build_upcoming_sections(resolution: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_csv(CLEAN_DIR / "upcoming_sections.csv")
    df["match_key"] = df["instructor"].apply(match_key_from_fullname)
    df = df.merge(resolution[["match_key", "prof_id"]], on="match_key", how="left")
    print(f"upcoming_sections: {len(df)} rows ({df['prof_id'].notna().sum()} with resolved prof_id)")
    return df


def build_salaries(resolution: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_csv(CLEAN_DIR / "salaries.csv")
    df["match_key"] = [
        match_key_from_parts(f, l) for f, l in zip(df["first_name"], df["last_name"])
    ]
    df = df.merge(resolution[["match_key", "prof_id"]], on="match_key", how="left")
    print(f"salaries: {len(df)} rows ({df['prof_id'].notna().sum()} linked to a professor in the master list)")
    return df


def build_data_sources() -> pd.DataFrame:
    """Last-pulled dates + row counts, for the About page. Dates reflect
    when each source was actually extracted this session (see commit
    history / extract script output) -- not derived from file mtimes,
    which would be wrong after a git clone or file copy.
    """
    import datetime as dt

    def raw_rows(path):
        return len(pd.read_csv(path, low_memory=False)) if Path(path).exists() else 0

    return pd.DataFrame([
        {"source": "RateMyProfessors", "last_pulled": dt.date(2026, 10, 7),
         "raw_rows": raw_rows(CLEAN_DIR / "rmp_professors.csv"), "notes": "professor gist only, no reviews yet"},
        {"source": "UBC grades (DonneyF/ubc-pair-grade-data)", "last_pulled": dt.date(2026, 10, 8),
         "raw_rows": raw_rows(CLEAN_DIR / "grade_sections.csv"),
         "notes": "1996S-2025W (pair-reports to 2013, tableau v1 2014-2020, tableau v2 2021+)"},
        {"source": "UBC course schedule", "last_pulled": dt.date(2026, 10, 8),
         "raw_rows": raw_rows(CLEAN_DIR / "upcoming_sections.csv"), "notes": "terms 1453-1454 (2026-27 W1/W2)"},
        {"source": "SOFI salary PDFs", "last_pulled": dt.date(2026, 10, 7),
         "raw_rows": raw_rows(CLEAN_DIR / "salaries.csv"), "notes": "FY21-FY25, manual annual upload"},
    ])


def build() -> None:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    resolution = build_prof_resolution()
    course_terms = build_course_terms(resolution)
    course_summary = build_course_summary(course_terms)
    prof_course_summary = build_prof_course_summary(course_terms, course_summary)
    prof_master = build_prof_master(resolution)
    prof_summary = build_prof_summary(prof_master, prof_course_summary)
    upcoming_sections = build_upcoming_sections(resolution)
    salaries = build_salaries(resolution)
    prof_crosswalk = pd.read_csv(CLEAN_DIR / "prof_crosswalk.csv")
    data_sources = build_data_sources()

    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE TABLE course_summary AS SELECT * FROM course_summary")
    con.execute("CREATE TABLE course_terms AS SELECT * FROM course_terms")
    con.execute("CREATE TABLE prof_summary AS SELECT * FROM prof_summary")
    con.execute("CREATE TABLE prof_course_summary AS SELECT * FROM prof_course_summary")
    con.execute("CREATE TABLE upcoming_sections AS SELECT * FROM upcoming_sections")
    con.execute("CREATE TABLE salaries AS SELECT * FROM salaries")
    con.execute("CREATE TABLE prof_crosswalk AS SELECT * FROM prof_crosswalk")
    con.execute("CREATE TABLE data_sources AS SELECT * FROM data_sources")
    con.close()

    print(f"\nbuilt {DB_PATH}")


if __name__ == "__main__":
    build()
