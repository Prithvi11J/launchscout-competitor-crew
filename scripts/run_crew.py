"""Run the crew built so far (Stage 2: Market Researcher -> Review Analyst).

    .venv\\Scripts\\python scripts/run_crew.py                      # demo brief (Chennai)
    .venv\\Scripts\\python scripts/run_crew.py --city Coimbatore --label cbe

Saves outputs/crew_<time>.json with each task's checked output, problems and costs.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from crewai import Crew  # noqa: E402
from crewai.tasks.task_output import TaskOutput  # noqa: E402

from launchscout.brief import DEMO_BRIEF, BusinessBrief  # noqa: E402
from launchscout.schemas import MarketResearch  # noqa: E402
from launchscout.crew import build_crew  # noqa: E402
from launchscout.evidence import evidence_to_json  # noqa: E402
from launchscout.tools import budget_used  # noqa: E402


def reuse_saved_research(crew: Crew, path: Path) -> Crew:
    """Give the research task a saved, checked answer and run only the later tasks.

    CrewAI reads a context task's `.output`; a context task outside the crew is allowed.
    """
    saved = json.loads(path.read_text(encoding="utf-8"))
    research = MarketResearch.model_validate(saved["research"])
    research_task, *later = crew.tasks
    research_guard = research_task.guardrail.__self__
    research_guard.brief = BusinessBrief.model_validate(saved["brief"])
    research_guard.last_research = research
    research_task.output = TaskOutput(
        description=research_task.description, raw=research.model_dump_json(), pydantic=research, agent="Market Researcher"
    )
    return Crew(agents=crew.agents[1:], tasks=later, process=crew.process, verbose=True, tracing=False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--idea", default=DEMO_BRIEF.idea)
    p.add_argument("--city", default=DEMO_BRIEF.city)
    p.add_argument("--customer", default=DEMO_BRIEF.target_customer)
    p.add_argument("--label", default="")
    p.add_argument("--research-from", help="Saved research_*.json: skip the researcher and review its answer (saves credits)")
    a = p.parse_args()

    crew = build_crew(BusinessBrief(idea=a.idea, city=a.city, target_customer=a.customer), with_reviews=True)
    if a.research_from:
        crew = reuse_saved_research(crew, Path(a.research_from))
    brief = crew.tasks[-1].guardrail.__self__.research_guard.brief
    started = time.perf_counter()
    record = {"brief": brief.model_dump(), "started_at": datetime.now().isoformat(timespec="seconds")}
    try:
        result = crew.kickoff(inputs=brief.to_inputs())
        record["status"] = "ok"
        record["token_usage"] = result.token_usage.model_dump()
    except Exception as err:  # a guardrail gave up: save what we have
        record.update(status="needs_review", error=f"{type(err).__name__}: {str(err)[:400]}")
    record["seconds"] = round(time.perf_counter() - started, 1)

    review_guard = crew.tasks[-1].guardrail.__self__
    research_guard = review_guard.research_guard
    record["research"] = research_guard.last_research.model_dump() if research_guard.last_research else None
    record["reviews"] = review_guard.last_reviews.model_dump() if review_guard.last_reviews else None
    record["attempts"] = {"research": research_guard.attempts, "reviews": review_guard.attempts}
    record["tool_calls"] = {
        agent.role: budget_used(agent.tools[0].budget_id) for agent in crew.agents
    }

    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    tag = f"_{a.label}" if a.label else ""
    path = out / f"crew_{datetime.now():%Y%m%d_%H%M%S}{tag}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    path.with_name(path.stem + "_review_evidence.json").write_text(
        json.dumps(evidence_to_json(review_guard.evidence), ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nStatus: {record['status']} ({record['seconds']} s)  tools: {record['tool_calls']}")
    for stage, attempts in record["attempts"].items():
        print(f"{stage}: " + ", ".join(a["stopped_by"] or "passed" for a in attempts))
    for c in (record["reviews"] or {}).get("competitors", []):
        rating = f"{c['rating']} ({c['rating_count']})" if c["rating"] else "-"
        print(f"\n{c['competitor']}  rating {rating}")
        for kind in ("likes", "complaints"):
            for point in c[kind]:
                print(f"  {'+' if kind == 'likes' else '-'} {point['point']}  \"{point['quote']}\"  <{point['source_url'][:60]}>")
    print(f"\nSaved {path.relative_to(ROOT)}")
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
