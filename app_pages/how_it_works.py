"""How it works: the four agents and the checks between them."""

import streamlit as st

st.title("How it works")
st.caption("A crew of four AI agents, each with one job. Code checks every hand-off, so a guess never "
           "reaches the report.")

AGENTS = [
    (":material/travel_explore:", "Market Researcher",
     "Searches the web, then reads each business's own website for prices, timings and address.",
     "Every price must sit next to the business's name on the page it cites. Listing sites and "
     "freelancers don't count as competitors, and each business must be placed in your city."),
    (":material/reviews:", "Review Analyst",
     "Reads each competitor's Google reviews, including the lowest-rated ones.",
     "Every like and complaint must quote a real customer review word for word. A business's own "
     "posts are marketing, not reviews."),
    (":material/lightbulb:", "Strategy Analyst",
     "Compares prices, timings and complaints to find one gap, then suggests a positioning and price.",
     "Every number it mentions must come from the research. The price must sit in a believable range."),
    (":material/edit_note:", "Report Writer",
     "Writes the summary and a week-by-week 30-day launch plan.",
     "Tables, quotes and sources are assembled in code, so no number can be retyped wrongly."),
]

for icon, name, job, check in AGENTS:
    with st.container(border=True):
        st.markdown(f"### {icon} {name}")
        st.write(job)
        st.caption(f"**Checked in code:** {check}")

st.subheader("When a check fails")
st.write("Code first repairs what it can: it moves a price to the page that really shows it, and drops claims "
         "no page supports. If too little is left, the agent is sent back with the exact problem and a list of "
         "businesses already checked, so it spends its searches on new ones. If a market is simply thin "
         "(fewer than 3 businesses publish prices), the report says so instead of guessing.")
