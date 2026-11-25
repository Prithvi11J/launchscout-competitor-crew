"""Offline tests for the tools' rules and the per-run budget (no network)."""

import copy

import pytest
from crewai_tools import ScrapeWebsiteTool, SerperDevTool

from launchscout.evidence import extract_evidence, owns_domain
from launchscout.tools import REFUSAL_PREFIX, BudgetedSearch, BusinessPageReader, budget_used, new_budget


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(ScrapeWebsiteTool, "_run", lambda self, **kw: "The following text is scraped website content:\n\nFees")
    monkeypatch.setattr(SerperDevTool, "_run", lambda self, **kw: {"organic": []})


def test_listing_and_social_pages_are_refused_without_using_budget(offline):
    budget = new_budget()
    reader = BusinessPageReader(budget_id=budget)
    for url in ["https://www.urbanpro.com/chennai/dance-classes", "https://www.instagram.com/reel/abc/",
                "https://m.facebook.com/x", "https://www.justdial.com/Chennai/X"]:
        assert reader._run(website_url=url).startswith(REFUSAL_PREFIX)
    assert budget_used(budget)["page_reads"] == 0


def test_own_website_is_opened_and_counted(offline):
    budget = new_budget()
    reader = BusinessPageReader(budget_id=budget)
    assert "Fees" in reader._run(website_url="https://www.danceanddance.com/studio/")
    assert budget_used(budget)["page_reads"] == 1


def test_budget_holds_across_copies_of_the_tool(offline):
    """The real bug: CrewAI copies tools per attempt, so a per-object counter reset. Ours can't."""
    budget = new_budget()
    search = BudgetedSearch(budget_id=budget, limit=2)
    first_attempt, retry = search.model_copy(), copy.copy(search)
    assert not str(first_attempt._run(search_query="a")).startswith(REFUSAL_PREFIX)
    assert not str(retry._run(search_query="b")).startswith(REFUSAL_PREFIX)
    assert str(search._run(search_query="c")).startswith(REFUSAL_PREFIX)
    assert budget_used(budget)["searches"] == 2


def test_runs_have_separate_budgets(offline):
    a, b = new_budget(), new_budget()
    BudgetedSearch(budget_id=a, limit=1)._run(search_query="x")
    assert str(BudgetedSearch(budget_id=b, limit=1)._run(search_query="x")) == "{'organic': []}"


def test_refusal_is_not_evidence():
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "p1", "function": {"name": "read", "arguments": '{"website_url": "https://www.urbanpro.com/x"}'}}]},
        {"role": "tool", "tool_call_id": "p1", "content": f"{REFUSAL_PREFIX} https://www.urbanpro.com/x is a listing page"},
    ]
    assert extract_evidence(messages) == []


def test_domain_made_of_initials_is_the_business_own_site():
    assert owns_domain("wsda.in", "Winning Steps Dance Academy")
    assert not owns_domain("wsda.in", "Zero 6 Dance and Fitness Company")
