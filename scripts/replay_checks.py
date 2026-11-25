"""Re-run every code check on a saved run, for free (no API calls, no Serper credits).

Each run of run_research.py saves the agent's answer and the raw evidence it
saw. After changing a check, replay old runs to see what the new rule would
have said, before paying for a new run.

    .venv\\Scripts\\python scripts/replay_checks.py                 # the newest run
    .venv\\Scripts\\python scripts/replay_checks.py outputs/research_..._chennai.json
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from launchscout.checks import duplicate_problems, find_problems  # noqa: E402
from launchscout.evidence import evidence_from_json, repair_claims  # noqa: E402
from launchscout.schemas import MarketResearch  # noqa: E402


def main() -> int:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        runs = [p for p in (ROOT / "outputs").glob("research_*.json") if not p.stem.endswith("_evidence")]
        path = max(runs, key=lambda p: p.stat().st_mtime)
    evidence_path = path.with_name(path.stem + "_evidence.json")
    record = json.loads(path.read_text(encoding="utf-8"))
    if "research" not in record or not evidence_path.exists():
        print(f"{path.name}: no saved answer or evidence to replay")
        return 1

    research = MarketResearch.model_validate(record["research"])
    evidence = evidence_from_json(json.loads(evidence_path.read_text(encoding="utf-8")))
    repaired, repairs = repair_claims(research, evidence)
    problems = find_problems(repaired) + duplicate_problems(repaired)
    print(f"{path.name}: {len(research.competitors)} competitors in, {len(repaired.competitors)} after repair, "
          f"{len(evidence)} evidence units")
    print("Repairs:" if repairs else "Repairs: none")
    for r in repairs:
        print(f"  ~ {r}")
    print("Problems left:" if problems else "All rules pass after repair.")
    for p in problems:
        print(f"  - {p}")
    for c in repaired.competitors:
        prices = ", ".join(f"Rs {p.amount_inr} {p.unit}" for p in c.prices) or c.price_status
        print(f"  {c.name}: {prices}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
