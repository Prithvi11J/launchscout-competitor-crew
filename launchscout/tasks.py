"""The crew's tasks. Stage 1 has one: competitor research.

A task = description (the job, with {placeholders} from the brief),
expected_output (the exact format, so the result is checkable), the agent
that does it, and here also a Pydantic model and a guardrail that enforce
that format in code.
"""

from crewai import Agent, Task

from launchscout.schemas import MarketResearch, ReviewResearch


def research_task(agent: Agent, guardrail) -> Task:
    return Task(
        description=(
            "A founder plans to launch: {idea}\n"
            "City: {city}\n"
            "Target customer: {target_customer}\n"
            "Competitors the founder already knows about: {known_competitors}\n\n"
            "Find 3 to 5 real businesses in {city} that are DIRECT competitors: they sell the same kind of "
            "thing to {target_customer}, as an ongoing offer. They must be businesses with their own venue or "
            "brand, not individual freelancers or home tutors. Include the known competitors if they are real. "
            "For each one, find its price(s), offers, sales channels, the area of the city it serves, and when "
            "customers can use it (schedule). Work in two steps: first use search (listing sites, social "
            "posts) to find candidate businesses in {city}; then, for each candidate, find its OWN website "
            "and open its fees, packages, classes or contact page. A business's own page is the best evidence "
            "for its price, schedule and address, because it names the business, shows the price next to it "
            "and usually says which city it is in. Use at least two different websites as sources.\n"
            "Separately, note any city-wide price ranges you find on listing or guide sites."
        ),
        expected_output=(
            "One JSON object with two keys:\n"
            "- competitors: 3 to 5 items. Each has name (the business, never a listing site), locality, "
            "offering, schedule ('unknown' if not found), fit_reason (one sentence on why it competes for the "
            "target customer), price_status ('published', 'on_enquiry' or 'not_found'), prices (each with "
            "label, amount_inr as a whole number, unit, and the source_url of the exact page showing that "
            "price; empty unless price_status is 'published'), channels, offers and source_urls.\n"
            "- market_price_context: city-wide ranges from listing sites, each with summary and source_url.\n"
            "At least 3 competitors must have a published price. No more than 2 competitors may rely on a "
            "single website. Every URL must be one you actually saw in a search result or opened page."
        ),
        agent=agent,
        output_pydantic=MarketResearch,
        guardrail=guardrail,
        guardrail_max_retries=2,
    )


def review_task(agent: Agent, guardrail, research: Task) -> Task:
    return Task(
        description=(
            "The Market Researcher's answer (in your context) lists competitors in {city} for this idea: {idea}. "
            "Target customer: {target_customer}.\n"
            "For EACH competitor in that list, use the Google reviews tool (its name and {city}). From the "
            "reviews it returns, report what customers like and what they complain about, and the listing's "
            "rating and number of ratings. Look for repeated themes, especially in the low-star reviews."
        ),
        expected_output=(
            "One JSON object with key competitors: one item per researched competitor, using exactly the same "
            "names. Each has competitor, rating (number or null), rating_count (number or null), "
            "rating_source_url, likes and complaints. Each like or complaint has point (your one-line summary), "
            "quote (5 to 25 words copied exactly from one Google review) and source_url (the listing link the "
            "tool returned; also use it as rating_source_url). At least 3 competitors need a like or complaint, and at least 2 complaints in total."
        ),
        agent=agent,
        context=[research],
        output_pydantic=ReviewResearch,
        guardrail=guardrail,
        guardrail_max_retries=2,
    )
