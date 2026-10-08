"""Step 2 (EXTRACT) for the SOFI salary source.

PDFs are added by hand into data/raw/salaries/<fiscal year>/ (not scraped —
see your spec: "SOFI salary PDFs: you download by hand, yearly"). This
script just parses whatever PDFs are already there and saves the raw
name/salary pairs untouched to data/raw/salaries/<fiscal year>/parsed.csv.

Regex and parsing approach carried over from the working version in the old
ECON323 project's ProfessorSalaryScrapper.ipynb (the .py file sitting next
to it has a stale bug — NameError on capitalized Name/Salary — that the
notebook itself doesn't have; this reimplements the notebook's version).

Known limitation (same as the original): the regex assumes "Lastname,
Firstname" with single-word names — it will miss or mis-split names with
middle initials, hyphens, or multi-word surnames. clean.py's matching step
should treat this source as noisier than RMP/grades.
"""

import re
from pathlib import Path

import pandas as pd
import pdfplumber

NAME_SALARY_PATTERN = r"([A-Za-z]+,\s[A-Za-z]+)\s+([\d,]+)"

SALARIES_DIR = Path("data/raw/salaries")


def parse_salary_pdf(pdf_path: Path) -> pd.DataFrame:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(
            page.extract_text() for page in pdf.pages if page.extract_text()
        )
    matches = re.findall(NAME_SALARY_PATTERN, text)
    return pd.DataFrame(matches, columns=["Name", "Salary"])


def parse_salaries() -> list[Path]:
    if not SALARIES_DIR.exists():
        raise RuntimeError(
            f"{SALARIES_DIR} doesn't exist. Add SOFI PDFs to "
            f"{SALARIES_DIR}/<fiscal year>/ first."
        )

    out_paths = []
    for year_dir in sorted(SALARIES_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        pdfs = sorted(year_dir.glob("*.pdf"))
        if not pdfs:
            print(f"{year_dir.name}: no PDF found, skipping")
            continue
        if len(pdfs) > 1:
            print(f"{year_dir.name}: WARNING, {len(pdfs)} PDFs found, using {pdfs[0].name}")

        df = parse_salary_pdf(pdfs[0])
        out_path = year_dir / "parsed.csv"
        df.to_csv(out_path, index=False)
        print(f"{year_dir.name}: parsed {len(df)} name/salary rows from {pdfs[0].name} -> {out_path}")
        out_paths.append(out_path)

    return out_paths


if __name__ == "__main__":
    parse_salaries()
