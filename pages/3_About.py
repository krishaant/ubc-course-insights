import streamlit as st

from dashboard import data, style

st.set_page_config(page_title="About — UBC Course Insights", layout="wide")
style.inject_css()

con = data.connect()

style.render_header("About this data")

st.subheader("Sources")
st.dataframe(data.get_data_sources(con), use_container_width=True, hide_index=True)

st.subheader("How the numbers are computed")
st.markdown(
    "- **Grade delta**: a professor's enrollment-weighted average grade in a "
    "course, minus that course's enrollment-weighted average across *all* "
    "instructors. Positive means they grade above the course average.\n"
    "- **Adjusted rating** (used only when sorting by it): Bayesian-shrunk "
    "toward the UBC-wide average rating, so a professor with 2 reviews "
    "doesn't rank above one with 200 just by chance. Raw rating is always "
    "shown alongside it.\n"
    "- **Match label**: how confidently a name in grades/schedule/salary "
    "data was matched to an RMP professor profile. `exact` = unambiguous. "
    "`unverified` = the name-key collides with 2+ RMP profiles and "
    "couldn't be resolved automatically. `no_rmp` = no RMP page found at "
    "all. See `data/overrides.csv` in the repo to hand-correct a specific "
    "match."
)

st.subheader("Match rate by source")
st.dataframe(data.get_match_rate_stats(con), use_container_width=True, hide_index=True)

st.subheader("Known limitations")
st.markdown(
    "- Reviews are capped at each professor's **20 most recent** on RMP "
    "(a hard limit in the package used to pull them, not something we "
    "chose) — not their full review history. Pulled for 3895 of 4117 "
    "matched professors (94.6%); the rest failed on a transient network "
    "issue during the pull and haven't been retried yet.\n"
    "- A review's course is free text on RMP (e.g. `MATH100`) and is only "
    "matched to a real course_key by exact normalization, not fuzzy "
    "matching — about 82% resolve to a real course, the rest show under "
    "\"course not specified\" on the professor's review list.\n"
    "- \"dept\"-based disambiguation for ambiguous name matches isn't "
    "implemented (needs a subject-code -> RMP-department mapping that "
    "doesn't exist yet) — those cases are labeled `unverified` instead.\n"
    "- No building/room data exists for sections — UBC's public schedule "
    "API doesn't expose it; Workday itself is not scraped.\n"
    "- Salary PDF parsing is a fairly blunt regex; a small number of rows "
    "are dropped as noise (financial-statement text that happened to match "
    "the name pattern) or missing (layout varies year to year)."
)
