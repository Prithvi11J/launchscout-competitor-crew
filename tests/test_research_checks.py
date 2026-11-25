"""Offline tests for the research guardrail, brief and crew wiring (no API calls)."""

import json
from types import SimpleNamespace

from launchscout.brief import DEMO_BRIEF, BusinessBrief
from launchscout.checks import (
    ResearchGuardrail,
    find_problems,
    parse_research,
    research_guardrail,
)
from launchscout.schemas import FitJudgement, FitVerdict, MarketResearch


def competitor(name, priced=True, url="https://example.com/studio"):
    return {
        "name": name,
        "locality": "RS Puram",
        "offering": "Bollywood, evening batches",
        "schedule": "Mon-Fri 7-8 pm",
        "fit_reason": "Evening adult batches",
        "price_status": "published" if priced else "on_enquiry",
        "prices": [{"label": "Adults monthly", "amount_inr": 900, "unit": "per month", "source_url": url}] if priced else [],
        "channels": ["Instagram"],
        "offers": [],
        "source_urls": [url],
    }


def research(*comps):
    return {"competitors": list(comps), "market_price_context": []}


def good_answer():
    return research(
        competitor("Studio A", url="https://a.example.com"),
        competitor("Studio B", url="https://b.example.com"),
        competitor("Studio C", url="https://c.example.com"),
        competitor("Studio D", priced=False, url="https://d.example.com"),
    )


def search_messages(answer):
    """Fake agent history: one search whose results name each competitor next to its price."""
    organic = [
        {"title": c["name"], "link": c["source_urls"][0], "snippet": f"{c['name']} adults batch Rs 900 per month"}
        for c in answer["competitors"]
    ]
    return [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": '{"search_query": "q"}'}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": repr({"organic": organic})},
    ]


def output_for(answer):
    return SimpleNamespace(raw=json.dumps(answer), messages=search_messages(answer))


def test_good_answer_passes_and_returns_model():
    ok, value = research_guardrail(SimpleNamespace(raw=json.dumps(good_answer())))
    assert ok
    assert isinstance(value, MarketResearch)


def test_json_inside_code_fence_is_read():
    raw = "Here you go:\n```json\n" + json.dumps(good_answer()) + "\n```"
    assert len(parse_research(raw).competitors) == 4


def test_not_json_fails_with_reason():
    ok, reason = research_guardrail(SimpleNamespace(raw="I found three studios."))
    assert not ok and "JSON" in reason


def test_too_few_priced_competitors():
    data = research(competitor("A"), competitor("B"), competitor("C", priced=False))
    problems = find_problems(MarketResearch.model_validate(data))
    assert any("published price" in p for p in problems)


def test_listing_site_is_not_a_competitor():
    data = good_answer()
    data["competitors"][0]["name"] = "Justdial"
    problems = find_problems(MarketResearch.model_validate(data))
    assert any("listing site" in p for p in problems)


def test_published_without_prices_is_flagged():
    data = good_answer()
    data["competitors"][0]["prices"] = []
    assert any("no prices" in p for p in find_problems(MarketResearch.model_validate(data)))


def test_price_needs_real_url():
    data = good_answer()
    data["competitors"][0]["prices"][0]["source_url"] = "their Instagram"
    assert any("needs the URL" in p for p in find_problems(MarketResearch.model_validate(data)))


def test_brief_fills_placeholders():
    inputs = BusinessBrief(idea=" Yoga ", city="Madurai", target_customer="Students", known_competitors=["X", " "]).to_inputs()
    assert inputs == {"idea": "Yoga", "city": "Madurai", "target_customer": "Students", "known_competitors": "X"}
    assert DEMO_BRIEF.to_inputs()["known_competitors"] == "none given"


