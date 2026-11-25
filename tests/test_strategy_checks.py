"""Offline tests for the comparison matrix and the Strategy Analyst's checks."""

import json
from types import SimpleNamespace

from launchscout.brief import DEMO_BRIEF
from launchscout.matrix import build_matrix, matrix_markdown
from launchscout.schemas import MarketResearch, ReviewResearch, StrategyAnalysis
from launchscout.strategy_checks import StrategyGuardrail, strategy_problems


def comp(name, prices):
    return {"name": name, "locality": "x", "offering": "x", "schedule": "Mon 7 pm", "fit_reason": "x",
            "price_status": "published" if prices else "on_enquiry",
            "prices": [{"label": label, "amount_inr": amt, "unit": unit, "source_url": "https://a.example.com"} for label, amt, unit in prices],
            "channels": [], "offers": [], "source_urls": ["https://a.example.com"]}


RESEARCH = MarketResearch.model_validate({"competitors": [
    comp("Studio A", [("Joining", 1500, "joining fee"), ("Adults", 4000, "per month")]),
    comp("Studio B", [("Adults", 999, "per month"), ("Drop-in", 250, "per class")]),
    comp("Studio C", []),
], "market_price_context": []})
REVIEWS = ReviewResearch.model_validate({"competitors": [
    {"competitor": "Studio A", "rating": 4.8, "rating_count": 616, "rating_source_url": None, "likes": [],
     "complaints": [{"point": "Kids dominate batches", "quote": "x x x", "source_url": "https://maps.google.com/?cid=1"}]},
]})


def strategy(**overrides):
    base = {"market_gap": "No studio publishes an adults-only 8 pm batch; Studio A charges Rs 4,000 and Studio B Rs 999.",
            "gap_evidence": ["Studio A", "Studio B"], "positioning": "After-work dance, adults only, Rs 1,999 a month",
            "recommended_price_inr": 1999, "price_unit": "per month",
            "price_reason": "Between Studio B's 999 and Studio A's 4,000, rated 4.8 by 616 people."}
    return StrategyAnalysis.model_validate({**base, **overrides})


def test_matrix_uses_monthly_price_and_skips_joining_fee():
    rows = build_matrix(RESEARCH, REVIEWS)
    assert rows[0]["price"]["amount_inr"] == 4000 and rows[1]["price"]["amount_inr"] == 999
    assert rows[2]["price"] is None and rows[0]["rating"] == 4.8
    assert "Rs 4,000 per month" in matrix_markdown(rows) and "on enquiry" in matrix_markdown(rows)


def test_good_strategy_passes():
    assert strategy_problems(strategy(), RESEARCH, REVIEWS) == []


def test_invented_number_is_caught():
    problems = strategy_problems(strategy(market_gap="Competitors charge Rs 3,200 on average."), RESEARCH, REVIEWS)
    assert any("3200" in p for p in problems)


def test_small_numbers_like_times_are_fine():
    assert strategy_problems(strategy(market_gap="Nobody runs an 8 pm batch 3 days a week."), RESEARCH, REVIEWS) == []


def test_numbers_from_the_brief_are_allowed():
    s = strategy(market_gap="Nobody targets professionals aged 35 to 45.")  # 35 and 45 are above the small-number cut
    assert any("45" in p for p in strategy_problems(s, RESEARCH, REVIEWS))
    assert strategy_problems(s, RESEARCH, REVIEWS, SimpleNamespace(to_inputs=lambda: {"t": "age 35 to 45"})) == []


def test_unknown_competitor_and_price_range():
    problems = strategy_problems(strategy(gap_evidence=["Studio Z"], recommended_price_inr=9000,
                                          positioning="Rs 9000 a month"), RESEARCH, REVIEWS)
    assert any("Studio Z" in p for p in problems) and any("outside the believable range" in p for p in problems)


def test_positioning_must_show_price():
    problems = strategy_problems(strategy(positioning="After-work dance for adults"), RESEARCH, REVIEWS)
    assert any("must include the recommended price" in p for p in problems)


def test_guardrail_returns_model_or_feedback():
    guard = StrategyGuardrail(SimpleNamespace(last_research=RESEARCH), SimpleNamespace(last_reviews=REVIEWS))
    ok, value = guard.check(SimpleNamespace(raw=strategy().model_dump_json()))
    assert ok and isinstance(value, StrategyAnalysis)
    ok, feedback = guard.check(SimpleNamespace(raw=json.dumps({"market_gap": "x"})))
    assert not ok and "StrategyAnalysis" in feedback


def test_three_agent_crew_wiring(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    from launchscout.crew import build_crew

    crew = build_crew(DEMO_BRIEF, stages=3)
    assert [a.role for a in crew.agents] == ["Market Researcher", "Review Analyst", "Strategy Analyst"]
    assert crew.tasks[2].context == [crew.tasks[0], crew.tasks[1]] and crew.agents[2].tools == []
