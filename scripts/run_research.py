"""Stage 1: run the Market Researcher on one business idea and check its work.

Run from the project root (defaults to the demo dance-class brief):
    .venv\\Scripts\\python scripts/run_research.py
    .venv\\Scripts\\python scripts/run_research.py --idea "Millet lunch boxes" --city Coimbatore --customer "Office workers"

Saves outputs/research_<time>.json. A run never crashes on a bad answer: if the
guardrail keeps failing, the run is saved with status "needs_review".
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles otherwise crash on the rupee sign

from launchscout.brief import DEMO_BRIEF, BusinessBrief  # noqa: E402
from launchscout.checks import duplicate_problems, find_problems  # noqa: E402
from launchscout.crew import build_crew  # noqa: E402
from launchscout.evidence import evidence_to_json, grounding_problems  # noqa: E402
from launchscout.tools import budget_used  # noqa: E402


def parse_args() -> tuple[BusinessBrief, str]:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--idea", default=DEMO_BRIEF.idea)
    p.add_argument("--city", default=DEMO_BRIEF.city)
    p.add_argument("--customer", default=DEMO_BRIEF.target_customer)
    p.add_argument("--known", default="", help="Comma-separated competitor names (optional)")
    p.add_argument("--label", default="", help="Short tag added to the output file name")
    a = p.parse_args()
    brief = BusinessBrief(idea=a.idea, city=a.city, target_customer=a.customer, known_competitors=a.known.split(","))
    return brief, a.label


def print_table(research) -> None:
    print("\nCompetitors found")
    for c in research.competitors:
        price = "; ".join(f"Rs {p.amount_inr:,} {p.unit} ({p.label})" for p in c.prices) or c.price_status
        print(f"- {c.name} [{c.locality}] | {price} | schedule: {c.schedule}")
        print(f"    fit: {c.fit_reason}")
    for note in research.market_price_context:
        print(f"  market: {note.summary}  <{note.source_url}>")


def main() -> int:
    brief, label = parse_args()
    crew = build_crew(brief)
    started = time.perf_counter()
    record = {"brief": brief.model_dump(), "started_at": datetime.now().isoformat(timespec="seconds")}

    try:
        result = crew.kickoff(inputs=brief.to_inputs())
    except Exception as err:  # guardrail gave up, API error, ... -> save, don't lose the run
        record.update(status="needs_review", error=f"{type(err).__name__}: {err}")
        result = None

    record["seconds"] = round(time.perf_counter() - started, 1)
    task = crew.tasks[0]
    record["guardrail_retries"] = task.retry_count
    guard = task.guardrail.__self__  # the ResearchGuardrail behind the bound method
    record["fit_verdicts"] = [v.model_dump() for v in guard.verdicts]
    record["guardrail_attempts"] = guard.attempts
    record["evidence_units"] = len(guard.evidence)

    if result is not None:
        research = result.pydantic
        record.update(
            status="ok",
            research=research.model_dump(),
            problems=find_problems(research) + duplicate_problems(research) + grounding_problems(research, guard.evidence),
            token_usage=result.token_usage.model_dump(),
        )
        print_table(research)
    elif guard.last_research is not None:
        # The checks gave up, but the last answer is still worth a human look: save it with its problems.
        research = guard.last_research
        record["research"] = research.model_dump()
        record["problems"] = find_problems(research) + duplicate_problems(research) + grounding_problems(research, guard.evidence)
        print("\nLast answer (needs review)")
        print_table(research)

    # Real counts for the whole run (all attempts), from our own budget, not CrewAI's per-copy counters.
    record["tool_calls"] = budget_used(crew.agents[0].tools[0].budget_id)

    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    tag = f"_{label}" if label else ""
    path = out_dir / f"research_{datetime.now():%Y%m%d_%H%M%S}{tag}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    # Raw evidence lets scripts/replay_checks.py re-run every code check later for free.
    evidence_path = path.with_name(path.stem + "_evidence.json")
    evidence_path.write_text(json.dumps(evidence_to_json(guard.evidence), ensure_ascii=False), encoding="utf-8")

    print(f"\nStatus          : {record['status']}  ({record['seconds']} s, guardrail retries: {record['guardrail_retries']})")
    print(f"Tool calls      : {record['tool_calls']}")
    for i, verdict in enumerate(record["fit_verdicts"], 1):
        rejected = [j["name"] for j in verdict["judgements"] if not j["direct_competitor"]]
        print(f"Fit check #{i}    : rejected {rejected or 'none'}")
    for i, attempt in enumerate(record["guardrail_attempts"], 1):
        print(f"Attempt {i}       : stopped by {attempt['stopped_by'] or 'nothing (passed)'}")
        for repair in attempt.get("repairs", []):
            print(f"   repaired     : {repair}")
    print(f"Evidence units  : {record['evidence_units']} search results and pages")
    if result is not None:
        usage = record["token_usage"]
        print(f"Tokens          : {usage.get('prompt_tokens')} in / {usage.get('completion_tokens')} out")
        print(f"Open problems   : {record['problems'] or 'none'}")
    else:
        print(f"Error           : {record['error'][:300]}")
        print(f"Open problems   : {record.get('problems') or 'no answer to review'}")
    print(f"Saved           : {path.relative_to(ROOT)}")
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
