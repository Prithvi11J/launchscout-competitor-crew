"""Offline tests for the Google reviews tool, its evidence and the Review Analyst's checks."""

import json
from types import SimpleNamespace

from launchscout import tools
from launchscout.brief import DEMO_BRIEF
from launchscout.evidence import Evidence, extract_evidence, normalize_text, normalize_url
from launchscout.review_checks import ReviewGuardrail, repair_reviews, review_problems
from launchscout.schemas import ReviewResearch

LINK = "https://maps.google.com/?cid=123"
NAMES = ["Dance and Dance Studio", "The Life of Dance", "Raack Academy of Dance"]


def review_unit(text, subject="Dance and Dance Studio"):
    return Evidence(normalize_url(LINK), normalize_text(text), "review", LINK, subject)


PLACE = Evidence(normalize_url(LINK), normalize_text("Dance and Dance Academy Anna Salai Chennai rating 4.3 from 40"),
                 "place", LINK, "Dance and Dance Studio")
EVIDENCE = [PLACE, review_unit("Great trainers, very patient with beginners."), review_unit("Dingy studio and ill mannered staff.")]


def point(quote, url=LINK):
    return {"point": "x", "quote": quote, "source_url": url}


def entry(name, likes=(), complaints=(), rating=None):
    return {"competitor": name, "rating": rating, "rating_count": None, "rating_source_url": LINK,
            "likes": list(likes), "complaints": list(complaints)}


def reviews(*items):
    return ReviewResearch.model_validate({"competitors": list(items)})


def test_quotes_from_reviews_and_listing_rating_are_kept():
    r = reviews(entry("Dance and Dance Studio", likes=[point("very patient with beginners")],
                      complaints=[point("Dingy studio and ill mannered staff")], rating=4.3))
    fixed, notes = repair_reviews(r, EVIDENCE, NAMES)
    c = fixed.competitors[0]
    assert len(c.likes) == 1 and len(c.complaints) == 1 and c.rating == 4.3 and notes == []


def test_marketing_text_is_not_a_review():
    """The first Stage 2 run quoted a studio's own Facebook post as a customer 'like'."""
    page = Evidence(normalize_url("https://facebook.com/x"), normalize_text("we are more than just a dance family"), "page")
    r = reviews(entry("Dance and Dance Studio", likes=[point("we are more than just a dance family", "https://facebook.com/x")]))
    fixed, _ = repair_reviews(r, [page], NAMES)
    assert fixed.competitors[0].likes == []


def test_review_of_another_business_does_not_count():
    other = [review_unit("Dingy studio and ill mannered staff.", subject="Zero 6 Dance and Fitness Company")]
    fixed, _ = repair_reviews(reviews(entry("Dance and Dance Studio", complaints=[point("Dingy studio and ill mannered staff")])), other, NAMES)
    assert fixed.competitors[0].complaints == []


def test_wrong_rating_removed():
    fixed, notes = repair_reviews(reviews(entry("Dance and Dance Studio", rating=4.8)), EVIDENCE, NAMES)
    assert fixed.competitors[0].rating is None and "Google listing" in notes[0]


def test_unknown_competitor_dropped_and_missing_added():
    fixed, notes = repair_reviews(reviews(entry("Some Other Studio")), [], NAMES)
    assert [c.competitor for c in fixed.competitors] == NAMES and "not one of the researched" in notes[0]


def test_rules_need_three_reviewed_and_two_complaints():
    fixed, _ = repair_reviews(reviews(entry("Dance and Dance Studio", likes=[point("very patient with beginners")])), EVIDENCE, NAMES)
    assert len(review_problems(fixed)) == 2


def test_guardrail_retry_names_the_empty_competitors():
    research_guard = SimpleNamespace(last_research=SimpleNamespace(competitors=[SimpleNamespace(name=n) for n in NAMES]))
    ok, feedback = ReviewGuardrail(research_guard).check(SimpleNamespace(raw=json.dumps({"competitors": []}), messages=[]))
    assert not ok and "Look up: Dance and Dance Studio, The Life of Dance, Raack Academy of Dance" in feedback


# --- the tool --------------------------------------------------------------------------

PLACES = [
    {"title": "The Dance Studio. Anna Nagar", "address": "Anna Nagar, Chennai", "cid": "1"},
    {"title": "Dance and Dance Academy", "address": "714 Pathari Road, Anna Salai, Chennai", "cid": "2", "rating": 4.3, "ratingCount": 40},
    {"title": "Dance and Dance Studio", "address": "RS Puram, Coimbatore", "cid": "3"},
]


def test_pick_place_needs_matching_name_and_city():
    assert tools.pick_place(PLACES, "Dance and Dance Studio", "Chennai")["cid"] == "2"
    assert tools.pick_place(PLACES, "Zenith Dance Academy", "Chennai") is None
    assert tools.pick_place(PLACES, "Dance and Dance Studio", "Madurai") is None


def test_tool_filters_old_short_and_duplicate_reviews(monkeypatch):
    recent, old = "2026-06-01T00:00:00Z", "2018-01-01T00:00:00Z"
    replies = {
        "maps": {"places": PLACES},
        "reviews": {"reviews": [
            {"id": "a", "rating": 1, "date": "a year ago", "isoDate": recent, "snippet": "Dingy studio and ill mannered staff."},
            {"id": "b", "rating": 1, "date": "8 years ago", "isoDate": old, "snippet": "Terrible service and very rude owner here."},
            {"id": "c", "rating": 1, "date": "a month ago", "isoDate": recent, "snippet": "Rahul singh"},
        ]},
    }
    monkeypatch.setattr(tools, "_serper", lambda path, body: replies[path])
    out = json.loads(tools.GoogleReviewsTool(budget_id=tools.new_budget())._run("Dance and Dance Studio", "Chennai"))
    assert out["found"] and out["link"] == "https://maps.google.com/?cid=2"
    assert [r["text"] for r in out["reviews"]] == ["Dingy studio and ill mannered staff."]  # once, recent, real


def test_tool_output_becomes_review_and_place_units():
    content = json.dumps({"business_name": "Dance and Dance Studio", "found": True, "listing_name": "Dance and Dance Academy",
                          "address": "Anna Salai, Chennai", "rating": 4.3, "rating_count": 40, "link": LINK,
                          "reviews": [{"stars": 1, "date": "x", "text": "Dingy studio and ill mannered staff."}]})
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "r1", "function": {
            "name": "google_reviews", "arguments": '{"business_name": "Dance and Dance Studio", "city": "Chennai"}'}}]},
        {"role": "tool", "tool_call_id": "r1", "content": content},
    ]
    units = extract_evidence(messages)
    assert [u.kind for u in units] == ["place", "review"] and all(u.subject == "Dance and Dance Studio" for u in units)


def test_two_agent_crew_wiring(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    from launchscout.crew import build_crew

    crew = build_crew(DEMO_BRIEF, stages=2)
    assert [a.role for a in crew.agents] == ["Market Researcher", "Review Analyst"]
    assert crew.tasks[1].context == [crew.tasks[0]]
    assert [t.name for t in crew.agents[1].tools] == ["Google reviews"]
