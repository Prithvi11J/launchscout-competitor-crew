"""LaunchScout web app: describe a business idea, watch four agents research it, get the report.

    .venv\\Scripts\\streamlit run app.py

The crew runs in a background thread; tools and checks send progress events to a
queue, and this page reads the queue every half second to show which agent is
working and what it just found.
"""

import queue
import threading
from pathlib import Path

import streamlit as st

from launchscout.brief import DEMO_BRIEF, BusinessBrief
from launchscout.config import ConfigError, get_api_key, get_serper_key
from launchscout.pdf import report_pdf

ROOT = Path(__file__).parent
DEMO_REPORT = ROOT / "demo" / "report_chennai_dance.md"
AGENTS = ["Market Researcher", "Review Analyst", "Strategy Analyst", "Report Writer"]
JOBS = {
    "Market Researcher": "finding competitors and their prices",
    "Review Analyst": "reading Google reviews",
    "Strategy Analyst": "finding the market gap and a launch price",
    "Report Writer": "writing the report and 30-day plan",
}

st.set_page_config(page_title="LaunchScout", page_icon="🔭", layout="wide")


def keys_ready() -> bool:
    try:
        get_api_key()
    except ConfigError:
        return False
    return bool(get_serper_key())


def start_job(brief: BusinessBrief) -> dict:
    """Start the crew in a background thread. The job lives in session_state, so a page rerun
    (a second click, a refresh) re-attaches to it instead of starting a second paid run."""
    from launchscout.pipeline import run_crew

    job = {"brief": brief, "queue": queue.Queue(), "events": [], "holder": {}}
    job["thread"] = threading.Thread(
        target=lambda: job["holder"].update(result=run_crew(brief, sink=job["queue"].put)), daemon=True
    )
    job["thread"].start()
    st.session_state["job"] = job
    return job


def follow_job(job: dict) -> dict:
    """Draw one status box per agent: replay events seen so far, then follow new ones live."""
    boxes = {name: st.status(f"{name}: waiting", state="complete", expanded=False) for name in AGENTS}
    current = None

    def show(event):
        nonlocal current
        role, message = event["role"], event["message"]
        if message == "__done__":
            boxes[role].update(label=f"{role}: done", state="complete", expanded=False)
            nxt = AGENTS.index(role) + 1
            role, message = (AGENTS[nxt], "__start__") if nxt < len(AGENTS) else (None, None)
        if role in boxes and role != current:
            current = role
            boxes[role].update(label=f"{role}: {JOBS[role]}...", state="running", expanded=True)
        if message and not message.startswith("__"):
            boxes[role].write(message)

    for event in job["events"]:
        show(event)
    while job["thread"].is_alive() or not job["queue"].empty():
        try:
            event = job["queue"].get(timeout=0.5)
        except queue.Empty:
            continue
        job["events"].append(event)
        show(event)

    result = job["holder"].get("result", {"status": "needs_review", "error": "The run stopped unexpectedly.", "report": None})
    if result["status"] != "ok" and current:
        boxes[current].update(label=f"{current}: stopped", state="error", expanded=True)
    return result


def show_report(report_md: str, file_stem: str) -> None:
    left, right, _ = st.columns([1, 1, 4])
    left.download_button("Download Markdown", report_md, f"{file_stem}.md", "text/markdown")
    right.download_button("Download PDF", report_pdf(report_md), f"{file_stem}.pdf", "application/pdf")
    st.markdown(report_md)


st.title("LaunchScout")
st.caption("Four AI agents research your competitors, their prices and reviews, and write a launch plan. "
           "Every price and quote links to its source.")

with st.form("brief"):
    idea = st.text_input("Business idea", DEMO_BRIEF.idea)
    c1, c2 = st.columns(2)
    city = c1.text_input("City", DEMO_BRIEF.city)
    customer = c2.text_input("Target customer", DEMO_BRIEF.target_customer)
    known = st.text_input("Known competitors (optional, comma-separated)")
    ready = keys_ready()
    submitted = st.form_submit_button("Research my market", type="primary", disabled=not ready)
if not ready:
    st.info("Live research needs an OpenAI key and a Serper key on the server. Below is an example report.")
else:
    st.caption("A run takes about 2 to 4 minutes and uses up to about 60 Serper searches.")

job = st.session_state.get("job")
running = job is not None and job["thread"].is_alive()
if submitted and running:
    st.warning("A run is already in progress; showing it below.")
if submitted and not running:
    job = start_job(BusinessBrief(idea=idea, city=city, target_customer=customer, known_competitors=known.split(",")))
    running = True
if running:
    st.session_state["result"] = follow_job(job)
    st.session_state["result_brief"] = job["brief"]

result = st.session_state.get("result")
if result:
    brief = st.session_state["result_brief"]
    if result["report"]:
        st.success(f"Done in {result['seconds']:.0f} seconds.")
        show_report(result["report"], f"launchscout_{brief.city.lower()}")
    else:
        st.warning("The agents could not confirm enough evidence to write a full report. "
                   "Their checks stopped the run instead of guessing. What they did confirm:")
        if result.get("matrix"):
            st.dataframe([{k: v for k, v in row.items() if k in ("name", "locality", "price_status", "rating")}
                          for row in result["matrix"]])
        st.caption(result.get("error") or "")
else:
    st.subheader("Example report: dance classes for working adults, Chennai")
    show_report(DEMO_REPORT.read_text(encoding="utf-8"), "launchscout_example_chennai")
