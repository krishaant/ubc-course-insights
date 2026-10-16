import streamlit as st

import config
from dashboard import data, schedule, style

st.set_page_config(page_title="Schedule — UBC Course Insights", layout="wide")
style.inject_css()

con = data.connect()

style.render_header(
    "Build your schedule",
    "Add sections, spot time conflicts, and compare instructor ratings before you register.",
)

st.session_state.setdefault("schedule_entries", {})

term_ids = data.list_terms(con)
if not term_ids:
    st.error("No upcoming sections in the database yet.")
    st.stop()

term_labels = [config.TERM_NAMES.get(t, str(t)) for t in term_ids]
term_choice = st.selectbox("Term", term_labels, index=0)
selected_term = term_ids[term_labels.index(term_choice)]

st.subheader("Add sections")
query = st.text_input("Search by course code or instructor", placeholder="e.g. CPSC 110, or Gregor Kiczales")

if query:
    results = data.get_sections_for_term(con, selected_term, query)
    if results.empty:
        st.write("No matching sections for this term.")
    else:
        shown = results.head(50)
        if len(results) > 50:
            st.caption(f"Showing first 50 of {len(results)} matches — refine your search.")
        for _, row in shown.iterrows():
            entry_key = f"{row['term_id']}_{row['course_key']}_{row['section_number']}"
            days = schedule.parse_days(row["days"])
            cols = st.columns([2, 1.2, 1.6, 2, 2, 1.3])
            cols[0].markdown(f"**{row['course_key']}** · Sec {row['section_number']}")
            cols[1].write(row["status"] or "—")
            cols[2].write(", ".join(schedule.DAY_LABEL[d] for d in days) or "No fixed days")
            if days:
                cols[3].write(f"{schedule.format_time(row['start_time_sec'])} – {schedule.format_time(row['end_time_sec'])}")
            else:
                cols[3].write("—")
            rating = f"★ {row['avg_rating']:.1f}" if row["avg_rating"] == row["avg_rating"] else "No rating"
            cols[4].write(f"{row['instructor'] or '—'}  \n{rating}")

            already_added = entry_key in st.session_state["schedule_entries"]
            if cols[5].button(
                "Added ✓" if already_added else "Add",
                key=f"add_{entry_key}",
                disabled=already_added,
                type="primary",
            ):
                st.session_state["schedule_entries"][entry_key] = {
                    "key": entry_key,
                    "course_key": row["course_key"],
                    "section": row["section_number"],
                    "term_id": row["term_id"],
                    "instructor": row["instructor"],
                    "avg_rating": row["avg_rating"],
                    "avg_difficulty": row["avg_difficulty"],
                    "days": days,
                    "start": row["start_time_sec"],
                    "end": row["end_time_sec"],
                    "prof_id": row["prof_id"],
                }
                st.rerun()
else:
    st.caption("Search above to find sections to add to your schedule.")

st.divider()
st.subheader("Your schedule")

current_entries = [e for e in st.session_state["schedule_entries"].values() if e["term_id"] == selected_term]

if not current_entries:
    st.write("No sections added for this term yet.")
else:
    top_cols = st.columns([5, 1])
    top_cols[0].caption(f"{len(current_entries)} section(s) added for {term_choice}.")
    if top_cols[1].button("Clear all"):
        for e in current_entries:
            del st.session_state["schedule_entries"][e["key"]]
        st.rerun()

    conflicts = schedule.find_conflicts([e for e in current_entries if e["days"]])
    if conflicts:
        for a, b, conflict_days in conflicts:
            day_str = ", ".join(schedule.DAY_LABEL[d] for d in conflict_days)
            st.error(
                f"⚠ **{a['course_key']} Sec {a['section']}** conflicts with "
                f"**{b['course_key']} Sec {b['section']}** on {day_str} "
                f"({schedule.format_time(a['start'])}–{schedule.format_time(a['end'])} overlaps "
                f"{schedule.format_time(b['start'])}–{schedule.format_time(b['end'])})."
            )
    else:
        st.success("No time conflicts.")

    no_time = [e for e in current_entries if not e["days"]]
    st.markdown(schedule.render_grid(current_entries), unsafe_allow_html=True)
    if no_time:
        st.caption(
            f"{len(no_time)} section(s) have no fixed meeting time and aren't shown in the grid above: "
            + ", ".join(f"{e['course_key']} Sec {e['section']}" for e in no_time)
        )

    st.markdown("**Added sections**")
    for e in current_entries:
        with st.container(border=True):
            rcols = st.columns([3, 2, 1.6, 2.6, 1.3])
            rcols[0].write(f"**{e['course_key']}** · Sec {e['section']}")
            rcols[1].write(e["instructor"] or "—")
            rating = f"★ {e['avg_rating']:.1f}" if e["avg_rating"] == e["avg_rating"] else "No rating"
            rcols[2].write(rating)
            if e["days"]:
                rcols[3].write(
                    ", ".join(schedule.DAY_LABEL[d] for d in e["days"])
                    + f" · {schedule.format_time(e['start'])}–{schedule.format_time(e['end'])}"
                )
            else:
                rcols[3].write("No fixed time")
            if rcols[4].button("Remove", key=f"remove_{e['key']}", use_container_width=True):
                del st.session_state["schedule_entries"][e["key"]]
                st.rerun()
