"""Checks for the Review Analyst: every like, complaint and rating must be in what it saw.

Same pattern as the research checks: repair in code first (drop what no evidence
supports), then send the agent back only if what is left breaks a rule.
A review point is supported only when its quote appears word for word in a Google
review of that business (from the Google reviews tool). Quotes from listing
descriptions or a business's own pages are marketing, not customers.
"""

import json
import re
from typing import Any

from pydantic import ValidationError

from launchscout.evidence import Evidence, extract_evidence, normalize_text, normalize_url
from launchscout.progress import emit
from launchscout.schemas import CompetitorReviews, ReviewResearch

MIN_REVIEWED = 3  # competitors with at least one supported like or complaint
MIN_COMPLAINTS = 2  # complaints across the market: the raw material for finding the gap
PARTIAL_MIN_REVIEWED = 1  # on the last attempt, accept this many reviewed competitors


def parse_reviews(raw: str) -> ReviewResearch:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{") and "{" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    return ReviewResearch.model_validate(json.loads(text))


def _units(evidence: list[Evidence], name: str, kind: str) -> list[Evidence]:
    """Review or place units from the Google reviews tool, looked up for this business."""
    key = normalize_text(name)
    return [e for e in evidence if e.kind == kind and normalize_text(e.subject) == key]


def point_supported(point, name: str, evidence: list[Evidence]) -> bool:
    """Only a customer's review counts: not a listing description, not the business's own page."""
    quote = normalize_text(point.quote)
    return len(quote.split()) >= 3 and any(
        quote in e.text and normalize_url(point.source_url or "") == e.url for e in _units(evidence, name, "review")
    )


def rating_supported(c: CompetitorReviews, evidence: list[Evidence]) -> bool:
    if c.rating is None:
        return False
    needle = normalize_text(f"{c.rating:g}")
    return any(re.search(rf"\brating {needle}\b", e.text) for e in _units(evidence, c.competitor, "place"))


def repair_reviews(reviews: ReviewResearch, evidence: list[Evidence], competitor_names: list[str]):
    """Drop unsupported points and ratings; keep only researched competitors; add missing ones empty."""
    reviews = reviews.model_copy(deep=True)
    notes: list[str] = []
    by_name = {normalize_text(n): n for n in competitor_names}
    kept: dict[str, CompetitorReviews] = {}
    for c in reviews.competitors:
        key = normalize_text(c.competitor)
        if key not in by_name:
            notes.append(f"Removed '{c.competitor}': not one of the researched competitors.")
            continue
        c.competitor = by_name[key]
        for field in ("likes", "complaints"):
            good = []
            for p in getattr(c, field):
                if point_supported(p, c.competitor, evidence):
                    good.append(p)
                else:
                    notes.append(f"Removed {field[:-1]} '{p.point}' for '{c.competitor}': not a quote from its Google reviews.")
            setattr(c, field, good)
        if c.rating is not None and not rating_supported(c, evidence):
            notes.append(f"Removed rating {c.rating} for '{c.competitor}': not the rating on its Google listing.")
            c.rating = c.rating_count = c.rating_source_url = None
        kept[c.competitor] = c
    for name in competitor_names:
        if name not in kept:
            kept[name] = CompetitorReviews(competitor=name, likes=[], complaints=[])
    reviews.competitors = [kept[n] for n in competitor_names]
    return reviews, notes


def merge_reviews(earlier: ReviewResearch | None, latest: ReviewResearch) -> ReviewResearch:
    """Keep supported points from earlier attempts.

    Bug found in a real run: attempt 1 quoted a real review, the retries had no lookups left,
    and the final answer dropped that quote, so the run failed with 0 reviewed competitors.
    Both inputs are already repaired, so everything kept here is backed by evidence.
    """
    if earlier is None:
        return latest
    merged = latest.model_copy(deep=True)
    before = {c.competitor: c for c in earlier.competitors}
    for c in merged.competitors:
        old = before.get(c.competitor)
        if old is None:
            continue
        for field in ("likes", "complaints"):
            points = getattr(c, field)
            seen = {normalize_text(p.quote) for p in points}
            points += [p for p in getattr(old, field) if normalize_text(p.quote) not in seen]
        if c.rating is None and old.rating is not None:
            c.rating, c.rating_count, c.rating_source_url = old.rating, old.rating_count, old.rating_source_url
    return merged


def review_problems(reviews: ReviewResearch) -> list[str]:
    reviewed = [c for c in reviews.competitors if c.likes or c.complaints]
    complaints = sum(len(c.complaints) for c in reviews.competitors)
    problems = []
    if len(reviewed) < MIN_REVIEWED:
        problems.append(f"At least {MIN_REVIEWED} competitors need a supported like or complaint; only {len(reviewed)} have one.")
    if complaints < MIN_COMPLAINTS:
        problems.append(f"Find at least {MIN_COMPLAINTS} supported complaints across the competitors; you have {complaints}.")
    return problems


class ReviewGuardrail:
    """CrewAI guardrail for the review task. Pass the bound method `guard.check` to the Task."""

    def __init__(self, research_guard, max_retries: int = 2):
        self.research_guard = research_guard  # holds the researched competitors once task 1 passes
        self.max_retries = max_retries  # must match the task's guardrail_max_retries
        self.partial = False
        self.evidence: list[Evidence] = []
        self.attempts: list[dict] = []
        self.last_reviews: ReviewResearch | None = None

    def check(self, task_output: Any) -> tuple[bool, Any]:
        known = {(e.url, e.text) for e in self.evidence}
        for unit in extract_evidence(getattr(task_output, "messages", None)):
            if (unit.url, unit.text) not in known:
                known.add((unit.url, unit.text))
                self.evidence.append(unit)
        try:
            parsed = parse_reviews(task_output.raw)
        except (json.JSONDecodeError, ValueError, ValidationError) as err:
            feedback = f"Your answer must be one JSON object matching the ReviewResearch schema. Error: {err}"
            self.attempts.append({"stopped_by": "format", "feedback": feedback, "repairs": []})
            return False, feedback

        research = self.research_guard.last_research
        names = [c.name for c in research.competitors] if research else [c.competitor for c in parsed.competitors]
        value, repairs = repair_reviews(parsed, self.evidence, names)
        value = merge_reviews(self.last_reviews, value)
        self.last_reviews = value
        problems = review_problems(value)
        # Partial outcome, as for prices: small businesses often have no Google listing. On the last
        # attempt, pass with at least one reviewed competitor; the report lists who has no reviews.
        reviewed = sum(1 for c in value.competitors if c.likes or c.complaints)
        if problems and len(self.attempts) >= self.max_retries and reviewed >= PARTIAL_MIN_REVIEWED:
            self.partial = True
            problems = []
        if problems:
            empty = [c.competitor for c in value.competitors if not (c.likes or c.complaints)]
            feedback = (
                "Fix these problems and answer again:\n- " + "\n- ".join(problems)
                + "\nEvery like and complaint needs a quote copied word for word from a Google review returned by "
                "the Google reviews tool, with that listing's link as source_url. Look up: " + ", ".join(empty) + "."
            )
            if repairs:
                feedback += "\nCode already removed these unsupported claims:\n- " + "\n- ".join(repairs)
            self.attempts.append({"stopped_by": "rules after repair", "feedback": feedback, "repairs": repairs})
            emit("Review Analyst", f"Sent back to dig further: {problems[0]}")
            return False, feedback
        self.attempts.append({"stopped_by": None, "feedback": "passed", "repairs": repairs})
        likes = sum(len(c.likes) for c in value.competitors)
        complaints = sum(len(c.complaints) for c in value.competitors)
        emit("Review Analyst", f"Found {likes} things customers like and {complaints} complaints")
        return True, value
