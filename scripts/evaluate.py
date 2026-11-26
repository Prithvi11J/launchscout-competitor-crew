"""Evaluate the checks: plant known errors into real runs and count how many are caught.

Free and offline (no API calls). Uses saved real runs in eval/fixtures/:
  1. Planted errors: copy a real, already-checked answer, inject one mistake of a known
     type, run the checks, and see whether that exact mistake is removed or flagged.
     The answer key is known by construction, like the planted patterns in ReviewLens.
  2. Controls: the real answers themselves must still pass (no false alarms).
  3. Hand-labelled real claims: 9 claims I judged by hand while building (labels.json).

    .venv\\Scripts\\python scripts/evaluate.py      # writes eval/results.md and eval/results.json
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from launchscout.brief import BusinessBrief  # noqa: E402
from launchscout.checks import duplicate_problems, find_problems  # noqa: E402
from launchscout.evidence import (  # noqa: E402
    GENERIC_WORDS, evidence_from_json, names_business, normalize_text, normalize_url, price_grounded, repair_claims,
)
from launchscout.report import plan_problems  # noqa: E402
from launchscout.review_checks import repair_reviews  # noqa: E402
from launchscout.schemas import LaunchPlan, MarketResearch, PricePoint, ReviewPoint, ReviewResearch, StrategyAnalysis  # noqa: E402
from launchscout.strategy_checks import strategy_problems  # noqa: E402

FIX = ROOT / "eval" / "fixtures"
RUNS = ["082905_coimbatore", "082957_chennai", "084733_chennai", "095410_measure3", "101033_budget24_3", "234843_remeasure_1"]
UNSEEN, REDIRECT, INVENTED = "https://unseen-example.com/fees", "https://www.google.com/goto?url=CAESabc", 7777

tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # check type -> [caught, planted]
misses: list[str] = []
RUN = {"name": ""}


def score(kind: str, caught: bool, detail: str = "") -> None:
    tally[kind][0] += int(caught)
    tally[kind][1] += 1
    if not caught:
        misses.append(f"{kind} ({RUN['name']}): {detail}")


def load(name: str):
    record = json.loads((FIX / f"research_20261125_{name}.json").read_text(encoding="utf-8"))
    evidence = evidence_from_json(json.loads((FIX / f"research_20261125_{name}_evidence.json").read_text(encoding="utf-8")))
    return record, evidence


def distinctive(name: str) -> list[str]:
    return [w for w in normalize_text(name).split() if w not in GENERIC_WORDS and len(w) >= 4]


def still_has_price(research: MarketResearch, name: str, amount: int) -> bool:
    return any(p.amount_inr == amount for c in research.competitors if c.name == name for p in c.prices)


def still_has_source(research: MarketResearch, name: str, url: str) -> bool:
    return any(url in c.source_urls for c in research.competitors if c.name == name)


def research_plants(name: str) -> None:
    record, evidence = load(name)
    RUN["name"] = name
    city = record["brief"]["city"]
    original = MarketResearch.model_validate(record["research"])
    base, _ = repair_claims(original, evidence, city=city)
    # Control: real competitors (kept by every other check) must not be dropped by the city check.
    without_city, _ = repair_claims(original, evidence)
    for c in without_city.competitors:
        score("control: real competitor kept by the city check", c.name in {k.name for k in base.competitors}, c.name)

    for i, b in enumerate(base.competitors):
        def planted(mutate):
            copy = base.model_copy(deep=True)
            mutate(copy.competitors[i])
            return repair_claims(copy, evidence, city=city)[0]

        cite = b.source_urls[0]
        own = {p.amount_inr for p in b.prices}
        donors = [p.amount_inr for a in base.competitors if a.name != b.name for p in a.prices if p.amount_inr not in own]
        if donors:
            amount = donors[0]
            fixed = planted(lambda c: c.prices.append(PricePoint(label="copied", amount_inr=amount, unit="per month", source_url=cite)))
            score("price copied from another competitor", not still_has_price(fixed, b.name, amount), f"Rs {amount} onto {b.name}")

        fixed = planted(lambda c: c.prices.append(PricePoint(label="invented", amount_inr=INVENTED, unit="per month", source_url=cite)))
        score("invented price on a real page", not still_has_price(fixed, b.name, INVENTED))

        fixed = planted(lambda c: c.source_urls.append(UNSEEN))
        score("source link never seen", not still_has_source(fixed, b.name, UNSEEN))

        fixed = planted(lambda c: c.source_urls.append(REDIRECT))
        score("search-engine redirect as source", not still_has_source(fixed, b.name, REDIRECT))

        words = distinctive(b.name)
        padding = next((e.raw_url for e in evidence if e.raw_url and e.raw_url not in b.source_urls and "google." not in e.url
                        and words and not any(w in e2.text for e2 in evidence if e2.url == e.url for w in words)), None)
        if padding:
            fixed = planted(lambda c: c.source_urls.append(padding))
            score("padded source that never names the business", not still_has_source(fixed, b.name, padding))

    for note in base.market_price_context:
        amounts = [int(n.replace(",", "")) for n in __import__("re").findall(r"\d[\d,]{2,}", note.summary)]
        target = base.competitors[0]
        if amounts and not still_has_price(base, target.name, amounts[0]):
            copy = base.model_copy(deep=True)
            copy.competitors[0].prices.append(PricePoint(label="city range", amount_inr=amounts[0], unit="per month",
                                                        source_url=note.source_url))
            score("city-wide price range given as a competitor's price",
                  not still_has_price(repair_claims(copy, evidence, city=city)[0], target.name, amounts[0]),
                  f"Rs {amounts[0]} onto {target.name} from {note.source_url}")
            break

    wrong_city, _ = repair_claims(base, evidence, city="Madurai")
    for c in base.competitors:
        score("competitor placed in the wrong city", c.name not in {w.name for w in wrong_city.competitors})

    listing = base.model_copy(deep=True)
    listing.competitors.append(listing.competitors[0].model_copy(update={"name": "Justdial"}))
    score("listing site named as a competitor", any("listing site" in p for p in find_problems(listing)))

    dup = base.model_copy(deep=True)
    dup.competitors.append(dup.competitors[0].model_copy(update={"name": dup.competitors[0].name + " Studio"}))
    score("same business listed twice", bool(duplicate_problems(dup)))


def review_plants() -> None:
    record = json.loads((FIX / "reviews_run.json").read_text(encoding="utf-8"))
    evidence = evidence_from_json(json.loads((FIX / "reviews_run_evidence.json").read_text(encoding="utf-8")))
    _, research_evidence = load("234843_remeasure_1")  # the research this review run was built on
    names = [c["name"] for c in record["research"]["competitors"]]
    base, _ = repair_reviews(ReviewResearch.model_validate(record["reviews"]), evidence, names)
    real = sum(len(c.likes) + len(c.complaints) for c in base.competitors)
    kept, _ = repair_reviews(base, evidence, names)
    score("control: real review quotes kept", sum(len(c.likes) + len(c.complaints) for c in kept.competitors) == real)

    reviewed = [c for c in base.competitors if c.rating is not None]
    for i, target in enumerate(base.competitors):
        link = target.rating_source_url or (reviewed[0].rating_source_url if reviewed else "https://maps.google.com/?cid=1")

        def check(point: ReviewPoint, as_like: bool = False) -> bool:
            copy = base.model_copy(deep=True)
            (copy.competitors[i].likes if as_like else copy.competitors[i].complaints).append(point)
            fixed, _ = repair_reviews(copy, evidence, names)
            return all(normalize_text(p.quote) != normalize_text(point.quote)
                       for c in fixed.competitors for p in c.likes + c.complaints)

        other = next((e for e in evidence if e.kind == "review" and normalize_text(e.subject) != normalize_text(target.competitor)), None)
        if other:
            quote = " ".join(other.text.split()[:8])
            score("another business's review attached", check(ReviewPoint(point="x", quote=quote, source_url=link)))
        score("invented customer quote", check(ReviewPoint(point="x", quote="the trainers never show up on time", source_url=link)))
        marketing = next((e for e in research_evidence if e.kind == "page" and names_business(e, target.competitor)), None)
        if marketing:
            quote = " ".join(marketing.text.split()[5:13])
            score("business's own marketing text as a review",
                  check(ReviewPoint(point="x", quote=quote, source_url=marketing.raw_url or link), as_like=True))
        if target.rating is not None:
            copy = base.model_copy(deep=True)
            copy.competitors[i].rating = round(target.rating + 0.4, 1)
            fixed, _ = repair_reviews(copy, evidence, names)
            score("wrong Google rating", fixed.competitors[i].rating is None)


def strategy_and_plan_plants() -> None:
    record = json.loads((FIX / "strategy_run.json").read_text(encoding="utf-8"))
    research = MarketResearch.model_validate(record["research"])
    reviews = ReviewResearch.model_validate(record["reviews"])
    brief = BusinessBrief.model_validate(record["brief"])
    base = StrategyAnalysis.model_validate(record["strategy"])
    score("control: real strategy passes", strategy_problems(base, research, reviews, brief) == [])
    cases = {
        "invented number in the strategy": {"market_gap": base.market_gap + " Competitors charge Rs 3,333 on average."},
        "unknown competitor cited as evidence": {"gap_evidence": base.gap_evidence + ["Imaginary Studio"]},
        "launch price far outside the market": {"recommended_price_inr": 99_999, "positioning": "Dance - Rs 99999 a month"},
        "positioning line without the price": {"positioning": "After-work dance for professionals"},
    }
    for kind, change in cases.items():
        score(kind, bool(strategy_problems(base.model_copy(update=change), research, reviews, brief)))

    record = json.loads((FIX / "plan_run.json").read_text(encoding="utf-8"))
    research, reviews = MarketResearch.model_validate(record["research"]), ReviewResearch.model_validate(record["reviews"])
    strategy, brief = StrategyAnalysis.model_validate(record["strategy"]), BusinessBrief.model_validate(record["brief"])
    plan = LaunchPlan.model_validate(record["plan"])
    score("control: real plan passes", plan_problems(plan, research, reviews, strategy, brief) == [])
    invented = plan.model_copy(update={"summary": plan.summary + " Offer a Rs 4,567 trial pass."})
    score("invented price in the launch plan", bool(plan_problems(invented, research, reviews, strategy, brief)))
    short = plan.model_copy(update={"weeks": plan.weeks[:3]})
    score("launch plan missing a week", bool(plan_problems(short, research, reviews, strategy, brief)))


def hand_labelled() -> list[dict]:
    rows = []
    for label in json.loads((ROOT / "eval" / "labels.json").read_text(encoding="utf-8")):
        _, evidence = load(label["run"])
        units = [u for u in evidence if u.url == normalize_url(label["url"])]
        if label["kind"] == "source":
            supported = any(names_business(u, label["business"]) for u in units)
        else:
            supported = any(price_grounded(u, label["business"], label["amount"]) for u in units)
        flagged = not supported
        rows.append({**label, "flagged": flagged, "correct": flagged == label["wrong"]})
    return rows


def main() -> int:
    for name in RUNS:
        research_plants(name)
    review_plants()
    strategy_and_plan_plants()
    labelled = hand_labelled()

    planted = {k: v for k, v in tally.items() if not k.startswith("control")}
    controls = {k: v for k, v in tally.items() if k.startswith("control")}
    caught, total = sum(v[0] for v in planted.values()), sum(v[1] for v in planted.values())
    lines = ["# LaunchScout evaluation", "",
             f"Planted errors caught: **{caught} of {total}** ({caught / total:.0%}), across {len(RUNS)} real research runs, "
             "one review run, one strategy and one plan. Free to re-run: `python scripts/evaluate.py`.", "",
             "| Planted error | Caught |", "|---|---|"]
    lines += [f"| {k} | {v[0]}/{v[1]} |" for k, v in sorted(planted.items(), key=lambda kv: kv[1][0] / kv[1][1])]
    lines += ["", "## Every miss", ""] + [f"- {m}" for m in misses]
    lines += ["", "## Controls (real answers must not be flagged)", "", "| Control | Passed |", "|---|---|"]
    lines += [f"| {k.removeprefix('control: ')} | {v[0]}/{v[1]} |" for k, v in controls.items()]
    right = sum(r["correct"] for r in labelled)
    lines += ["", f"## Hand-labelled real claims: {right} of {len(labelled)} judged correctly", "",
              "| Business | Claim | Truth | Checker | Note |", "|---|---|---|---|---|"]
    for r in labelled:
        claim = f"Rs {r['amount']:,}" if r["kind"] == "price" else "source link"
        lines.append(f"| {r['business']} | {claim} | {'wrong' if r['wrong'] else 'right'} | "
                     f"{'flagged' if r['flagged'] else 'kept'} {'✓' if r['correct'] else '✗'} | {r['note']} |")

    runs = json.loads((ROOT / "eval" / "runs.json").read_text(encoding="utf-8"))
    done = sum(r["outcome"].startswith("full report") for r in runs)
    lines += ["", f"## End-to-end runs: {done} of {len(runs)} produced a full report", "",
              "Real, paid runs of all four agents (logged by hand from the run outputs). A stopped run is the checks "
              "refusing to guess, not a crash; its partial findings are saved for review.", "",
              "| Idea | City | Outcome | Time | Note |", "|---|---|---|---|---|"]
    lines += [f"| {r['idea']} | {r['city']} | {r['outcome']} | {r['seconds']} s | {r['note']} |" for r in runs]

    out = ROOT / "eval"
    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps({"planted": planted, "controls": controls, "hand_labelled": labelled},
                                                 indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
