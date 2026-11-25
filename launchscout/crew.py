"""Assemble agents and tasks into a Crew.

Stage 1: a one-agent, one-task crew. Later stages add the Review Analyst,
Strategy Analyst and Report Writer; with Process.sequential each task gets
the earlier tasks' output as context.

A crew is built per brief because the fit check needs to know the founder's
target customer. The agent and task text still use {placeholders}, filled at
kickoff, so no code changes are needed for a new idea or city.
"""

from crewai import Crew, Process

from launchscout.agents import market_researcher
from launchscout.brief import BusinessBrief
from launchscout.checks import ResearchGuardrail, llm_fit_judge
from launchscout.config import get_llm
from launchscout.tasks import research_task


def build_crew(brief: BusinessBrief, llm=None, tools=None, judge=llm_fit_judge) -> Crew:
    llm = llm or get_llm()
    researcher = market_researcher(llm=llm, tools=tools)
    guardrail = ResearchGuardrail(brief, llm=llm, judge=judge)
    return Crew(
        agents=[researcher],
        tasks=[research_task(researcher, guardrail.check)],
        process=Process.sequential,
        verbose=True,
        tracing=False,  # never upload run traces to CrewAI
    )
