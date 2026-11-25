"""The web tools agents can choose to use, with a budget per run.

Each Serper search costs a credit, so the budget is a cost line, not a nicety.
CrewAI's own `max_usage_count` turned out not to hold across guardrail retries
(CrewAI rebuilds its internal tool copies on each attempt: one run made 15 page
reads with a cap of 8), so the budget is enforced here, inside `_run`, where
every real call has to pass. Counts live in a registry keyed by a budget id,
so they survive any copying CrewAI does.
"""

from itertools import count
from typing import Any
from urllib.parse import urlparse

from crewai_tools import ScrapeWebsiteTool, SerperDevTool

SEARCHES_PER_RUN = 24  # whole run, including guardrail retries: at most 24 Serper credits (16 left retries with none)
PAGE_READS_PER_RUN = 12

# Pages not worth a read. Listing sites are huge (UrbanPro: 75,000 characters, mostly
# freelance tutors) and their search snippets already hold what we need; social sites
# return only a login wall. A run once spent all its reads on these and none on studios.
SKIP_DOMAINS = (
    "justdial.com", "urbanpro.com", "sulekha.com", "superprof.co.in", "lyfskills.com",
    "instagram.com", "facebook.com", "youtube.com", "google.com",
)
REFUSAL_PREFIX = "Tool refusal:"

_USED: dict[str, dict[str, int]] = {}
_ids = count(1)


def new_budget() -> str:
    budget_id = f"run-{next(_ids)}"
    _USED[budget_id] = {"searches": 0, "page_reads": 0}
    return budget_id


def budget_used(budget_id: str) -> dict[str, int]:
    return dict(_USED.get(budget_id, {}))


def _take(budget_id: str, kind: str, limit: int) -> bool:
    used = _USED.setdefault(budget_id, {"searches": 0, "page_reads": 0})
    if used[kind] >= limit:
        return False
    used[kind] += 1
    return True


def _domain(url: str) -> str:
    return urlparse(url.strip()).netloc.lower().removeprefix("www.").removeprefix("m.")


class BudgetedSearch(SerperDevTool):
    budget_id: str = "unbudgeted"
    limit: int = SEARCHES_PER_RUN

    def _run(self, **kwargs: Any) -> Any:
        if not _take(self.budget_id, "searches", self.limit):
            return f"{REFUSAL_PREFIX} the search budget for this run ({self.limit}) is used up. Answer with what you have."
        return super()._run(**kwargs)


class BusinessPageReader(ScrapeWebsiteTool):
    """ScrapeWebsiteTool that only opens businesses' own websites.

    Rules in code rather than in the prompt: the agent may still try to open a
    listing page, but the tool says no and explains why. Refusals cost no budget.
    """

    name: str = "Read a business website"
    description: str = (
        "Open a business's OWN website (for example its fees, packages, classes or contact page) "
        "and return the page text. Listing sites (Justdial, UrbanPro, Sulekha) and social media "
        "pages cannot be opened; use their search results instead."
    )
    budget_id: str = "unbudgeted"
    limit: int = PAGE_READS_PER_RUN

    def _run(self, **kwargs: Any) -> Any:
        url = kwargs.get("website_url") or ""
        if _domain(url).endswith(SKIP_DOMAINS):
            return (
                f"{REFUSAL_PREFIX} {url} is a listing or social page and is not opened. Use its search "
                "results, and open the business's own website for prices, timings and address."
            )
        if not _take(self.budget_id, "page_reads", self.limit):
            return f"{REFUSAL_PREFIX} the page-read budget for this run ({self.limit}) is used up. Answer with what you have."
        return super()._run(**kwargs)


def research_tools(budget_id: str, searches: int = SEARCHES_PER_RUN, page_reads: int = PAGE_READS_PER_RUN) -> list:
    # country="in" asks Google for Indian results (prices in rupees, local listings).
    return [
        BudgetedSearch(n_results=8, country="in", budget_id=budget_id, limit=searches),
        BusinessPageReader(budget_id=budget_id, limit=page_reads),
    ]
