"""Research page: the founder describes the idea, watches the agents work, gets the report."""

import streamlit as st

from launchscout.brief import DEMO_BRIEF, BusinessBrief
from ui import state
from ui.report_view import show_report

st.markdown("# Launch:orange[Scout]")
st.markdown("#### Know your market before you sign the lease.")
st.caption("Four AI agents find your local competitors, their real prices and Google reviews, spot the gap, "
           "and write a 30-day launch plan. Every number links to the page it came from.")

with st.form("brief", border=True):
    idea = st.text_input("What do you want to launch?", DEMO_BRIEF.idea)
    c1, c2 = st.columns(2)
    city = c1.text_input("City", DEMO_BRIEF.city)
    customer = c2.text_input("Who is it for?", DEMO_BRIEF.target_customer)
    known = st.text_input("Competitors you already know (optional, comma-separated)")
    ready = state.keys_ready()
    submitted = st.form_submit_button("Research my market", type="primary", icon=":material/travel_explore:",
                                      disabled=not ready)

if not ready:
    st.info("This live demo has no API keys, so new research is switched off. "
            "Open **Example reports** to see a complete run, with every source.", icon=":material/info:")
else:
    st.caption("A run takes 1 to 3 minutes and uses up to about 60 web searches.")

running = state.job_running()
if submitted and running:
    st.warning("A run is already in progress; showing it below.")
if submitted and not running:
    state.start_job(BusinessBrief(idea=idea, city=city, target_customer=customer, known_competitors=known.split(",")))
    running = True
if running:
    st.session_state["result"] = state.follow_job(state.current_job())
    st.session_state["result_brief"] = state.current_job()["brief"]

result = st.session_state.get("result")
if result:
    brief = st.session_state["result_brief"]
    if result["report"]:
        stats = result.get("stats", {})
        st.success(f"Done in {result['seconds']:.0f} seconds · {stats.get('searches', 0)} searches · "
                   f"{stats.get('review_lookups', 0)} Google review lookups", icon=":material/check_circle:")
        show_report(result["report"], result.get("trail", []), f"launchscout_{brief.city.lower()}", key="live")
    else:
        st.warning("The agents could not confirm enough evidence for a full report, so their checks stopped "
                   "the run instead of guessing. What they did confirm:", icon=":material/report:")
        if result.get("matrix"):
            st.dataframe([{k: row[k] for k in ("name", "locality", "price_status", "rating")} for row in result["matrix"]],
                         hide_index=True)
else:
    examples = state.examples()
    if examples:
        title, demo = next(iter(examples.items()))
        st.subheader("Example report")
        st.caption(f"{title} · a real run, {demo['seconds']:.0f} seconds")
        show_report(demo["report"], demo["trail"], "launchscout_example", key="home")
