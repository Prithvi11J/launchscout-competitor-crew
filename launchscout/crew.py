"""Assemble agents and tasks into a Crew.

Stage 1: a one-agent, one-task crew. Later stages add the Review Analyst,
Strategy Analyst and Report Writer; with Process.sequential each task gets
the earlier tasks' output as context.
"""

from crewai import Crew, Process

from launchscout.agents import market_researcher
from launchscout.tasks import research_task


def build_crew(llm=None, tools=None) -> Crew:
    researcher = market_researcher(llm=llm, tools=tools)
    return Crew(
        agents=[researcher],
        tasks=[research_task(researcher)],
        process=Process.sequential,
        verbose=True,
        tracing=False,  # never upload run traces to CrewAI
    )
