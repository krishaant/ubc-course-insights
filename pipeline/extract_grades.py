"""Step 2 (EXTRACT) for the UBC grades source.

Pulls UBC Vancouver grade-distribution CSVs from DonneyF/ubc-pair-grade-data
via a single sparse git clone covering all three eras the repo has (UBCO is
out of scope), and saves them untouched to data/raw/grades/<date>/. No
cleaning, era-precedence resolution, or instructor-splitting happens here —
that's pipeline/clean.py.

The three eras have genuinely different schemas (confirmed against live
data, not assumed from the README):
  - pair-reports/UBC        1996-2018, "Last, First" professor names,
                             Pass/Fail/Withdrew/Audit counts + finer buckets
  - tableau-dashboard/UBCV  2014-2021, "First Last" names (';'-joined for
                             multiple), includes TA names mixed into
                             Professor (per the repo's own README)
  - tableau-dashboard-v2/UBCV  2021-2025, "First Last" names, no TA names,
                             adds percentiles, no Std dev

Eras overlap for 2014-2018 (pair-reports vs v1) and 2021 (v1 vs v2);
clean.py resolves precedence (newer era wins), not this script.
"""

import datetime
import shutil
import subprocess
from pathlib import Path

import pandas as pd

SOURCE_REPO = "https://github.com/DonneyF/ubc-pair-grade-data.git"

ERAS = {
    "pair_reports": {
        "sparse_path": "pair-reports/UBC",
        "expected_columns": [
            "Campus", "Year", "Session", "Subject", "Course", "Detail", "Section",
            "Title", "Professor", "Enrolled", "Avg", "Std dev", "High", "Low",
            "Pass", "Fail", "Withdrew", "Audit", "Other",
            "0-9", "10-19", "20-29", "30-39", "40-49",
            "<50", "50-54", "55-59", "60-63", "64-67", "68-71", "72-75", "76-79", "80-84", "85-89", "90-100",
        ],
    },
    "tableau_v1": {
        "sparse_path": "tableau-dashboard/UBCV",
        "expected_columns": [
            "Campus", "Year", "Session", "Subject", "Course", "Detail", "Section",
            "Title", "Professor", "Enrolled", "Avg", "Std dev", "High", "Low",
            "<50", "50-54", "55-59", "60-63", "64-67", "68-71", "72-75", "76-79", "80-84", "85-89", "90-100",
        ],
    },
    "tableau_v2": {
        "sparse_path": "tableau-dashboard-v2/UBCV",
        "expected_columns": [
            "Campus", "Year", "Session", "Subject", "Course", "Detail", "Section",
            "Title", "Professor", "Reported", "Avg", "Median", "Percentile (25)",
            "Percentile (75)", "High", "Low", "<50", "50-54", "55-59", "60-63",
            "64-67", "68-71", "72-75", "76-79", "80-84", "85-89", "90-100",
        ],
    },
}


def _sparse_clone(dest: Path, sparse_paths: list[str]) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1",
         SOURCE_REPO, str(dest)],
        check=True,
    )
    subprocess.run(["git", "sparse-checkout", "init", "--cone"], cwd=dest, check=True)
    subprocess.run(["git", "sparse-checkout", "set", *sparse_paths], cwd=dest, check=True)
    subprocess.run(["git", "checkout"], cwd=dest, check=True)


def _verify_era(era_name: str, era_dir: Path, expected_columns: list[str]) -> None:
    term_dirs = sorted(p for p in era_dir.iterdir() if p.is_dir())
    if not term_dirs:
        raise RuntimeError(f"No term folders found under {era_dir}")

    bad_columns = []
    total_files = 0
    total_rows = 0

    for term_dir in term_dirs:
        csvs = sorted(term_dir.glob("*.csv"))
        total_files += len(csvs)
        for csv_path in csvs:
            df = pd.read_csv(csv_path)
            total_rows += len(df)
            if list(df.columns) != expected_columns:
                bad_columns.append(csv_path)

    print(f"{era_name}: {len(term_dirs)} terms ({term_dirs[0].name}-{term_dirs[-1].name}), "
          f"{total_files} files, {total_rows} rows")
    if bad_columns:
        print(f"  WARNING: {len(bad_columns)} files have unexpected columns, e.g. {bad_columns[:3]}")


def extract_grades() -> dict[str, Path]:
    out_dir = Path("data/raw/grades") / datetime.date.today().isoformat()
    clone_dir = out_dir / "ubc-pair-grade-data"

    sparse_paths = [e["sparse_path"] for e in ERAS.values()]
    print(f"Sparse-cloning {SOURCE_REPO} ({', '.join(sparse_paths)}) into {clone_dir}...")
    _sparse_clone(clone_dir, sparse_paths)

    era_dirs = {}
    for era_name, era in ERAS.items():
        era_dir = clone_dir / era["sparse_path"]
        _verify_era(era_name, era_dir, era["expected_columns"])
        era_dirs[era_name] = era_dir

    print(f"Saved to {clone_dir}")
    return era_dirs


if __name__ == "__main__":
    extract_grades()
