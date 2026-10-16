"""Plain DuckDB query functions used by the Streamlit pages.

Every function here is a straight read against data/final/ubc.duckdb --
no source is ever called live from the app (per the spec's SERVE step).
Caching is handled by Streamlit decorators at the page level where it
matters; these functions stay plain/testable per the spec's repo layout.
"""

import difflib

import duckdb
import pandas as pd

import config


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.DB_PATH), read_only=True)


def adjusted_rating(avg_rating, num_ratings, global_avg, k=config.ADJUSTED_RATING_K):
    if pd.isna(avg_rating) or pd.isna(num_ratings):
        return float("nan")
    return (num_ratings * avg_rating + k * global_avg) / (num_ratings + k)


def get_global_avg_rating(con) -> float:
    row = con.execute("SELECT AVG(avg_rating) FROM prof_summary WHERE avg_rating IS NOT NULL").fetchone()
    return row[0] if row and row[0] is not None else float("nan")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(con, query: str, limit: int = 15) -> dict:
    """Typo-tolerant search across courses and professors.

    Substring match first (handles the common case cheaply and precisely),
    falling back to difflib close-matching for actual typos.
    """
    query = query.strip()
    if not query:
        return {"courses": pd.DataFrame(), "professors": pd.DataFrame()}

    courses = con.execute(
        "SELECT course_key, course_title, overall_avg, num_sections_total "
        "FROM course_summary WHERE course_key ILIKE ? OR course_title ILIKE ? "
        "ORDER BY num_sections_total DESC LIMIT ?",
        [f"%{query}%", f"%{query}%", limit],
    ).fetchdf()

    profs = con.execute(
        "SELECT prof_id, first_name, last_name, department, avg_rating, num_ratings "
        "FROM prof_summary WHERE (first_name || ' ' || last_name) ILIKE ? "
        "ORDER BY num_ratings DESC NULLS LAST LIMIT ?",
        [f"%{query}%", limit],
    ).fetchdf()

    if courses.empty and profs.empty:
        all_keys = con.execute("SELECT DISTINCT course_key FROM course_summary").fetchdf()["course_key"].tolist()
        close = difflib.get_close_matches(query.upper(), all_keys, n=5, cutoff=0.6)
        if close:
            placeholders = ",".join("?" for _ in close)
            courses = con.execute(
                f"SELECT course_key, course_title, overall_avg, num_sections_total "
                f"FROM course_summary WHERE course_key IN ({placeholders})",
                close,
            ).fetchdf()

        all_names = con.execute(
            "SELECT prof_id, first_name || ' ' || last_name AS full_name FROM prof_summary "
            "WHERE first_name IS NOT NULL"
        ).fetchdf()
        name_close = difflib.get_close_matches(query, all_names["full_name"].tolist(), n=5, cutoff=0.6)
        if name_close:
            ids = all_names[all_names["full_name"].isin(name_close)]["prof_id"].tolist()
            placeholders = ",".join("?" for _ in ids)
            profs = con.execute(
                f"SELECT prof_id, first_name, last_name, department, avg_rating, num_ratings "
                f"FROM prof_summary WHERE prof_id IN ({placeholders})",
                ids,
            ).fetchdf()

    return {"courses": courses, "professors": profs}


def list_all_courses(con) -> pd.DataFrame:
    return con.execute(
        "SELECT course_key, course_title FROM course_summary ORDER BY course_key"
    ).fetchdf()


def list_all_professors(con) -> pd.DataFrame:
    return con.execute(
        "SELECT prof_id, first_name, last_name, department FROM prof_summary "
        "ORDER BY last_name, first_name"
    ).fetchdf()


# ---------------------------------------------------------------------------
# Course page
# ---------------------------------------------------------------------------

def get_course_summary(con, course_key: str) -> pd.Series | None:
    df = con.execute("SELECT * FROM course_summary WHERE course_key = ?", [course_key]).fetchdf()
    return df.iloc[0] if not df.empty else None


