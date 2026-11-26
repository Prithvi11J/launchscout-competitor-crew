"""Example reports: complete saved runs, each with its evidence trail."""

import streamlit as st

from ui import state
from ui.report_view import show_report

st.title("Example reports")
st.caption("A real run of the crew, saved as it came out: nothing was edited by hand.")

examples = state.examples()
if not examples:
    st.info("No example reports saved yet.")
    st.stop()

title = st.segmented_control("Example", list(examples), default=list(examples)[0], label_visibility="collapsed")
demo = examples[title or list(examples)[0]]
brief = demo["brief"]
c1, c2, c3 = st.columns(3)
c1.metric("City", brief["city"])
c2.metric("Run time", f"{demo['seconds']:.0f} s")
c3.metric("Claims with evidence", len(demo["trail"]))
st.caption(f"For: {brief['target_customer']}")
show_report(demo["report"], demo["trail"], f"launchscout_{brief['city'].lower()}", key="examples")
