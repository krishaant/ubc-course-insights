import plotly.graph_objects as go
import streamlit as st

import config
from dashboard import data, style

st.set_page_config(page_title="Professor — UBC Course Insights", layout="wide")
style.inject_css()

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
if st.query_params.get("prof_id") != selected_id:
    st.query_params["prof_id"] = selected_id  # shareable/bookmarkable once loaded

summary = data.get_prof_summary(con, selected_id)
if summary is None:
    st.error("No data for this professor.")
    st.stop()

style.render_header(
    f"{summary['first_name'] or ''} {summary['last_name'] or ''}".strip() or chosen_display,
    summary["department"] or "Department unknown (no RMP match)",
)
st.markdown(style.match_label_badge(summary["match_label"]), unsafe_allow_html=True)

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
    st.caption("Click a row to view that course.")
    sections_event = st.dataframe(
        display[["course_key", "section_number", "status", "term_id"]].rename(columns={
            "course_key": "Course", "section_number": "Section", "status": "Status", "term_id": "Term",
        }),
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="prof_sections_table",
    )
    sections_sel = sections_event["selection"]["rows"]
    if sections_sel:
        st.session_state["selected_course_key"] = sections.iloc[sections_sel[0]]["course_key"]
        st.switch_page("pages/1_Course.py")

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
    display_courses = courses_df[[
        "course_key", "course_title", "num_sections", "total_reported",
        "prof_avg", "course_avg", "grade_delta",
    ]].rename(columns={
        "course_key": "Course", "course_title": "Title", "num_sections": "Sections",
        "total_reported": "Students", "prof_avg": "Their avg", "course_avg": "Course avg",
        "grade_delta": "Delta",
    })
    st.caption("Click a row to view that course.")
    courses_event = st.dataframe(
        display_courses, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="prof_courses_table",
    )
    courses_sel = courses_event["selection"]["rows"]
    if courses_sel:
        st.session_state["selected_course_key"] = courses_df.iloc[courses_sel[0]]["course_key"]
        st.switch_page("pages/1_Course.py")

st.subheader("Reviews")
review_courses = data.get_prof_review_courses(con, selected_id)
if not review_courses:
    st.write(
        "No reviews on record — either not matched to RMP, or not included "
        "in the review pull (capped at the 20 most recent per professor)."
    )
else:
    rcol1, rcol2 = st.columns([2, 1])
    course_filter = rcol1.selectbox("Filter by course", ["(all courses)"] + review_courses)
    sort_choice = rcol2.selectbox("Sort by", ["Newest", "Most helpful"])

    reviews_df = data.get_prof_reviews(
        con, selected_id, course_key=None if course_filter == "(all courses)" else course_filter,
    )
    if sort_choice == "Most helpful":
        reviews_df = reviews_df.sort_values("helpful_rating", ascending=False)

    st.caption(f"{len(reviews_df)} review(s) — capped at this professor's 20 most recent on RMP overall, not per course.")
    for _, r in reviews_df.iterrows():
        st.markdown(style.render_review_card(r, show_course=True), unsafe_allow_html=True)