def get_course_trend_by_term(con, course_key: str) -> pd.DataFrame:
    # Dedupe to one row per section first -- course_terms has one row per
    # (section, instructor), so a co-taught section would otherwise count
    # toward the term average once per instructor (confirmed: ~18% of
    # sections have 2+ instructors). Matches the same fix in
    # pipeline/build.py's course_summary.
    return con.execute(
        "WITH one_row_per_section AS ("
        "  SELECT term, section, ANY_VALUE(avg) AS avg, ANY_VALUE(reported) AS reported "
        "  FROM course_terms WHERE course_key = ? GROUP BY term, section"
        ") "
        "SELECT term, SUM(reported * avg) / SUM(reported) AS avg, SUM(reported) AS reported "
        "FROM one_row_per_section GROUP BY term ORDER BY term",
        [course_key],
    ).fetchdf()


def get_course_now(con, course_key: str) -> pd.DataFrame:
    return con.execute(
        "SELECT s.*, p.avg_rating, p.num_ratings FROM upcoming_sections s "
        "LEFT JOIN prof_summary p ON s.prof_id = p.prof_id "
        "WHERE s.course_key = ? ORDER BY s.term_id, s.section_number",
        [course_key],
    ).fetchdf()


def get_course_history(con, course_key: str) -> pd.DataFrame:
    cols = ', '.join(f'ct."{c}"' for c in GRADE_BUCKET_COLS)
    return con.execute(
        f'SELECT ct.term, ct.section, ct.instructor, ct.prof_id, '
        f'p.first_name, p.last_name, '
        f'ct.reported, ct.avg, ct.median, ct."Percentile (25)" AS pct_25, '
        f'ct."Percentile (75)" AS pct_75, ct."High" AS high, ct."Low" AS low, {cols} '
        f'FROM course_terms ct LEFT JOIN prof_summary p ON ct.prof_id = p.prof_id '
        f'WHERE ct.course_key = ? ORDER BY ct.term DESC, ct.section',
        [course_key],
    ).fetchdf()


GRADE_BUCKET_COLS = [
    "<50", "50-54", "55-59", "60-63", "64-67", "68-71",
    "72-75", "76-79", "80-84", "85-89", "90-100",
]

# UBC's percentage-to-letter scale, same order as GRADE_BUCKET_COLS.
GRADE_LETTER_LABELS = ["F", "D", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]


def get_grade_distribution(con, course_key: str, prof_id: str | None = None) -> pd.Series:
    cols = ", ".join(f'SUM("{c}") AS "{c}"' for c in GRADE_BUCKET_COLS)
    if prof_id:
        # One instructor's own rows -- correct to sum as-is, even for a
        # section they co-taught (that's genuinely their contribution).
        df = con.execute(
            f"SELECT {cols} FROM course_terms WHERE course_key = ? AND prof_id = ?",
            [course_key, prof_id],
        ).fetchdf()
    else:
        # All instructors combined -- dedupe to one row per section first,
        # or a co-taught section's students get counted once per
        # instructor (same bug as get_course_trend_by_term).
        any_cols = ", ".join(f'ANY_VALUE("{c}") AS "{c}"' for c in GRADE_BUCKET_COLS)
        sum_cols = ", ".join(f'SUM("{c}") AS "{c}"' for c in GRADE_BUCKET_COLS)
        df = con.execute(
            f"WITH one_row_per_section AS ("
            f"  SELECT term, section, {any_cols} FROM course_terms "
            f"  WHERE course_key = ? GROUP BY term, section"
            f") SELECT {sum_cols} FROM one_row_per_section",
            [course_key],
        ).fetchdf()
    return df.iloc[0] if not df.empty else pd.Series({c: 0 for c in GRADE_BUCKET_COLS})


def get_course_professors(con, course_key: str) -> pd.DataFrame:
    df = con.execute(
        "SELECT pcs.*, p.first_name, p.last_name, p.avg_rating, p.avg_difficulty, "
        "p.num_ratings, p.match_label "
        "FROM prof_course_summary pcs JOIN prof_summary p ON pcs.prof_id = p.prof_id "
        "WHERE pcs.course_key = ?",
        [course_key],
    ).fetchdf()
    global_avg = get_global_avg_rating(con)
    df["adjusted_rating"] = [
        adjusted_rating(r, n, global_avg) for r, n in zip(df["avg_rating"], df["num_ratings"])
    ]
    return df


