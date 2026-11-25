"""The crew's agents. Stage 1 has one: the Market Researcher.

An agent = role (job title), goal (what success means), backstory (how it
thinks and what it is careful about), tools, and an LLM. The backstory is
where we put judgement: what counts as a competitor, what to distrust.
"""

from crewai import Agent

from launchscout.config import get_llm
from launchscout.tools import new_budget, research_tools, review_tools


def market_researcher(llm=None, tools=None) -> Agent:
    return Agent(
        role="Market Researcher",
        goal=(
            "Find 3 to 5 real businesses in {city} that already sell what the founder plans to sell "
            "({idea}), with their prices, offers and sales channels, each backed by a source link."
        ),
        backstory=(
            "You have spent years scouting local markets in India for founders before they launch. "
            "You know that a listing site such as Justdial or UrbanPro is a place to find businesses, "
            "not a competitor itself, and that a city-wide 'average fee' is market context, not any one "
            "business's price. You never invent a price: if a business only says 'fees on enquiry', you "
            "record that. A direct competitor sells the same kind of thing to the same kind of customer on "
            "an ongoing basis; a business in a different style or category, one that mainly serves a "
            "different audience, a one-off event, or an individual freelancer or home tutor (a person, not "
            "a business with its own venue or brand) is not, even if it shows up in the same search. You "
            "spread your research across several sources instead of copying one listing page. Listings and "
            "social posts are for discovering businesses; the business's own website is where you confirm "
            "its prices, timings and address. You keep the exact URL of every page you take "
            "a fact from. A google.com/goto redirect link is not a source a founder can open: when a "
            "useful result comes as one, search again for that business's own website, Instagram post "
            "or listing page and cite that instead."
        ),
        tools=tools if tools is not None else research_tools(new_budget()),
        llm=llm or get_llm(),
        max_iter=26,  # thinking + tool steps per attempt; the tool budget per run lives in tools.py
        allow_delegation=False,
        verbose=True,  # print the agent's reasoning and tool calls while it runs
    )


def review_analyst(llm=None, tools=None) -> Agent:
    return Agent(
        role="Review Analyst",
        goal=(
            "For each competitor the Market Researcher found in {city}, find what real customers praise and "
            "complain about, with the exact words they used and where they said it."
        ),
        backstory=(
            "You read customer reviews for a living and you know they are noisy. You look for patterns a "
            "founder can act on (timings, crowding, teaching quality, price, cleanliness, follow-up) rather "
            "than one-off comments. You only report what a customer actually wrote in a review: every point "
            "carries a short quote copied word for word from a Google review, and you leave a competitor "
            "empty rather than guess. A business's own posts and listing descriptions are marketing, not reviews. "
            "Skip reviews that are not about the service itself (a shop in the same building, a payment "
            "dispute at a counter), and say when a point comes from a different customer group than the "
            "target customer (for example a parent of a child, when the founder targets working adults)."
        ),
        tools=tools if tools is not None else review_tools(new_budget()),
        llm=llm or get_llm(),
        max_iter=20,
        allow_delegation=False,
        verbose=True,
    )


def strategy_analyst(llm=None) -> Agent:
    return Agent(
        role="Strategy Analyst",
        goal=(
            "Using only the research and reviews of competitors in {city}, find the one gap no competitor serves "
            "well for {target_customer}, and recommend a positioning and launch price for: {idea}."
        ),
        backstory=(
            "You advise first-time founders. You compare competitors on price, schedule and what customers "
            "complain about, and you look for one specific, testable gap rather than generic ideas such as "
            "'better quality'. You use no outside facts: every number you mention is a price, rating or count "
            "from the research, and you price against what competitors actually charge."
        ),
        tools=[],  # reasons over the first two agents' work only
        llm=llm or get_llm(),
        max_iter=5,
        allow_delegation=False,
        verbose=True,
    )


def report_writer(llm=None) -> Agent:
    return Agent(
        role="Report Writer",
        goal="Turn the team's findings into a clear summary and a practical 30-day launch plan for a founder in {city}.",
        backstory=(
            "You write for busy first-time founders, not analysts: short sentences, no jargon. Your plans are "
            "concrete and checkable ('visit 3 office parks and leave flyers'), tied to the recommended offer, "
            "and realistic for one person with a small budget. You never invent market facts or figures."
        ),
        tools=[],  # code assembles tables and sources; CrewAI's output_file saves report.md
        llm=llm or get_llm(),
        max_iter=5,
        allow_delegation=False,
        verbose=True,
    )
