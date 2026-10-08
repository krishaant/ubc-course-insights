"""Step 2 (EXTRACT) for the UBC grades source.

Pulls UBC Vancouver grade-distribution CSVs from DonneyF/ubc-pair-grade-data
(tableau-dashboard-v2/UBCV only — UBCO and pre-2021 formats are out of
scope) via a sparse git clone, and saves them untouched to
data/raw/grades/<date>/. No cleaning or instructor-splitting happens here —
that's pipeline/clean.py.
"""

import datetime
import shutil
import subprocess
from pathlib import Path

import pandas as pd

SOURCE_REPO = "https://github.com/DonneyF/ubc-pair-grade-data.git"
SPARSE_PATH = "tableau-dashboard-v2/UBCV"

EXPECTED_COLUMNS = [
    "Campus", "Year", "Session", "Subject", "Course", "Detail", "Section",
    "Title", "Professor", "Reported", "Avg", "Median", "Percentile (25)",
    "Percentile (75)", "High", "Low", "<50", "50-54", "55-59", "60-63",
    "64-67", "68-71", "72-75", "76-79", "80-84", "85-89", "90-100",
]


def _sparse_clone(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1",
         SOURCE_REPO, str(dest)],
        check=True,
    )
    subprocess.run(["git", "sparse-checkout", "init", "--cone"], cwd=dest, check=True)
    subprocess.run(["git", "sparse-checkout", "set", SPARSE_PATH], cwd=dest, check=True)
    subprocess.run(["git", "checkout"], cwd=dest, check=True)


def _verify(ubcv_dir: Path) -> None:
    term_dirs = sorted(p for p in ubcv_dir.iterdir() if p.is_dir())
    if not term_dirs:
        raise RuntimeError(f"No term folders found under {ubcv_dir}")

    print(f"Found {len(term_dirs)} terms: {[t.name for t in term_dirs]}")

    bad_columns = []
    bad_overall = []
    total_files = 0
    total_rows = 0

    for term_dir in term_dirs:
        csvs = sorted(term_dir.glob("*.csv"))
        total_files += len(csvs)
        for csv_path in csvs:
            df = pd.read_csv(csv_path)
            total_rows += len(df)
            if list(df.columns) != EXPECTED_COLUMNS:
                bad_columns.append(csv_path)
            if "Detail" in df.columns and (df["Detail"].astype(str) == "OVERALL").any():
                bad_overall.append(csv_path)

    print(f"Total files: {total_files}, total rows: {total_rows}")

    if bad_columns:
        print(f"WARNING: {len(bad_columns)} files have unexpected columns, e.g. {bad_columns[:3]}")
    else:
        print("Column schema consistent across every term.")

    if bad_overall:
        print(f"WARNING: {len(bad_overall)} files contain OVERALL rows, e.g. {bad_overall[:3]}")
    else:
        print("No OVERALL rows found (clean.py's drop-OVERALL step should be a no-op, kept as a safety net).")


def extract_grades() -> Path:
    out_dir = Path("data/raw/grades") / datetime.date.today().isoformat()
    clone_dir = out_dir / "ubc-pair-grade-data"

    print(f"Sparse-cloning {SOURCE_REPO} ({SPARSE_PATH}) into {clone_dir}...")
    _sparse_clone(clone_dir)

    ubcv_dir = clone_dir / SPARSE_PATH
    _verify(ubcv_dir)

    print(f"Saved to {ubcv_dir}")
    return ubcv_dir


if __name__ == "__main__":
    extract_grades()
