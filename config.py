"""One place for the knobs the spec calls out explicitly."""

from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "final" / "ubc.duckdb"

# Per spec: salary shown per professor, gated behind this flag. Flip to
# False before anything goes public -- see spec's "Later (not MVP)" note
# about revisiting per-professor salary once public.
SHOW_INDIVIDUAL_SALARY = True

# Bayesian shrinkage constant for the adjusted-rating sort toggle:
# (n * prof_avg + K * global_avg) / (n + K)
ADJUSTED_RATING_K = 5

RMP_PROFESSOR_URL = "https://www.ratemyprofessors.com/professor/{legacy_id}"

# UBC-V term IDs -> readable names, from pipeline/extract_sections.py's
# TERM_IDS (kept here too since this is a display concern, not an
# extraction one).
TERM_NAMES = {
    1449: "2025-26 Winter Term 1",
    1450: "2025-26 Winter Term 2",
    1452: "2026 Summer Session",
    1453: "2026-27 Winter Term 1",
    1454: "2026-27 Winter Term 2",
}

LOW_DATA_REVIEW_THRESHOLD = 5
LOW_DATA_SECTION_THRESHOLD = 2
