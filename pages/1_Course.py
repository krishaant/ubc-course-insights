import ast

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from dashboard import data

st.set_page_config(page_title="Course — UBC Course Insights", layout="wide")

con = data.connect()

all_courses = data.list_all_courses(con)
course_keys = all_courses["course_key"].tolist()

default_key = st.session_state.get("selected_course_key") or st.query_params.get("course_key")
if default_key not in course_keys:
    default_key = course_keys[0] if course_keys else None

selected = st.selectbox(
    "Course", course_keys,
    index=course_keys.index(default_key) if default_key in course_keys else 0,
)
st.session_state["selected_course_key"] = selected
st.query_params["course_key"] = selected  # shareable/bookmarkable once loaded

summary = data.get_course_summary(con, selected)
if summary is None:
    st.error("No data for this course.")
    st.stop()


def format_time(seconds) -> str:
    if seconds is None or (isinstance(seconds, float) and seconds != seconds):
        return "—"
    h, m = divmod(int(seconds), 3600)
    return f"{h:02d}:{m // 60:02d}"


def format_days(raw) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "—"
    try:
        days = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw
    label = {"m": "Mon", "t": "Tue", "w": "Wed", "th": "Thu", "f": "Fri", "s": "Sat", "su": "Sun"}
    return ", ".join(label.get(d, d) for d in days)


st.title(selected)
st.caption(summary["course_title"] or "")

def fmt(val, decimals=1):
    return f"{val:.{decimals}f}" if val == val else "—"  # val == val is False for NaN


col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Overall avg", fmt(summary["overall_avg"]))
col2.metric("Max avg", fmt(summary["max_section_avg"]))
col3.metric("Min avg", fmt(summary["min_section_avg"]))
col4.metric("Terms", int(summary["num_terms_offered"]))
col5.metric("Sections", int(summary["num_sections_total"]))

trend = data.get_course_trend_by_term(con, selected)
if not trend.empty:
    trend = trend.sort_values("term")
    range_choice = st.radio(
        "Chart range", ["Past 5 years", "All years"], horizontal=True, label_visibility="collapsed",
    )
    # Terms run ~2/year (W + S), so the last 10 is a close enough proxy for
    # "5 years" -- matches what ubcgrades.com itself shows.
    chart_df = trend.tail(10) if range_choice == "Past 5 years" else trend
    fig = px.line(chart_df, x="term", y="avg", markers=True, title="Average grade by term")
    st.plotly_chart(fig, use_container_width=True)

tab_now, tab_history, tab_grades, tab_profs = st.tabs(["Now", "History", "Grades", "Professors"])

with tab_now:
    now_df = data.get_course_now(con, selected)
    if now_df.empty:
        st.write("No sections scheduled for the current or next term.")
    else:
        display = now_df.copy()
        display["term_id"] = display["term_id"].map(config.TERM_NAMES).fillna(display["term_id"])
        display["days"] = display["days"].apply(format_days)
        display["start"] = display["start_time_sec"].apply(format_time)
        display["end"] = display["end_time_sec"].apply(format_time)
        display["location"] = "See Workday"
        st.dataframe(
            display[[
                "term_id", "section_number", "status", "instructional_method", "days", "start", "end",
                "location", "instructor", "avg_rating", "num_ratings",
            ]].rename(columns={
                "term_id": "Term", "section_number": "Section", "status": "Status", "instructional_method": "Activity",
                "days": "Days", "start": "Start", "end": "End", "location": "Location",
                "instructor": "Instructor", "avg_rating": "Rating", "num_ratings": "# Reviews",
            }),
            use_container_width=True, hide_index=True,
        )

with tab_history:
    hist_df = data.get_course_history(con, selected)
    st.dataframe(
        hist_df[["term", "section", "instructor", "reported", "avg"]].rename(columns={
            "term": "Term", "section": "Section", "instructor": "Instructor",
            "reported": "Enrolled", "avg": "Average",
        }),
        use_container_width=True, hide_index=True,
    )

with tab_grades:
    profs_for_overlay = data.get_course_professors(con, selected)
    overlay_name = st.selectbox(
        "Overlay one professor's distribution",
        ["(all instructors)"] + [
            f"{r['first_name']} {r['last_name']}" for _, r in profs_for_overlay.iterrows()
        ],
    )
    dist_all = data.get_grade_distribution(con, selected)
    fig = go.Figure()
    fig.add_bar(x=data.GRADE_BUCKET_COLS, y=dist_all.values, name="All instructors")
    if overlay_name != "(all instructors)":
        row = profs_for_overlay[
            (profs_for_overlay["first_name"] + " " + profs_for_overlay["last_name"]) == overlay_name
        ].iloc[0]
        dist_prof = data.get_grade_distribution(con, selected, prof_id=row["prof_id"])
        fig.add_bar(x=data.GRADE_BUCKET_COLS, y=dist_prof.values, name=overlay_name)
    fig.update_layout(title="Grade distribution", barmode="group", xaxis_title="Grade range", yaxis_title="Students")
    st.plotly_chart(fig, use_container_width=True)

with tab_profs:
    profs_df = data.get_course_professors(con, selected)
    if profs_df.empty:
        st.write("No professor data for this course.")
    else:
        sort_by = st.selectbox(
            "Sort by", ["Quality (raw)", "Quality (adjusted)", "Grade delta (easiest)", "Most reviews"],
        )
        sort_col, ascending = {
            "Quality (raw)": ("avg_rating", False),
            "Quality (adjusted)": ("adjusted_rating", False),
            "Grade delta (easiest)": ("grade_delta", False),
            "Most reviews": ("num_ratings", False),
        }[sort_by]
        profs_df = profs_df.sort_values(sort_col, ascending=ascending, na_position="last")

        display = profs_df.copy()
        display["low_data"] = display["num_ratings"].fillna(0) < 5
        for _, row in display.iterrows():
            cols = st.columns([3, 2, 2, 2, 2, 2])
            cols[0].write(f"**{row['first_name']} {row['last_name']}**")
            cols[1].write(f"Rating: {row['avg_rating']:.2f}" if row["avg_rating"] == row["avg_rating"] else "No rating")
            cols[2].write(f"Difficulty: {row['avg_difficulty']:.2f}" if row["avg_difficulty"] == row["avg_difficulty"] else "—")
            cols[3].write(f"Grade Δ: {row['grade_delta']:+.1f}" if row["grade_delta"] == row["grade_delta"] else "—")
            badge = {"exact": "✓ matched", "no_rmp": "no RMP page", "unverified": "⚠ unverified match"}.get(row["match_label"], row["match_label"])
            cols[4].caption(badge + (" · low data" if row["low_data"] else ""))
            if cols[5].button("View profile", key=f"prof_link_{row['prof_id']}"):
                st.session_state["selected_prof_id"] = row["prof_id"]
                st.switch_page("pages/2_Professor.py")

            course_reviews = data.get_prof_reviews(con, row["prof_id"], course_key=selected)
            if not course_reviews.empty:
                with st.expander(f"{len(course_reviews)} review(s) for {selected}"):
                    for _, r in course_reviews.iterrows():
                        date_str = str(r["date"]).split(" ")[0] if r["date"] else ""
                        st.markdown(f"_{date_str}_ — {r['comment'] if r['comment'] else '(no comment text)'}")
                        st.caption(f"Clarity: {r['clarity_rating']} · Difficulty: {r['difficulty_rating']}")

st.caption(
    "Reviews are capped at each professor's 20 most recent on RMP overall "
    "(a package limitation, not a data gap) — not all 20 are necessarily "
    "for this specific course."
)