def test_crew_wiring_without_api(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    from launchscout.crew import build_crew

    crew = build_crew(DEMO_BRIEF, tools=[])
    task = crew.tasks[0]
    assert [a.role for a in crew.agents] == ["Market Researcher"]
    assert task.output_pydantic is MarketResearch
    assert "{city}" in task.description and "{city}" in crew.agents[0].goal


def test_duplicate_prices_are_removed_after_passing():
    data = good_answer()
    first = data["competitors"][0]["prices"][0]
    data["competitors"][0]["prices"].append({**first, "source_url": "https://other.example.com"})
    ok, value = research_guardrail(SimpleNamespace(raw=json.dumps(data)))
    assert ok and len(value.competitors[0].prices) == 1


def test_tracing_off_by_default():
    import os

    assert os.environ["CREWAI_TRACING_ENABLED"] == "false"


def test_too_many_competitors_from_one_site():
    data = good_answer()
    for c in data["competitors"][:3]:
        c["source_urls"] = ["https://www.urbanpro.com/chennai/dance-classes"]
    problems = find_problems(MarketResearch.model_validate(data))
    assert any("come only from urbanpro.com" in p for p in problems)


def test_missing_fit_reason_is_flagged():
    data = good_answer()
    data["competitors"][0]["fit_reason"] = " "
    assert any("fit_reason" in p for p in find_problems(MarketResearch.model_validate(data)))


def fake_judge(rejected=()):
    def judge(brief, research, llm):
        return FitVerdict(judgements=[
            FitJudgement(name=c.name, direct_competitor=c.name not in rejected, reason="test")
            for c in research.competitors
        ])
    return judge


def test_fit_check_rejects_and_names_the_business():
    guard = ResearchGuardrail(DEMO_BRIEF, judge=fake_judge(rejected={"Studio B"}))
    ok, feedback = guard.check(output_for(good_answer()))
    assert not ok and "Studio B" in feedback and DEMO_BRIEF.target_customer in feedback
    assert len(guard.verdicts) == 1


def test_fit_check_is_skipped_when_code_rules_fail():
    calls = []
    guard = ResearchGuardrail(DEMO_BRIEF, judge=lambda *a: calls.append(1))
    ok, _ = guard.check(SimpleNamespace(raw="not json"))
    assert not ok and calls == []  # no LLM call wasted on a broken answer


def test_fit_check_passes_clean_answer():
    ok, value = ResearchGuardrail(DEMO_BRIEF, judge=fake_judge()).check(output_for(good_answer()))
    assert ok and isinstance(value, MarketResearch)


def test_guardrail_runs_through_crewai_own_code_path(monkeypatch):
    """Unit tests above call the guardrail directly; CrewAI also logs it (reading its source).
    Run it the way CrewAI does so that kind of bug shows up offline, not in a paid run."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    from crewai.tasks.task_output import TaskOutput
    from crewai.utilities.guardrail import process_guardrail

    from launchscout.crew import build_crew

    crew = build_crew(DEMO_BRIEF, tools=[], judge=fake_judge())
    task = crew.tasks[0]
    output = TaskOutput(description=task.description, raw=json.dumps(good_answer()), agent="Market Researcher",
                        messages=search_messages(good_answer()))
    result = process_guardrail(output=output, guardrail=task.guardrail, retry_count=0, event_source=task, from_task=task)
    assert result.success and isinstance(result.result, MarketResearch)


def test_answer_without_evidence_stops_before_fit_check():
    calls = []
    guard = ResearchGuardrail(DEMO_BRIEF, judge=lambda *a: calls.append(1))
    ok, feedback = guard.check(SimpleNamespace(raw=json.dumps(good_answer()), messages=[]))
    assert not ok and "removed" in feedback.lower() and "you listed 0" in feedback
    assert calls == [] and guard.attempts[-1]["stopped_by"] == "rules after repair"


def test_evidence_from_earlier_attempts_still_counts():
    guard = ResearchGuardrail(DEMO_BRIEF, judge=fake_judge())
    guard.check(SimpleNamespace(raw="not json", messages=search_messages(good_answer())))  # attempt 1 searched
    ok, _ = guard.check(SimpleNamespace(raw=json.dumps(good_answer()), messages=[]))  # retry did not search again
    assert ok


def test_last_answer_is_kept_when_checks_fail():
    guard = ResearchGuardrail(DEMO_BRIEF, judge=fake_judge())
    answer = research(competitor("Only one"))
    guard.check(SimpleNamespace(raw=json.dumps(answer), messages=search_messages(answer)))
    assert guard.last_research is not None and guard.last_research.competitors[0].name == "Only one"


def test_same_business_twice_is_a_duplicate():
    from launchscout.checks import duplicate_problems

    data = good_answer()
    data["competitors"][0]["name"] = "Dance Studio Chennai"
    data["competitors"][1]["name"] = "Chennai Dance and Dance Studio"
    assert duplicate_problems(MarketResearch.model_validate(data))


def test_different_studios_are_not_duplicates():
    from launchscout.checks import duplicate_problems

    assert duplicate_problems(MarketResearch.model_validate(good_answer())) == []
