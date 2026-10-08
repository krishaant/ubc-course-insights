import plotly.graph_objects as go
import streamlit as st

import config
from dashboard import data

st.set_page_config(page_title="Professor — UBC Course Insights", layout="wide")

con = data.connect()

all_profs = data.list_all_professors(con)
all_profs["display"] = all_profs["last_name"] + ", " + all_profs["first_name"]
id_by_display = dict(zip(all_profs["display"], all_profs["prof_id"]))

default_id = st.session_state.get("selected_prof_id") or st.query_params.get("prof_id")
options = all_profs["prof_id"].tolist()

selected_id = default_id if default_id in options else (options[0] if options else None)
display_default = all_profs.loc[all_profs["prof_id"] == selected_id, "display"].iloc[0] if selected_id else None

chosen_display = st.selectbox(
    "Professor", all_profs["display"].tolist(),
    index=all_profs["display"].tolist().index(display_default) if display_default else 0,
)
selected_id = id_by_display[chosen_display]
st.session_state["selected_prof_id"] = selected_id
st.query_params["prof_id"] = selected_id  # shareable/bookmarkable once loaded

summary = data.get_prof_summary(con, selected_id)
if summary is None:
    st.error("No data for this professor.")
    st.stop()

st.title(f"{summary['first_name'] or ''} {summary['last_name'] or ''}".strip() or chosen_display)
st.caption(summary["department"] or "Department unknown (no RMP match)")

badge = {
    "exact": "✓ matched to RMP",
    "no_rmp": "No RMP page found",
    "unverified": "⚠ ambiguous match — unverified",
}.get(summary["match_label"], summary["match_label"])
st.caption(badge)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Rating", f"{summary['avg_rating']:.2f}" if summary["avg_rating"] == summary["avg_rating"] else "—")
col2.metric("Difficulty", f"{summary['avg_difficulty']:.2f}" if summary["avg_difficulty"] == summary["avg_difficulty"] else "—")
col3.metric("Would take again", f"{summary['would_take_again_percent']:.0f}%" if summary["would_take_again_percent"] == summary["would_take_again_percent"] else "—")
col4.metric("# Reviews", int(summary["num_ratings"]) if summary["num_ratings"] == summary["num_ratings"] else 0)

st.metric("Overall grade delta (vs course averages)", f"{summary['overall_grade_delta']:+.2f}" if summary["overall_grade_delta"] == summary["overall_grade_delta"] else "—")

if summary["legacy_id"] == summary["legacy_id"]:
    st.link_button("View on RateMyProfessors", config.RMP_PROFESSOR_URL.format(legacy_id=int(summary["legacy_id"])))

sections = data.get_prof_sections(con, selected_id)
st.subheader("Currently teaching")
if sections.empty:
    st.write("No current or upcoming sections.")
else:
    display = sections.copy()
    display["term_id"] = display["term_id"].map(config.TERM_NAMES).fillna(display["term_id"])
    st.dataframe(
        display[["course_key", "section_number", "status", "term_id"]].rename(columns={
            "course_key": "Course", "section_number": "Section", "status": "Status", "term_id": "Term",
        }),
        use_container_width=True, hide_index=True,
    )

if config.SHOW_INDIVIDUAL_SALARY:
    st.subheader("Salary (SOFI disclosure)")
    salary_df = data.get_prof_salary(con, selected_id)
    if salary_df.empty:
        st.write("No disclosed salary on record (may be below the $75k threshold, or not yet matched).")
    else:
        fig = go.Figure()
        fig.add_bar(x=salary_df["fiscal_year"], y=salary_df["salary"])
        fig.update_layout(title="Salary by fiscal year", yaxis_title="CAD")
        st.plotly_chart(fig, use_container_width=True)

st.subheader("Courses taught")
courses_df = data.get_prof_courses(con, selected_id)
if courses_df.empty:
    st.write("No grade history on record for this professor.")
else:
    st.dataframe(
        courses_df[[
            "course_key", "course_title", "num_sections", "total_reported",
            "prof_avg", "course_avg", "grade_delta",
        ]].rename(columns={
            "course_key": "Course", "course_title": "Title", "num_sections": "Sections",
            "total_reported": "Students", "prof_avg": "Their avg", "course_avg": "Course avg",
            "grade_delta": "Delta",
        }),
        use_container_width=True, hide_index=True,
    )

st.caption("Review text isn't available yet — not pulled from RMP for this build.")
