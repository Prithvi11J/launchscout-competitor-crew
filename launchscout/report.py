"""The founder's report, assembled in code from every checked stage.

The Report Writer writes only the words a founder needs (a summary and a 30-day
plan). Tables, prices, ratings, quotes and the numbered source list come straight
from the checked data, so the report cannot retype a number or a link wrongly.
"""

import json
import re
from typing import Any

from pydantic import ValidationError

from launchscout.matrix import build_matrix
from launchscout.schemas import LaunchPlan
from launchscout.strategy_checks import _numbers, known_numbers

# A plan has targets ("collect 50 reviews") but no new prices: numbers above this must come from the data.
PLAN_TARGET_LIMIT = 100

SECTIONS = ["Key Competitors", "What Customers Complain About", "Market Gap", "Recommended Positioning",
            "30-Day Launch Plan", "Sources"]


class Sources:
    """Numbers each URL once, in order of first use: [1], [2], ..."""

    def __init__(self):
        self.urls: list[str] = []

    def ref(self, url: str | None) -> str:
        if not url:
            return ""
        if url not in self.urls:
            self.urls.append(url)
        return f"[{self.urls.index(url) + 1}]"


def assemble_report(brief, research, reviews, strategy, plan: LaunchPlan) -> str:
    src = Sources()
    rows = build_matrix(research, reviews)
    review_by_name = {r.competitor: r for r in (reviews.competitors if reviews else [])}
    out = [f"# Competitor Report: {brief.idea}, {brief.city}", "",
           f"**Target customer:** {brief.target_customer}", "", plan.summary, ""]

    out += [f"## 1. {SECTIONS[0]}", "",
            "| Competitor | Area | Price | Schedule | Google rating | Channels |", "|---|---|---|---|---|---|"]
    for row in rows:
        p = row["price"]
        price = f"Rs {p['amount_inr']:,} {p['unit']} {src.ref(p['source_url'])}" if p else row["price_status"].replace("_", " ")
        r = review_by_name.get(row["name"])
        rating = f"{row['rating']} ({row['rating_count']:,}) {src.ref(r.rating_source_url)}" if row["rating"] else "-"
        out.append(f"| {row['name']} | {row['locality']} | {price} | {row['schedule'][:70]} | {rating} | {', '.join(row['channels']) or '-'} |")
    priced = sum(1 for row in rows if row["price"])
    out += ["", f"{priced} of {len(rows)} competitors publish a price; the rest share fees only on enquiry.", ""]

    out += [f"## 2. {SECTIONS[1]}", ""]
    any_complaint = False
    for name, r in review_by_name.items():
        for point in r.complaints:
            any_complaint = True
            out.append(f"- **{name}:** {point.point}. *\"{point.quote}\"* {src.ref(point.source_url)}")
    if not any_complaint:
        out.append("- No recent complaints were found in Google reviews.")
    out.append("")

    out += [f"## 3. {SECTIONS[2]}", "", strategy.market_gap, "", f"*Evidence: {', '.join(strategy.gap_evidence)}.*", ""]
    out += [f"## 4. {SECTIONS[3]}", "", f"> **{strategy.positioning}**", "",
            f"**Launch price:** Rs {strategy.recommended_price_inr:,} {strategy.price_unit}. {strategy.price_reason}", ""]

    out += [f"## 5. {SECTIONS[4]}", ""]
    for week in plan.weeks:
        out.append(f"**Week {week.week}: {week.focus}**")
        out += [f"- {action}" for action in week.actions]
        out.append("")

    out += [f"## 6. {SECTIONS[5]}", ""]
    out += [f"[{i}] {url}" for i, url in enumerate(src.urls, 1)]
    return "\n".join(out) + "\n"


def parse_plan(raw: str) -> LaunchPlan:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{") and "{" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    return LaunchPlan.model_validate(json.loads(text))


def plan_problems(plan: LaunchPlan, research, reviews, strategy, brief) -> list[str]:
    problems = []
    if [w.week for w in plan.weeks] != [1, 2, 3, 4]:
        problems.append("weeks must be exactly weeks 1, 2, 3 and 4, in order.")
    for w in plan.weeks:
        if not 2 <= len(w.actions) <= 4:
            problems.append(f"Week {w.week} needs 2 to 4 actions; it has {len(w.actions)}.")
    allowed = known_numbers(research, reviews) | {float(strategy.recommended_price_inr)}
    allowed |= set(_numbers(" ".join(brief.to_inputs().values())))
    text = " ".join([plan.summary, *(w.focus for w in plan.weeks), *(a for w in plan.weeks for a in w.actions)])
    invented = sorted({n for n in _numbers(text) if n > PLAN_TARGET_LIMIT and n not in allowed})
    if invented:
        problems.append(
            f"These numbers are not in the research, reviews, brief or recommended price: {', '.join(f'{n:g}' for n in invented)}. "
            "Use targets in words or small counts (for example 'sign up 20 members') instead."
        )
    return problems


class ReportGuardrail:
    """Checks the plan, then returns the full report as the task's output: CrewAI saves it to output_file."""

    def __init__(self, research_guard, review_guard, strategy_guard):
        self.research_guard, self.review_guard, self.strategy_guard = research_guard, review_guard, strategy_guard
        self.attempts: list[dict] = []
        self.last_plan: LaunchPlan | None = None
        self.report: str | None = None

    def check(self, task_output: Any) -> tuple[bool, Any]:
        try:
            plan = parse_plan(task_output.raw)
        except (json.JSONDecodeError, ValueError, ValidationError) as err:
            feedback = f"Your answer must be one JSON object matching the LaunchPlan schema. Error: {err}"
            self.attempts.append({"stopped_by": "format", "feedback": feedback})
            return False, feedback
        self.last_plan = plan
        research, reviews = self.research_guard.last_research, self.review_guard.last_reviews
        strategy, brief = self.strategy_guard.last_strategy, self.research_guard.brief
        problems = plan_problems(plan, research, reviews, strategy, brief)
        if problems:
            feedback = "Fix these problems and answer again:\n- " + "\n- ".join(problems)
            self.attempts.append({"stopped_by": "rules", "feedback": feedback})
            return False, feedback
        self.report = assemble_report(brief, research, reviews, strategy, plan)
        self.attempts.append({"stopped_by": None, "feedback": "passed"})
        return True, self.report
