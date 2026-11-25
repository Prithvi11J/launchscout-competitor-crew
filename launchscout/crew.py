"""Assemble agents and tasks into a Crew.

Process.sequential: tasks run in order, and a task listed in another's
`context` hands its (checked) output to it, like a team passing work along.
A crew is built per brief because the checks need the founder's city and
target customer; agent and task text still use {placeholders}, filled at kickoff.
"""

from crewai import Crew, Process

from launchscout.agents import market_researcher, review_analyst
from launchscout.brief import BusinessBrief
from launchscout.checks import ResearchGuardrail, llm_fit_judge
from launchscout.config import get_llm
from launchscout.review_checks import ReviewGuardrail
from launchscout.tasks import research_task, review_task


def build_crew(brief: BusinessBrief, llm=None, tools=None, judge=llm_fit_judge, with_reviews: bool = False) -> Crew:
    llm = llm or get_llm()
    researcher = market_researcher(llm=llm, tools=tools)
    research_guard = ResearchGuardrail(brief, llm=llm, judge=judge)
    research = research_task(researcher, research_guard.check)
    agents, tasks = [researcher], [research]

    if with_reviews:
        analyst = review_analyst(llm=llm, tools=tools)
        agents.append(analyst)
        tasks.append(review_task(analyst, ReviewGuardrail(research_guard).check, research))

    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        tracing=False,  # never upload run traces to CrewAI
    )
