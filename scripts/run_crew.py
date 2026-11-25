"""Run the full crew: Market Researcher -> Review Analyst -> Strategy Analyst -> Report Writer.

    .venv\\Scripts\\python scripts/run_crew.py                         # full run, demo brief (Chennai)
    .venv\\Scripts\\python scripts/run_crew.py --from outputs/crew_x.json   # reuse saved stages (saves credits)

--from accepts a research_*.json (reuses research) or a crew_*.json (reuses research and
reviews), so a later stage can be tested without paying for the earlier ones again.
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
from launchscout.crew import build_crew  # noqa: E402
from launchscout.matrix import build_matrix, matrix_markdown  # noqa: E402
from launchscout.schemas import MarketResearch, ReviewResearch, StrategyAnalysis  # noqa: E402
from launchscout.tasks import REPORT_FILE  # noqa: E402
from launchscout.tools import budget_used  # noqa: E402
from launchscout.trail import build_trail  # noqa: E402

STAGES = 4


def guards(crew_tasks):
    return [t.guardrail.__self__ for t in crew_tasks]


def reuse_saved(full: Crew, path: Path) -> Crew:
    """Give finished tasks their saved, checked answers and run only the rest.

    CrewAI reads a context task's `.output`; a context task outside the crew is allowed.
    """
    saved = json.loads(path.read_text(encoding="utf-8"))
    research_guard, review_guard, strategy_guard, _ = guards(full.tasks)
    research_guard.brief = BusinessBrief.model_validate(saved["brief"])
    research_guard.last_research = MarketResearch.model_validate(saved["research"])
    full.tasks[0].output = TaskOutput(description="research", raw=research_guard.last_research.model_dump_json(), agent="Market Researcher")
    done = 1
    if saved.get("reviews"):
        review_guard.last_reviews = ReviewResearch.model_validate(saved["reviews"])
        full.tasks[1].output = TaskOutput(description="reviews", raw=review_guard.last_reviews.model_dump_json(), agent="Review Analyst")
        done = 2
    if saved.get("reviews") and saved.get("strategy"):
        strategy_guard.last_strategy = StrategyAnalysis.model_validate(saved["strategy"])
        full.tasks[2].output = TaskOutput(description="strategy", raw=strategy_guard.last_strategy.model_dump_json(), agent="Strategy Analyst")
        done = 3
    return Crew(agents=full.agents[done:], tasks=full.tasks[done:], process=full.process, verbose=True, tracing=False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--idea", default=DEMO_BRIEF.idea)
    p.add_argument("--city", default=DEMO_BRIEF.city)
    p.add_argument("--customer", default=DEMO_BRIEF.target_customer)
    p.add_argument("--label", default="")
    p.add_argument("--from", dest="from_file", help="Saved research_*.json or crew_*.json to reuse")
    p.add_argument("--save-demo", help="Also save the report and evidence trail as demo/<name>.json for the app")
    a = p.parse_args()

    full = build_crew(BusinessBrief(idea=a.idea, city=a.city, target_customer=a.customer), stages=STAGES)
    research_guard, review_guard, strategy_guard, report_guard = guards(full.tasks)
    crew = reuse_saved(full, Path(a.from_file)) if a.from_file else full
    brief = research_guard.brief

    started = time.perf_counter()
    record = {"brief": brief.model_dump(), "started_at": datetime.now().isoformat(timespec="seconds")}
    try:
        result = crew.kickoff(inputs=brief.to_inputs())
        record["status"] = "ok"
        record["token_usage"] = result.token_usage.model_dump()
    except Exception as err:  # a guardrail gave up: save what we have
        record.update(status="needs_review", error=f"{type(err).__name__}: {str(err)[:400]}")
    record["seconds"] = round(time.perf_counter() - started, 1)

    research, reviews, strategy = research_guard.last_research, review_guard.last_reviews, strategy_guard.last_strategy
    record["research"] = research.model_dump() if research else None
    record["reviews"] = reviews.model_dump() if reviews else None
    record["strategy"] = strategy.model_dump() if strategy else None
    record["matrix"] = build_matrix(research, reviews) if research else None
    record["partial"] = research_guard.partial
    record["trail"] = build_trail(research, reviews, research_guard.evidence, review_guard.evidence) if research else []
    record["plan"] = report_guard.last_plan.model_dump() if report_guard.last_plan else None
    record["report_file"] = REPORT_FILE if report_guard.report else None
    record["attempts"] = {"research": research_guard.attempts, "reviews": review_guard.attempts,
                          "strategy": strategy_guard.attempts, "report": report_guard.attempts}
    record["tool_calls"] = {ag.role: budget_used(ag.tools[0].budget_id) for ag in crew.agents if ag.tools}

    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    path = out / f"crew_{datetime.now():%Y%m%d_%H%M%S}{'_' + a.label if a.label else ''}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nStatus: {record['status']} ({record['seconds']} s)  tools: {record['tool_calls']}")
    for stage, attempts in record["attempts"].items():
        if attempts:
            print(f"{stage}: " + ", ".join(x["stopped_by"] or "passed" for x in attempts))
    if record["matrix"]:
        print("\n" + matrix_markdown(record["matrix"]))
    if strategy:
        print(f"\nGap: {strategy.market_gap}\nEvidence: {', '.join(strategy.gap_evidence)}")
        print(f"Positioning: {strategy.positioning}\nPrice: Rs {strategy.recommended_price_inr} {strategy.price_unit} - {strategy.price_reason}")
    if record["report_file"]:
        print(f"\nReport saved to {REPORT_FILE}")
    if a.save_demo and report_guard.report:
        demo = {"brief": record["brief"], "report": report_guard.report, "trail": record["trail"],
                "partial": record["partial"], "seconds": record["seconds"], "tool_calls": record["tool_calls"]}
        demo_path = ROOT / "demo" / f"{a.save_demo}.json"
        demo_path.write_text(json.dumps(demo, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Example saved to {demo_path.relative_to(ROOT)}")
    if record["status"] != "ok":
        print(f"\n{record['error']}")
    print(f"\nSaved {path.relative_to(ROOT)}")
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
