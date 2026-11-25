"""Checks for the Strategy Analyst: its words may reason, but its numbers and names must be real.

* every competitor named as evidence for the gap is one we researched;
* every number in its text is a number from the data (a price, rating or count),
  its own recommended price, or a small number such as a time or a class count;
* the recommended price sits in a believable range of competitors' prices in the same unit.
"""

import json
import re
from typing import Any

from pydantic import ValidationError

from launchscout.evidence import normalize_text
from launchscout.matrix import build_matrix
from launchscout.progress import emit
from launchscout.schemas import StrategyAnalysis

SMALL_NUMBER = 31  # times (7 pm), days, class counts and percentages are fine without a source
PRICE_FLOOR, PRICE_CEILING = 0.5, 1.5  # recommended price vs the cheapest and dearest competitor, same unit


def parse_strategy(raw: str) -> StrategyAnalysis:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{") and "{" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    return StrategyAnalysis.model_validate(json.loads(text))


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def known_numbers(research, reviews) -> set[float]:
    known: set[float] = set()
    for c in research.competitors:
        known.update(float(p.amount_inr) for p in c.prices)
    for r in reviews.competitors if reviews else []:
        known.update(float(x) for x in (r.rating, r.rating_count) if x is not None)
    return known


def strategy_problems(s: StrategyAnalysis, research, reviews, brief=None) -> list[str]:
    problems = []
    names = {normalize_text(c.name): c.name for c in research.competitors}
    unknown = [n for n in s.gap_evidence if normalize_text(n) not in names]
    if unknown:
        problems.append(f"gap_evidence must name researched competitors exactly; unknown: {', '.join(unknown)}.")
    if not s.gap_evidence:
        problems.append("gap_evidence is empty: name the competitors whose data shows the gap.")

    allowed = known_numbers(research, reviews) | {float(s.recommended_price_inr)}
    if brief is not None:  # the founder's own numbers, e.g. "age 22 to 40"
        allowed |= set(_numbers(" ".join(brief.to_inputs().values())))
    text = f"{s.market_gap} {s.positioning} {s.price_reason}"
    invented = sorted({n for n in _numbers(text) if n > SMALL_NUMBER and n not in allowed})
    if invented:
        listed = ", ".join(f"{n:g}" for n in invented)
        problems.append(f"These numbers are not in the research or reviews: {listed}. Use only real prices, ratings and counts.")

    rows = build_matrix(research, reviews)
    same_unit = [r["price"]["amount_inr"] for r in rows if r["price"] and r["price"]["unit"] == s.price_unit]
    if same_unit:
        low, high = min(same_unit) * PRICE_FLOOR, max(same_unit) * PRICE_CEILING
        if not low <= s.recommended_price_inr <= high:
            problems.append(
                f"Recommended Rs {s.recommended_price_inr} {s.price_unit} is outside the believable range "
                f"Rs {low:,.0f} to Rs {high:,.0f} given competitors' {s.price_unit} prices {sorted(same_unit)}."
            )
    if str(s.recommended_price_inr) not in s.positioning.replace(",", ""):
        problems.append("The positioning line must include the recommended price.")
    return problems


class StrategyGuardrail:
    def __init__(self, research_guard, review_guard):
        self.research_guard = research_guard
        self.review_guard = review_guard
        self.attempts: list[dict] = []
        self.last_strategy: StrategyAnalysis | None = None

    def check(self, task_output: Any) -> tuple[bool, Any]:
        try:
            strategy = parse_strategy(task_output.raw)
        except (json.JSONDecodeError, ValueError, ValidationError) as err:
            feedback = f"Your answer must be one JSON object matching the StrategyAnalysis schema. Error: {err}"
            self.attempts.append({"stopped_by": "format", "feedback": feedback})
            return False, feedback
        self.last_strategy = strategy
        problems = strategy_problems(
            strategy, self.research_guard.last_research, self.review_guard.last_reviews, getattr(self.research_guard, "brief", None)
        )
        if problems:
            feedback = "Fix these problems and answer again:\n- " + "\n- ".join(problems)
            self.attempts.append({"stopped_by": "rules", "feedback": feedback})
            emit("Strategy Analyst", f"Sent back: {problems[0]}")
            return False, feedback
        self.attempts.append({"stopped_by": None, "feedback": "passed"})
        emit("Strategy Analyst", f"Gap found; launch price Rs {strategy.recommended_price_inr:,} {strategy.price_unit}")
        return True, strategy
