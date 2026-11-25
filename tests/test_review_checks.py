"""Offline tests for the Review Analyst's checks and the 2-agent crew wiring."""

import json
from types import SimpleNamespace

from launchscout.brief import DEMO_BRIEF
from launchscout.evidence import Evidence, normalize_text, normalize_url
from launchscout.review_checks import ReviewGuardrail, repair_reviews, review_problems
from launchscout.schemas import ReviewResearch

JD = "https://www.justdial.com/Chennai/Dance-And-Dance-Studio-Greams-Road/044P123"
NAMES = ["Dance and Dance Studio", "The Life of Dance", "Raack Academy of Dance"]


def unit(url, text):
    return Evidence(normalize_url(url), normalize_text(text), "search", url)


def point(quote, url=JD, text="x"):
    return {"point": text, "quote": quote, "source_url": url}


def reviews(*items):
    return ReviewResearch.model_validate({"competitors": list(items)})


def entry(name, likes=(), complaints=(), rating=None, rating_url=None):
    return {"competitor": name, "rating": rating, "rating_count": None, "rating_source_url": rating_url,
            "likes": list(likes), "complaints": list(complaints)}


EVIDENCE = [unit(JD, "Dance and Dance Studio 4.5 rating. Great trainers, very patient. Classes often start late.")]


def test_quote_on_a_page_naming_the_business_is_kept():
    r = reviews(entry("Dance and Dance Studio", likes=[point("great trainers, very patient")],
                      complaints=[point("Classes often start late")], rating=4.5, rating_url=JD))
    fixed, notes = repair_reviews(r, EVIDENCE, NAMES)
    c = fixed.competitors[0]
    assert len(c.likes) == 1 and len(c.complaints) == 1 and c.rating == 4.5 and notes == []


def test_invented_quote_and_rating_are_removed():
    r = reviews(entry("Dance and Dance Studio", complaints=[point("the AC never works in summer")], rating=3.9, rating_url=JD))
    fixed, notes = repair_reviews(r, EVIDENCE, NAMES)
    assert fixed.competitors[0].complaints == [] and fixed.competitors[0].rating is None and len(notes) == 2


def test_quote_from_a_page_about_another_business_is_removed():
    other = "https://www.justdial.com/Chennai/Zero-6-Dance/044P999"
    ev = [unit(other, "Zero 6 Dance. Classes often start late.")]
    r = reviews(entry("Dance and Dance Studio", complaints=[point("Classes often start late", url=other)]))
    fixed, _ = repair_reviews(r, ev, NAMES)
    assert fixed.competitors[0].complaints == []


def test_unknown_competitor_dropped_and_missing_ones_added():
    fixed, notes = repair_reviews(reviews(entry("Some Other Studio")), [], NAMES)
    assert [c.competitor for c in fixed.competitors] == NAMES and "not one of the researched" in notes[0]


def test_rules_need_three_reviewed_and_two_complaints():
    fixed, _ = repair_reviews(reviews(entry("Dance and Dance Studio", likes=[point("great trainers, very patient")])), EVIDENCE, NAMES)
    problems = review_problems(fixed)
    assert len(problems) == 2


def test_guardrail_retry_names_the_empty_competitors():
    research_guard = SimpleNamespace(last_research=SimpleNamespace(competitors=[SimpleNamespace(name=n) for n in NAMES]))
    guard = ReviewGuardrail(research_guard)
    ok, feedback = guard.check(SimpleNamespace(raw=json.dumps({"competitors": []}), messages=[]))
    assert not ok and "The Life of Dance" in feedback and "Raack Academy of Dance" in feedback


def test_two_agent_crew_passes_research_as_context(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    from launchscout.crew import build_crew

    crew = build_crew(DEMO_BRIEF, tools=[], with_reviews=True)
    assert [a.role for a in crew.agents] == ["Market Researcher", "Review Analyst"]
    assert crew.tasks[1].context == [crew.tasks[0]]
    assert crew.tasks[1].output_pydantic is ReviewResearch
