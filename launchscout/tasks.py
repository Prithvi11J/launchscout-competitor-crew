"""The crew's tasks. Stage 1 has one: competitor research.

A task = description (the job, with {placeholders} from the brief),
expected_output (the exact format, so the result is checkable), the agent
that does it, and here also a Pydantic model and a guardrail that enforce
that format in code.
"""

from crewai import Agent, Task

from launchscout.schemas import MarketResearch, ReviewResearch, StrategyAnalysis


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


def strategy_task(agent: Agent, guardrail, research: Task, reviews: Task) -> Task:
    return Task(
        description=(
            "Your context holds the checked competitor research (prices, schedules, channels) and customer "
            "reviews for {city}. The founder plans: {idea}, for {target_customer}.\n"
            "Compare the competitors. Find the single biggest gap: something the target customer wants that "
            "no competitor offers well, shown by prices, schedules, missing published prices, or repeated "
            "complaints. Then recommend a positioning line and a launch price."
        ),
        expected_output=(
            "One JSON object with: market_gap (2 to 3 sentences), gap_evidence (list of competitor names, "
            "exactly as in the research, whose data shows the gap), positioning (one poster-style line that "
            "includes the price), recommended_price_inr (whole number), price_unit ('per month', 'per class', "
            "'per hour', 'per course' or 'other') and price_reason (1 to 2 sentences comparing with competitors' "
            "real prices). Mention no number that is not in the research or reviews, except your own price."
        ),
        agent=agent,
        context=[research, reviews],
        output_pydantic=StrategyAnalysis,
        guardrail=guardrail,
        guardrail_max_retries=2,
    )


REPORT_FILE = "outputs/report.md"


def report_task(agent: Agent, guardrail, research: Task, reviews: Task, strategy: Task) -> Task:
    # No output_pydantic: the guardrail turns the plan into the full markdown report,
    # and CrewAI saves the task's final output to output_file.
    return Task(
        description=(
            "Your context holds the checked competitor research, customer reviews and the Strategy Analyst's gap, "
            "positioning and price for: {idea} in {city}, for {target_customer}.\n"
            "Write (1) a 2 to 3 sentence summary for the founder and (2) a 30-day launch plan, week by week, "
            "that tests the recommended offer. Code adds the competitor table, complaints and sources."
        ),
        expected_output=(
            "One JSON object with: summary (2 to 3 sentences) and weeks (exactly 4 items: week 1 to 4, each "
            "with focus and 2 to 4 concrete actions). Use no price or figure that is not in your context; small "
            "targets up to 100 are fine, such as 'run 2 trial classes' or 'collect 50 reviews'."
        ),
        agent=agent,
        context=[research, reviews, strategy],
        guardrail=guardrail,
        guardrail_max_retries=2,
        output_file=REPORT_FILE,
        create_directory=True,
    )
