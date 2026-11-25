"""Shared app state: example reports and the background research job.

The job lives in session_state, so a page rerun (a second click, a refresh, switching
pages) re-attaches to the running crew instead of starting a second paid run.
"""

import json
import queue
import threading
from pathlib import Path

import streamlit as st

from launchscout.brief import BusinessBrief
from launchscout.config import ConfigError, get_api_key, get_serper_key

DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"
AGENTS = ["Market Researcher", "Review Analyst", "Strategy Analyst", "Report Writer"]
JOBS = {
    "Market Researcher": "finding competitors and their prices",
    "Review Analyst": "reading Google reviews",
    "Strategy Analyst": "finding the market gap and a launch price",
    "Report Writer": "writing the report and 30-day plan",
}


@st.cache_data
def examples() -> dict[str, dict]:
    """Saved example runs (demo/*.json), keyed by a readable title."""
    found = {}
    for path in sorted(DEMO_DIR.glob("*.json")):
        demo = json.loads(path.read_text(encoding="utf-8"))
        brief = demo["brief"]
        found[f"{brief['idea']} · {brief['city']}"] = demo
    return found


def keys_ready() -> bool:
    try:
        get_api_key()
    except ConfigError:
        return False
    return bool(get_serper_key())


def current_job() -> dict | None:
    return st.session_state.get("job")


def job_running() -> bool:
    job = current_job()
    return job is not None and job["thread"].is_alive()


def start_job(brief: BusinessBrief) -> dict:
    from launchscout.pipeline import run_crew  # imports CrewAI: only when a run starts

    job = {"brief": brief, "queue": queue.Queue(), "events": [], "holder": {}}
    job["thread"] = threading.Thread(
        target=lambda: job["holder"].update(result=run_crew(brief, sink=job["queue"].put)), daemon=True
    )
    job["thread"].start()
    st.session_state["job"] = job
    return job


def follow_job(job: dict) -> dict:
    """One status box per agent: replay events seen so far, then follow new ones live."""
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
