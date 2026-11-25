"""The web tools agents can choose to use.

`max_usage_count` caps how often one agent may call a tool in a run. Each
Serper search costs a credit, so this is the budget line, not a nicety.
"""

from crewai_tools import ScrapeWebsiteTool, SerperDevTool

SEARCHES_PER_AGENT = 8
SCRAPES_PER_AGENT = 4


def web_search() -> SerperDevTool:
    # country="in" asks Google for Indian results (prices in rupees, local listings).
    return SerperDevTool(n_results=8, country="in", max_usage_count=SEARCHES_PER_AGENT)


def page_reader() -> ScrapeWebsiteTool:
    return ScrapeWebsiteTool(max_usage_count=SCRAPES_PER_AGENT)
