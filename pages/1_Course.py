import ast

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from dashboard import data, style

st.set_page_config(page_title="Course — UBC Course Insights", layout="wide")
style.inject_css()

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
if st.query_params.get("course_key") != selected:
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


style.render_header(selected, summary["course_title"] or "")

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
    if range_choice == "Past 5 years":
        # Filter by actual calendar year, not term count -- courses aren't
        # offered every term, so "last 10 terms" can span well over 5 years.
        trend_year = trend["term"].str[:4].astype(int)
        chart_df = trend[trend_year >= trend_year.max() - 4]
    else:
        chart_df = trend
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
        st.caption("Click a row to view that instructor's profile.")
        now_event = st.dataframe(
            display[[
                "term_id", "section_number", "status", "instructional_method", "days", "start", "end",
                "location", "instructor", "avg_rating", "num_ratings",
            ]].rename(columns={
                "term_id": "Term", "section_number": "Section", "status": "Status", "instructional_method": "Activity",
                "days": "Days", "start": "Start", "end": "End", "location": "Location",
                "instructor": "Instructor", "avg_rating": "Rating", "num_ratings": "# Reviews",
            }),
            use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row", key="course_now_table",
        )
        now_sel = now_event["selection"]["rows"]
        if now_sel:
            prof_id = now_df.iloc[now_sel[0]]["prof_id"]
            if prof_id == prof_id:  # not NaN
                st.session_state["selected_prof_id"] = prof_id
                st.switch_page("pages/2_Professor.py")

with tab_history:
    hist_df = data.get_course_history(con, selected)
    display_hist = hist_df[["term", "section", "instructor", "reported", "avg"]].rename(columns={
        "term": "Term", "section": "Section", "instructor": "Instructor",
        "reported": "Enrolled", "avg": "Average",
    })
    st.caption("Click a row to view that instructor's profile.")
    hist_event = st.dataframe(
        display_hist, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="course_history_table",
    )
    hist_sel = hist_event["selection"]["rows"]
    if hist_sel:
        prof_id = hist_df.iloc[hist_sel[0]]["prof_id"]
        if prof_id == prof_id:  # not NaN
            st.session_state["selected_prof_id"] = prof_id
            st.switch_page("pages/2_Professor.py")

    hist_df = hist_df.reset_index(drop=True)
    hist_labels = [
        f"{r['term']} · Section {r['section']}"
        + (f" · {r['instructor']}" if isinstance(r["instructor"], str) else "")
        for _, r in hist_df.iterrows()
    ]
    picked_label = st.selectbox(
        "Pick a term/section for the full grade distribution",
        hist_labels, key="history_picker", index=None,
        placeholder="Pick a term/section...",
    )

    if picked_label is None:
        st.caption("Pick a term/section above to see that offering's full grade distribution.")
    else:
        row = hist_df.iloc[hist_labels.index(picked_label)]
        st.divider()
        st.subheader(f"{selected} · {row['term']} · Section {row['section']}")

        mcols = st.columns(6)
        mcols[0].metric("Average", fmt(row["avg"]))
        mcols[1].metric("Median", fmt(row["median"]))
        mcols[2].metric("25th pct", fmt(row["pct_25"]))
        mcols[3].metric("75th pct", fmt(row["pct_75"]))
        mcols[4].metric("High", fmt(row["high"], decimals=0))
        mcols[5].metric("Low", fmt(row["low"], decimals=0))

        if row["prof_id"] == row["prof_id"]:  # not NaN
            if st.button(f"View {row['first_name']} {row['last_name']}'s profile", key="history_prof_link"):
                st.session_state["selected_prof_id"] = row["prof_id"]
                st.switch_page("pages/2_Professor.py")

        st.markdown("**Grade distribution**")
        bcol1, bcol2 = st.columns(2)
        buckets = data.GRADE_BUCKET_COLS
        half = len(buckets) // 2 + len(buckets) % 2
        for i, bucket in enumerate(buckets):
            target = bcol1 if i < half else bcol2
            count = row[bucket]
            count_str = str(int(count)) if count == count else "—"
            target.markdown(
                f"<div style='display:flex; justify-content:space-between; "
                f"padding:6px 0; border-bottom:1px solid rgba(128,128,128,0.2);'>"
                f"<span>{bucket}%</span>"
                f"<span style='background:#fce4e4; color:#b23b3b; border-radius:12px; "
                f"padding:2px 10px; font-weight:600;'>{count_str}</span></div>",
                unsafe_allow_html=True,
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
    fig.add_bar(x=data.GRADE_LETTER_LABELS, y=dist_all.values, name="All instructors")
    if overlay_name != "(all instructors)":
        row = profs_for_overlay[
            (profs_for_overlay["first_name"] + " " + profs_for_overlay["last_name"]) == overlay_name
        ].iloc[0]
        dist_prof = data.get_grade_distribution(con, selected, prof_id=row["prof_id"])
        fig.add_bar(x=data.GRADE_LETTER_LABELS, y=dist_prof.values, name=overlay_name)
    fig.update_layout(title="Grade distribution", barmode="group", xaxis_title="Grade", yaxis_title="Students")
    st.plotly_chart(fig, use_container_width=True)

    total_all = dist_all.sum()
    grade_table = pd.DataFrame({
        "Grade": data.GRADE_LETTER_LABELS,
        "Score range": data.GRADE_BUCKET_COLS,
        "Students": dist_all.values.astype(int),
        "% of class": [f"{(c / total_all * 100):.1f}%" if total_all else "—" for c in dist_all.values],
    })
    st.dataframe(grade_table, use_container_width=True, hide_index=True)

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
            badge_html = style.match_label_badge(row["match_label"])
            if row["low_data"]:
                badge_html += " <span style='color:#8A6100; font-size:0.78rem;'>· low data</span>"
            cols[4].markdown(badge_html, unsafe_allow_html=True)
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
