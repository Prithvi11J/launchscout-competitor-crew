"""Offline tests for the report assembly, the plan checks and the 4-agent crew."""

import json
import re
from types import SimpleNamespace

from launchscout.brief import DEMO_BRIEF
from launchscout.report import SECTIONS, ReportGuardrail, assemble_report, plan_problems
from launchscout.schemas import LaunchPlan
from tests.test_strategy_checks import RESEARCH, REVIEWS, strategy


def plan(**overrides):
    base = {"summary": "Three studios lead; none runs an openly priced adults-only evening batch.",
            "weeks": [{"week": w, "focus": f"Focus {w}", "actions": ["Visit 3 office parks", "Run 2 trial classes"]}
                      for w in (1, 2, 3, 4)]}
    return LaunchPlan.model_validate({**base, **overrides})


def test_report_has_all_six_sections_in_order():
    report = assemble_report(DEMO_BRIEF, RESEARCH, REVIEWS, strategy(), plan())
    positions = [report.index(f"## {i}. {name}") for i, name in enumerate(SECTIONS, 1)]
    assert positions == sorted(positions)


def test_every_price_links_to_a_numbered_source():
    report = assemble_report(DEMO_BRIEF, RESEARCH, REVIEWS, strategy(), plan())
    assert "Rs 4,000 per month [1]" in report
    refs = set(re.findall(r"\[(\d+)\]", report.split("## 6. Sources")[0]))
    listed = set(re.findall(r"^\[(\d+)\] http", report.split("## 6. Sources")[1], re.M))
    assert refs and refs == listed  # every reference has a source line, and no unused sources


def test_complaint_quotes_and_price_count_come_from_data():
    report = assemble_report(DEMO_BRIEF, RESEARCH, REVIEWS, strategy(), plan())
    assert "**Studio A:** Kids dominate batches" in report
    assert "2 of 3 competitors publish a price" in report


def test_plan_rules():
    s = strategy()
    assert plan_problems(plan(), RESEARCH, REVIEWS, s, DEMO_BRIEF) == []
    bad_weeks = plan(weeks=plan().model_dump()["weeks"][:3])
    assert any("weeks 1, 2, 3 and 4" in p for p in plan_problems(bad_weeks, RESEARCH, REVIEWS, s, DEMO_BRIEF))
    invented = plan(summary="Offer a Rs 499 trial pass.")
    assert any("499" in p for p in plan_problems(invented, RESEARCH, REVIEWS, s, DEMO_BRIEF))
    target = plan(summary="Collect 50 reviews by week 4.")
    assert plan_problems(target, RESEARCH, REVIEWS, s, DEMO_BRIEF) == []


def test_guardrail_returns_the_markdown_report():
    guard = ReportGuardrail(SimpleNamespace(last_research=RESEARCH, brief=DEMO_BRIEF),
                            SimpleNamespace(last_reviews=REVIEWS), SimpleNamespace(last_strategy=strategy()))
    ok, report = guard.check(SimpleNamespace(raw=plan().model_dump_json()))
    assert ok and report.startswith("# Competitor Report:") and guard.report == report
    ok, feedback = guard.check(SimpleNamespace(raw=json.dumps({"summary": "x"})))
    assert not ok and "LaunchPlan" in feedback


def test_four_agent_crew_saves_report(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    from launchscout.crew import build_crew

    crew = build_crew(DEMO_BRIEF)
    assert [a.role for a in crew.agents] == ["Market Researcher", "Review Analyst", "Strategy Analyst", "Report Writer"]
    assert crew.tasks[3].output_file == "outputs/report.md" and crew.tasks[3].context == crew.tasks[:3]


def test_partial_report_explains_the_price_gap():
    report = assemble_report(DEMO_BRIEF, RESEARCH, REVIEWS, strategy(), plan(), partial=True)
    assert "fewer than 3 competitors in Chennai publish prices" in report
    assert "fewer than 3" not in assemble_report(DEMO_BRIEF, RESEARCH, REVIEWS, strategy(), plan())
