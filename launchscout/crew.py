"""Assemble agents and tasks into a Crew.

Process.sequential: tasks run in order, and a task listed in another's
`context` hands its (checked) output to it, like a team passing work along.
A crew is built per brief because the checks need the founder's city and
target customer; agent and task text still use {placeholders}, filled at kickoff.

stages: 1 = research, 2 = + reviews, 3 = + strategy, 4 = + report (the full crew).
"""

from crewai import Crew, Process

from launchscout.agents import market_researcher, report_writer, review_analyst, strategy_analyst
from launchscout.brief import BusinessBrief
from launchscout.checks import ResearchGuardrail, llm_fit_judge
from launchscout.config import get_llm
from launchscout.report import ReportGuardrail
from launchscout.review_checks import ReviewGuardrail
from launchscout.strategy_checks import StrategyGuardrail
from launchscout.tasks import report_task, research_task, review_task, strategy_task


def build_crew(brief: BusinessBrief, llm=None, tools=None, judge=llm_fit_judge, stages: int = 4) -> Crew:
    llm = llm or get_llm()
    researcher = market_researcher(llm=llm, tools=tools)
    research_guard = ResearchGuardrail(brief, llm=llm, judge=judge)
    research = research_task(researcher, research_guard.check)
    agents, tasks = [researcher], [research]

    if stages >= 2:
        analyst = review_analyst(llm=llm, tools=tools)
        review_guard = ReviewGuardrail(research_guard)
        reviews = review_task(analyst, review_guard.check, research)
        agents.append(analyst)
        tasks.append(reviews)

    if stages >= 3:
        strategist = strategy_analyst(llm=llm)
        strategy_guard = StrategyGuardrail(research_guard, review_guard)
        strategy = strategy_task(strategist, strategy_guard.check, research, reviews)
        agents.append(strategist)
        tasks.append(strategy)

    if stages >= 4:
        writer = report_writer(llm=llm)
        agents.append(writer)
        tasks.append(report_task(writer, ReportGuardrail(research_guard, review_guard, strategy_guard).check,
                                 research, reviews, strategy))

    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        tracing=False,  # never upload run traces to CrewAI
    )
