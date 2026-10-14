<div align="center">

# UBC Course Insights

**Who teaches each course, how students rate them, how their grades compare
to the course average, and what they're paid.**

[![Python](https://img.shields.io/badge/Python-3.12-0055B7?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![DuckDB](https://img.shields.io/badge/DuckDB-analytics-FFD600?style=flat-square&logo=duckdb&logoColor=002145)](https://duckdb.org/)
[![License](https://img.shields.io/badge/license-private-002145?style=flat-square)](#)

*Unofficial student project — not affiliated with or endorsed by UBC.*

</div>

---

## What it does
When I am registering for classes I usually have Workday, RateMyProf, A calendar, and UBCGrades open at the same time. 

A single place to answer the question every UBC student actually has before registering: **is this course/professor worth it?**

- **Search** any course or professor by name — typo-tolerant.
- **Course pages**, grade trend over time (1996–2025), max/min section
  averages, who's teaching it now, full term-by-term history with
  drill-down grade distributions by UBC letter grade, every professor
  who's taught it ranked by rating or grade leniency.
- **Professor pages**, RMP rating & difficulty, salary history (SOFI
  public disclosures), every course they teach with their grade delta vs.
  the course average, and their actual reviews — filterable by course.
- **About page**, exactly where every number comes from, with honest
  caveats, not a results dashboard that hides its own gaps.

## Architecture

Five scripts, run by hand, each handing a clean artifact to the next.
Nothing in the Streamlit app ever calls a live source, it only ever reads
the one database the pipeline built.

![Pipeline diagram: four sources (RateMyProfessor, UBCGrades, UBC Course Schedule, UBC Financial Statements) feed extract scripts, which flow through clean.py, match.py and build.py into nine DuckDB tables, stored in data/final/ubc.duckdb, served by dashboard/data.py to four Streamlit pages, and deployed via GitHub to Streamlit Cloud.](docs/architecture.png)

| Stage | Script | What it does |
|---|---|---|
| **Extract** | `extract_rmp.py` · `extract_grades.py` · `extract_sections.py` · `parse_salaries.py` | Pulls each source untouched — RMP via its GraphQL API, grades via a sparse clone of [DonneyF/ubc-pair-grade-data](https://github.com/DonneyF/ubc-pair-grade-data), the course schedule via UBC's own public JSON:API, salaries from hand-downloaded SOFI PDFs. |
| **Clean** | `clean.py` | One tidy table per source — `"Smith, John"` and `"John Smith"` become the same name, multi-instructor sections get exploded one row per instructor, parsing noise (e.g. `"Furnishings, equipment"` reading like a name) gets filtered out. |
| **Match** | `match.py` | The hard part: deciding that `"J. Smith"` in the grades data and `"John Smith"` on RateMyProfessors are the same person. Every link is labeled `exact` / `no_rmp` / `unverified` / `ambiguous_within_rmp` — never silently guessed. |
| **Build** | `build.py` | Assembles everything into `data/final/ubc.duckdb` — one row per professor per course, ready to query. Dropped and rebuilt fresh every run. |
| **Serve** | `app.py` + `pages/` | A Streamlit app that reads only `dashboard/data.py`, which reads only the DB. |
| **Deploy** | — | `git push` → private GitHub repo → Streamlit Community Cloud build → an unlisted live link. |

## Data, for real

Nine tables land in `data/final/ubc.duckdb`:

| Table | Rows | What it holds |
|---|---:|---|
| `course_summary` | 12,187 | One row per course — overall/max/min section average, terms offered, sections offered. |
| `course_terms` | 325,027 | One row per (section, instructor) grade record, 1996S–2025W. |
| `prof_summary` / `prof_master` | 23,854 | One row per professor — RMP rating, difficulty, grade delta, match confidence. 4,117 have an RMP match. |
| `prof_course_summary` | 75,859 | One row per (professor, course) — their average vs. the course average. |
| `upcoming_sections` | 16,530 | Current + next term's schedule, with instructor rating joined in. |
| `salaries` | 35,467 | SOFI public salary disclosures, FY21–FY25. |
| `reviews` | 41,646 | RMP review text, capped at 20 most recent per professor. |
| `prof_crosswalk` | 48,785 | Every name→RMP match attempt, including the unresolved ones. |
| `data_sources` | 5 | Metadata for the About page — last pulled, row count, notes. |

**What a row actually looks like** — real data, pulled straight from the DB:

`course_summary`

| course_key | course_title | overall_avg | max_section_avg | min_section_avg | num_terms_offered | first_term | last_term |
|---|---|---:|---:|---:|---:|---|---|
| CPSC 110 | Computation, Programs, and Programming | 74.1 | 93.5 | 60.0 | 28 | 2009W | 2025W |
| ECON 101 | Prncpls Microecon | 69.0 | 80.1 | 60.9 | 51 | 2000W | 2025W |
| STAT 251 | Elementary Statistics | 73.0 | 84.9 | 60.9 | 60 | 1996S | 2025W |

`prof_summary`

| first_name | last_name | department | avg_rating | avg_difficulty | num_ratings | overall_grade_delta | match_label |
|---|---|---|---:|---:|---:|---:|---|
| Patrick | Walls | Mathematics | 3.6 | 3.8 | 80 | +2.37 | exact |

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `localhost:8501`. The repo ships with a built `data/final/ubc.duckdb`
snapshot, so the app runs immediately — no pipeline run required.

To refresh the data yourself:

```bash
python3 -m pipeline.extract_rmp        # or extract_grades / extract_sections / parse_salaries
python3 -m pipeline.clean
python3 -m pipeline.match
python3 -m pipeline.build
```

## Known limitations

Documented honestly in the app's own About page, not swept under the rug:

- Reviews are capped at each professor's **20 most recent** on RMP (a hard
  limit in the API client used to pull them) — 222 of 4,117 matched
  professors don't have reviews pulled yet either (a network blip, not
  retried).
- A review's course is free text on RMP (e.g. `MATH100`) — matched to a
  real course by exact normalization, not fuzzy matching (~82% resolve).
- Ambiguous professor-name matches are labeled `unverified` rather than
  auto-resolved; `data/overrides.csv` exists to hand-correct them but has
  never actually been used.
- No building/room data exists for sections — UBC's public schedule API
  doesn't expose it, and Workday itself is never scraped.
- No scheduled refresh — every pipeline step above is a manual run.

## Tech stack

Python · Streamlit · DuckDB · Plotly · pandas · pdfplumber
