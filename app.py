import streamlit as st

from dashboard import data, style

st.set_page_config(page_title="UBC Course Insights", layout="wide")
style.inject_css()

style.render_header(
    "UBC Course Insights",
    "Who teaches each course, how students rate them, how their grades "
    "compare to the course average, and what they're paid.",
)

con = data.connect()

query = st.text_input("Search a course or professor", placeholder="e.g. STAT 344, or Patrick Walls")

if query:
    results = data.search(con, query)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Courses")
        if results["courses"].empty:
            st.write("No matching courses.")
        else:
            for _, row in results["courses"].iterrows():
                label = f"{row['course_key']} — {row['course_title'] or ''}"
                if st.button(label, key=f"course_{row['course_key']}", use_container_width=True, type="primary"):
                    st.session_state["selected_course_key"] = row["course_key"]
                    st.switch_page("pages/1_Course.py")

    with col2:
        st.subheader("Professors")
        if results["professors"].empty:
            st.write("No matching professors.")
        else:
            for _, row in results["professors"].iterrows():
                dept = f" ({row['department']})" if row["department"] else ""
                label = f"{row['first_name']} {row['last_name']}{dept}"
                if st.button(label, key=f"prof_{row['prof_id']}", use_container_width=True, type="primary"):
                    st.session_state["selected_prof_id"] = row["prof_id"]
                    st.switch_page("pages/2_Professor.py")
else:
    st.info("Type above to search, or browse the full lists below.")
    with st.expander("All courses"):
        st.dataframe(data.list_all_courses(con), use_container_width=True, hide_index=True)
    with st.expander("All professors"):
        st.dataframe(data.list_all_professors(con), use_container_width=True, hide_index=True)

st.divider()
link_cols = st.columns(2)
link_cols[0].page_link("pages/4_Schedule.py", label="Build your schedule")
link_cols[1].page_link("pages/3_About.py", label="About this data")
