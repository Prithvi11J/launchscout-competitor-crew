"""Offline tests for the research guardrail, brief and crew wiring (no API calls)."""

import json
from types import SimpleNamespace

from launchscout.brief import DEMO_BRIEF, BusinessBrief
from launchscout.checks import (
    ResearchGuardrail,
    find_problems,
    parse_research,
    research_guardrail,
    unverified_urls,
    urls_seen_in_tool_results,
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


def test_urls_from_tool_results_count_but_agent_words_do_not():
    messages = [
        {"role": "user", "content": "Observation: {'link': 'https://a.example.com', 'snippet': 'Rs 900'}"},
        {"role": "assistant", "content": "Final answer cites https://invented.example.com"},
    ]
    seen = urls_seen_in_tool_results(messages)
    assert "https://a.example.com" in seen
    assert "https://invented.example.com" not in seen


def test_unverified_urls_lists_invented_links():
    model = MarketResearch.model_validate(good_answer())
    seen = {"https://a.example.com", "https://b.example.com", "https://c.example.com"}
    assert unverified_urls(model, seen) == ["https://d.example.com"]


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
    ok, feedback = guard.check(SimpleNamespace(raw=json.dumps(good_answer())))
    assert not ok and "Studio B" in feedback and DEMO_BRIEF.target_customer in feedback
    assert len(guard.verdicts) == 1


def test_fit_check_is_skipped_when_code_rules_fail():
    calls = []
    guard = ResearchGuardrail(DEMO_BRIEF, judge=lambda *a: calls.append(1))
    ok, _ = guard.check(SimpleNamespace(raw="not json"))
    assert not ok and calls == []  # no LLM call wasted on a broken answer


def test_fit_check_passes_clean_answer():
    ok, value = ResearchGuardrail(DEMO_BRIEF, judge=fake_judge()).check(SimpleNamespace(raw=json.dumps(good_answer())))
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
    output = TaskOutput(description=task.description, raw=json.dumps(good_answer()), agent="Market Researcher")
    result = process_guardrail(output=output, guardrail=task.guardrail, retry_count=0, event_source=task, from_task=task)
    assert result.success and isinstance(result.result, MarketResearch)
