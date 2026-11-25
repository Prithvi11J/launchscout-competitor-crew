"""The crew's agents. Stage 1 has one: the Market Researcher.

An agent = role (job title), goal (what success means), backstory (how it
thinks and what it is careful about), tools, and an LLM. The backstory is
where we put judgement: what counts as a competitor, what to distrust.
"""

from crewai import Agent

from launchscout.config import get_llm
from launchscout.tools import page_reader, web_search


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
            "spread your research across several sources instead of copying one listing page, you prefer "
            "the business's own pages and recent posts, and you keep the exact URL of every page you take "
            "a fact from. A google.com/goto redirect link is not a source a founder can open: when a "
            "useful result comes as one, search again for that business's own website, Instagram post "
            "or listing page and cite that instead."
        ),
        tools=tools if tools is not None else [web_search(), page_reader()],
        llm=llm or get_llm(),
        max_iter=22,  # thinking + tool steps before it must answer; must exceed the 12 + 4 tool budget
        allow_delegation=False,
        verbose=True,  # print the agent's reasoning and tool calls while it runs
    )