# ---------------------------------------------------------------------------
# Professor page
# ---------------------------------------------------------------------------

def get_prof_summary(con, prof_id: str) -> pd.Series | None:
    df = con.execute("SELECT * FROM prof_summary WHERE prof_id = ?", [prof_id]).fetchdf()
    return df.iloc[0] if not df.empty else None


def get_prof_courses(con, prof_id: str) -> pd.DataFrame:
    return con.execute(
        "SELECT pcs.*, cs.course_title FROM prof_course_summary pcs "
        "JOIN course_summary cs ON pcs.course_key = cs.course_key "
        "WHERE pcs.prof_id = ? ORDER BY pcs.total_reported DESC",
        [prof_id],
    ).fetchdf()


def get_prof_sections(con, prof_id: str) -> pd.DataFrame:
    return con.execute(
        "SELECT * FROM upcoming_sections WHERE prof_id = ? ORDER BY term_id, course_key",
        [prof_id],
    ).fetchdf()


def get_prof_salary(con, prof_id: str) -> pd.DataFrame:
    return con.execute(
        "SELECT fiscal_year, salary FROM salaries WHERE prof_id = ? ORDER BY fiscal_year",
        [prof_id],
    ).fetchdf()


def get_prof_reviews(con, prof_id: str, course_key: str | None = None) -> pd.DataFrame:
    if course_key:
        return con.execute(
            "SELECT * FROM reviews WHERE prof_id = ? AND course_key_guess = ? ORDER BY date DESC",
            [prof_id, course_key],
        ).fetchdf()
    return con.execute(
        "SELECT * FROM reviews WHERE prof_id = ? ORDER BY date DESC", [prof_id],
    ).fetchdf()


def get_prof_review_courses(con, prof_id: str) -> list[str]:
    df = con.execute(
        "SELECT DISTINCT course_key_guess FROM reviews "
        "WHERE prof_id = ? AND course_key_guess IS NOT NULL ORDER BY course_key_guess",
        [prof_id],
    ).fetchdf()
    return df["course_key_guess"].tolist()


def get_course_reviews(con, course_key: str) -> pd.DataFrame:
    return con.execute(
        "SELECT r.*, p.first_name, p.last_name FROM reviews r "
        "JOIN prof_summary p ON r.prof_id = p.prof_id "
        "WHERE r.course_key_guess = ? ORDER BY r.date DESC",
        [course_key],
    ).fetchdf()


# ---------------------------------------------------------------------------
# Schedule page
# ---------------------------------------------------------------------------

def list_terms(con) -> list[int]:
    df = con.execute("SELECT DISTINCT term_id FROM upcoming_sections ORDER BY term_id").fetchdf()
    return df["term_id"].tolist()


def get_sections_for_term(con, term_id: int, query: str | None = None) -> pd.DataFrame:
    sql = (
        "SELECT s.*, p.avg_rating, p.avg_difficulty, p.num_ratings "
        "FROM upcoming_sections s LEFT JOIN prof_summary p ON s.prof_id = p.prof_id "
        "WHERE s.term_id = ?"
    )
    params = [term_id]
    if query:
        sql += " AND (s.course_key ILIKE ? OR s.course_title ILIKE ? OR s.instructor ILIKE ?)"
        params += [f"%{query}%"] * 3
    sql += " ORDER BY s.course_key, s.section_number"
    return con.execute(sql, params).fetchdf()


# ---------------------------------------------------------------------------
# About page
# ---------------------------------------------------------------------------

def get_data_sources(con) -> pd.DataFrame:
    return con.execute("SELECT * FROM data_sources").fetchdf()


def get_match_rate_stats(con) -> pd.DataFrame:
    return con.execute(
        "SELECT source, match_label, COUNT(*) AS n FROM prof_crosswalk "
        "WHERE source IN ('grades', 'sections', 'salaries') "
        "GROUP BY source, match_label ORDER BY source, match_label"
    ).fetchdf()
