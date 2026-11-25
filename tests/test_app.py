"""Offline tests for the app pages, progress events, the evidence trail and the PDF export."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from launchscout import pipeline, progress, tools
from launchscout.evidence import Evidence, normalize_text, normalize_url
from launchscout.pdf import report_pdf
from launchscout.trail import build_trail
from tests.test_strategy_checks import RESEARCH, REVIEWS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SERPER_API_KEY", "")


def page(name):
    return AppTest.from_file(str(ROOT / "app_pages" / name), default_timeout=60).run()


def test_app_frame_loads(no_keys):
    assert not AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run().exception


def test_research_page_without_keys_shows_note_and_example(no_keys):
    at = page("research.py")
    assert not at.exception
    assert at.button[0].disabled  # no keys: research is off, with a friendly note instead of an error
    assert any("no API keys" in i.value for i in at.info)
    assert any("Competitor Report" in m.value for m in at.markdown)


def test_examples_and_how_it_works_pages(no_keys):
    examples = page("examples.py")
    assert not examples.exception and any("Competitor Report" in m.value for m in examples.markdown)
    how = page("how_it_works.py")
    assert not how.exception and "Market Researcher" in " ".join(m.value for m in how.markdown)


def test_tools_emit_progress(monkeypatch):
    events = []
    progress.set_sink(events.append)
    monkeypatch.setattr(tools.SerperDevTool, "_run", lambda self, **kw: {"organic": []})
    tools.BudgetedSearch(budget_id=tools.new_budget())._run(search_query="dance classes Chennai fees")
    progress.set_sink(None)
    assert events == [{"role": "Market Researcher", "message": "Searching the web: dance classes Chennai fees"}]


def test_pipeline_reports_needs_review_instead_of_crashing(monkeypatch):
    class FailingCrew:
        agents = []
        tasks = [type("T", (), {"guardrail": type("G", (), {"__self__": guard})()})() for guard in [
            type("R", (), {"last_research": None, "evidence": []})(), type("V", (), {"last_reviews": None, "evidence": []})(),
            type("S", (), {"last_strategy": None})(), type("W", (), {"report": None})()]]

        def kickoff(self, inputs):
            raise RuntimeError("guardrail gave up")

    events = []
    monkeypatch.setattr(pipeline, "build_crew", lambda brief, task_callback=None: FailingCrew())
    from launchscout.brief import DEMO_BRIEF

    result = pipeline.run_crew(DEMO_BRIEF, sink=events.append)
    assert result["status"] == "needs_review" and result["report"] is None and result["trail"] == []
    assert events[0] == {"role": "Market Researcher", "message": "__start__"}


def test_trail_shows_the_words_behind_each_claim():
    url = "https://a.example.com"  # RESEARCH prices cite this page
    research_ev = [Evidence(normalize_url(url), normalize_text("Studio A adults 4,000 per month, Studio B 999 per month"),
                            "search", url, raw="Studio A adults 4,000 per month, Studio B 999 per month")]
    trail = build_trail(RESEARCH, REVIEWS, research_ev, [])
    price = next(t for t in trail if t["claim"].startswith("Rs 4,000"))
    assert price["excerpt"].startswith("Studio A adults 4,000")
    assert {t["kind"] for t in trail} >= {"price", "rating", "complaint"}


def test_pdf_handles_rupee_sign_and_tables():
    pdf = report_pdf("# Report\n\n| A | B |\n|---|---|\n| ₹999 — month | x |\n\nText “quoted”.")
    assert pdf.startswith(b"%PDF") and len(pdf) > 500
