"""The crew's tasks. Stage 1 has one: competitor research.

A task = description (the job, with {placeholders} from the brief),
expected_output (the exact format, so the result is checkable), the agent
that does it, and here also a Pydantic model and a guardrail that enforce
that format in code.
"""

from crewai import Agent, Task

from launchscout.checks import research_guardrail
from launchscout.schemas import MarketResearch


def research_task(agent: Agent) -> Task:
    return Task(
        description=(
            "A founder plans to launch: {idea}\n"
            "City: {city}\n"
            "Target customer: {target_customer}\n"
            "Competitors the founder already knows about: {known_competitors}\n\n"
            "Find 3 to 5 real businesses in {city} that compete for this customer. Include the known "
            "competitors if they are real. For each one, find its price(s), offers, sales channels and the "
            "area of the city it serves. Search listing sites, the businesses' own websites and their social "
            "media posts. Open a page with the scraper when a search snippet does not show the price.\n"
            "Separately, note any city-wide price ranges you find on listing or guide sites."
        ),
        expected_output=(
            "One JSON object with two keys:\n"
            "- competitors: 3 to 5 items. Each has name (the business, never a listing site), locality, "
            "offering, price_status ('published', 'on_enquiry' or 'not_found'), prices (each with label, "
            "amount_inr as a whole number, unit, and the source_url of the exact page showing that price; "
            "empty unless price_status is 'published'), channels, offers and source_urls.\n"
            "- market_price_context: city-wide ranges from listing sites, each with summary and source_url.\n"
            "At least 3 competitors must have a published price. Every URL must be one you actually saw in "
            "a search result or opened page."
        ),
        agent=agent,
        output_pydantic=MarketResearch,
        guardrail=research_guardrail,
        guardrail_max_retries=2,
    )
