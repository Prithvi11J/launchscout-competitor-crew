"""Offline tests for the app, the progress events and the PDF export."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from launchscout import pipeline, progress, tools
from launchscout.pdf import report_pdf

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_without_keys_shows_example_report(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SERPER_API_KEY", "")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("example report" in i.value.lower() for i in at.info)
    assert at.button[0].disabled  # no keys: the research button is off, not an error
    assert any("Competitor Report" in m.value for m in at.markdown)


def test_tools_emit_progress(monkeypatch):
    events = []
    progress.set_sink(events.append)
    monkeypatch.setattr(tools.SerperDevTool, "_run", lambda self, **kw: {"organic": []})
    tools.BudgetedSearch(budget_id=tools.new_budget())._run(search_query="dance classes Chennai fees")
    progress.set_sink(None)
    assert events == [{"role": "Market Researcher", "message": "Searching the web: dance classes Chennai fees"}]


def test_pipeline_reports_needs_review_instead_of_crashing(monkeypatch):
    class FailingCrew:
        tasks = [type("T", (), {"guardrail": type("G", (), {"__self__": guard})()})() for guard in [
            type("R", (), {"last_research": None})(), type("V", (), {"last_reviews": None})(),
            type("S", (), {"last_strategy": None})(), type("W", (), {"report": None})()]]

        def kickoff(self, inputs):
            raise RuntimeError("guardrail gave up")

    events = []
    monkeypatch.setattr(pipeline, "build_crew", lambda brief, task_callback=None: FailingCrew())
    from launchscout.brief import DEMO_BRIEF

    result = pipeline.run_crew(DEMO_BRIEF, sink=events.append)
    assert result["status"] == "needs_review" and result["report"] is None
    assert events[0] == {"role": "Market Researcher", "message": "__start__"}


def test_pdf_handles_rupee_sign_and_tables():
    pdf = report_pdf("# Report\n\n| A | B |\n|---|---|\n| ₹999 — month | x |\n\nText “quoted”.")
    assert pdf.startswith(b"%PDF") and len(pdf) > 500
