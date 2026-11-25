"""Checks for the Review Analyst: every like, complaint and rating must be in what it saw.

Same pattern as the research checks: repair in code first (drop what no evidence
supports), then send the agent back only if what is left breaks a rule.
A review point is supported when its quote appears word for word in a search
result or page from its source URL, and that result or URL names the business.
"""

import json
import re
from typing import Any

from pydantic import ValidationError

from launchscout.evidence import (
    AFTER,
    BEFORE,
    Evidence,
    extract_evidence,
    mention_positions,
    names_business,
    normalize_text,
    normalize_url,
)
from launchscout.schemas import CompetitorReviews, ReviewResearch

MIN_REVIEWED = 3  # competitors with at least one supported like or complaint
MIN_COMPLAINTS = 2  # complaints across the market: the raw material for finding the gap


def parse_reviews(raw: str) -> ReviewResearch:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{") and "{" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    return ReviewResearch.model_validate(json.loads(text))


def _url_names(url: str, name: str) -> bool:
    """justdial.com/chennai/dance-and-dance-studio-greams-road names the studio in its address."""
    return bool(mention_positions(normalize_text(url.replace("/", " ").replace("-", " ")), name))


def _units_for(evidence: list[Evidence], url: str, name: str) -> list[Evidence]:
    key = normalize_url(url or "")
    return [e for e in evidence if e.url == key and (names_business(e, name) or _url_names(e.url, name))]


def point_supported(point, name: str, evidence: list[Evidence]) -> bool:
    quote = normalize_text(point.quote)
    return len(quote.split()) >= 3 and any(quote in e.text for e in _units_for(evidence, point.source_url, name))


def rating_supported(c: CompetitorReviews, evidence: list[Evidence]) -> bool:
    if c.rating is None or not c.rating_source_url:
        return False
    needle = normalize_text(f"{c.rating:g}")
    for e in _units_for(evidence, c.rating_source_url, c.competitor):
        if _url_names(e.url, c.competitor) and re.search(rf"\b{needle}\b", e.text):
            return True  # the business's own listing page
        for pos in mention_positions(e.text, c.competitor):
            if re.search(rf"\b{needle}\b", e.text[max(0, pos - BEFORE) : pos + AFTER]):
                return True
    return False


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
                    notes.append(f"Removed {field[:-1]} '{p.point}' for '{c.competitor}': quote not found on {p.source_url}.")
            setattr(c, field, good)
        if c.rating is not None and not rating_supported(c, evidence):
            notes.append(f"Removed rating {c.rating} for '{c.competitor}': not shown next to the business on its source.")
            c.rating = c.rating_count = c.rating_source_url = None
        kept[c.competitor] = c
    for name in competitor_names:
        if name not in kept:
            kept[name] = CompetitorReviews(competitor=name, likes=[], complaints=[])
    reviews.competitors = [kept[n] for n in competitor_names]
    return reviews, notes


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

    def __init__(self, research_guard):
        self.research_guard = research_guard  # holds the researched competitors once task 1 passes
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
        self.last_reviews = value
        problems = review_problems(value)
        if problems:
            empty = [c.competitor for c in value.competitors if not (c.likes or c.complaints)]
            feedback = (
                "Fix these problems and answer again:\n- " + "\n- ".join(problems)
                + "\nEvery like and complaint needs a quote copied word for word from a search result or page "
                "that names the business. Search for reviews of: " + ", ".join(empty)
                + " (for example '<name> <city> reviews' or the business's Justdial or Google listing)."
            )
            if repairs:
                feedback += "\nCode already removed these unsupported claims:\n- " + "\n- ".join(repairs)
            self.attempts.append({"stopped_by": "rules after repair", "feedback": feedback, "repairs": repairs})
            return False, feedback
        self.attempts.append({"stopped_by": None, "feedback": "passed", "repairs": repairs})
        return True, value
