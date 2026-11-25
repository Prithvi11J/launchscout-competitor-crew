"""One call that runs the whole crew for a brief and returns everything the app shows.

The app runs this in a background thread and reads progress events from a queue,
so the page stays live while the agents work.
"""

import time

from launchscout import progress
from launchscout.brief import BusinessBrief
from launchscout.crew import build_crew
from launchscout.matrix import build_matrix

AGENTS = ["Market Researcher", "Review Analyst", "Strategy Analyst", "Report Writer"]


def run_crew(brief: BusinessBrief, sink=None) -> dict:
    progress.set_sink(sink)

    def task_done(output) -> None:
        progress.emit(output.agent, "__done__")

    crew = build_crew(brief, task_callback=task_done)
    guards = [t.guardrail.__self__ for t in crew.tasks]
    started = time.perf_counter()
    progress.emit(AGENTS[0], "__start__")
    try:
        crew.kickoff(inputs=brief.to_inputs())
        status, error = "ok", None
    except Exception as err:  # a check gave up after its retries: return what was found
        status, error = "needs_review", f"{type(err).__name__}: {str(err)[:300]}"
    finally:
        progress.set_sink(None)

    research, reviews = guards[0].last_research, guards[1].last_reviews
    return {
        "status": status,
        "error": error,
        "seconds": round(time.perf_counter() - started, 1),
        "report": guards[3].report,
        "partial": getattr(guards[0], "partial", False),
        "matrix": build_matrix(research, reviews) if research else None,
        "strategy": guards[2].last_strategy.model_dump() if guards[2].last_strategy else None,
    }
