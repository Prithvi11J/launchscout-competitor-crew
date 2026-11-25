"""Rules in code: validate what an agent hands back.

`research_guardrail` is attached to the research task. CrewAI calls it with the
agent's answer; if it returns (False, "reason"), CrewAI sends the reason back to
the agent and makes it try again (up to `guardrail_max_retries`). The agent
learns exactly what was wrong instead of us hoping the prompt was clear enough.
"""

import json
import re
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from launchscout.schemas import MarketResearch

MIN_COMPETITORS = 3
MAX_COMPETITORS = 6
MIN_PRICED = 3

# Listing and directory sites are sources, not competitors.
LISTING_SITES = {
    "justdial", "urbanpro", "superprof", "lyfskills", "sulekha", "5bestincity", "threebestrated",
    "planmyplay", "wedmegood", "google", "facebook", "instagram", "reddit", "youtube", "quora",
}


def parse_research(raw: str) -> MarketResearch:
    """Read the agent's JSON answer, tolerating ```json fences around it."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{") and "{" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    return MarketResearch.model_validate(json.loads(text))


def is_url(value: str) -> bool:
    parts = urlparse(value.strip())
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _looks_like_listing_site(name: str) -> bool:
    squashed = re.sub(r"[^a-z0-9]", "", name.lower())
    return any(site == squashed or squashed.startswith(site) for site in LISTING_SITES)


def find_problems(research: MarketResearch) -> list[str]:
    """Everything that breaks the brief's rules, as plain sentences the agent can act on."""
    problems: list[str] = []
    comps = research.competitors

    if not MIN_COMPETITORS <= len(comps) <= MAX_COMPETITORS:
        problems.append(f"List {MIN_COMPETITORS} to {MAX_COMPETITORS} competitors; you listed {len(comps)}.")

    names = [c.name.strip().lower() for c in comps]
    if len(set(names)) != len(names):
        problems.append("Each competitor must appear only once.")

    for c in comps:
        if _looks_like_listing_site(c.name):
            problems.append(f"'{c.name}' is a listing site, not a competitor. Use it as a source or as market price context.")
        if not any(is_url(u) for u in c.source_urls):
            problems.append(f"'{c.name}' has no source URL.")
        if c.price_status == "published" and not c.prices:
            problems.append(f"'{c.name}' is marked 'published' but has no prices. Add them or change price_status.")
        if c.price_status != "published" and c.prices:
            problems.append(f"'{c.name}' has prices but price_status is '{c.price_status}'. Use 'published'.")
        for p in c.prices:
            if not is_url(p.source_url):
                problems.append(f"Price '{p.label}' for '{c.name}' needs the URL of the page that shows it.")
            if not 0 < p.amount_inr < 200_000:
                problems.append(f"Price '{p.label}' for '{c.name}' is Rs {p.amount_inr}, which is not a believable amount.")

    priced = [c for c in comps if c.price_status == "published" and c.prices]
    if len(priced) < MIN_PRICED:
        problems.append(
            f"At least {MIN_PRICED} competitors need a published price with its source page; only {len(priced)} have one. "
            "Search for more competitors or for their fee pages, Instagram posts or listing pages."
        )
    return problems


def research_guardrail(task_output: Any) -> tuple[bool, Any]:
    """CrewAI guardrail: (True, validated model) or (False, what to fix)."""
    try:
        research = parse_research(task_output.raw)
    except (json.JSONDecodeError, ValueError, ValidationError) as err:
        return False, f"Your answer must be one JSON object matching the MarketResearch schema. Error: {err}"

    problems = find_problems(research)
    if problems:
        return False, "Fix these problems and answer again:\n- " + "\n- ".join(problems)
    return True, drop_duplicate_prices(research)


def drop_duplicate_prices(research: MarketResearch) -> MarketResearch:
    """The same price seen on two pages is one price; keep the first source.

    Cleaning in code instead of asking the model to "avoid duplicates":
    it is cheaper, and it cannot be forgotten.
    """
    for c in research.competitors:
        unique, keys = [], set()
        for p in c.prices:
            key = (p.amount_inr, p.unit, p.label.strip().lower())
            if key not in keys:
                keys.add(key)
                unique.append(p)
        c.prices = unique
    return research


def urls_seen_in_tool_results(messages: list[dict] | None) -> set[str]:
    """Every URL that appeared in text the agent received, so we can tell found links from invented ones."""
    seen: set[str] = set()
    for message in messages or []:
        if message.get("role") == "assistant":
            continue  # the agent's own words prove nothing
        content = message.get("content")
        text = content if isinstance(content, str) else json.dumps(content, default=str)
        seen.update(u.rstrip("/.,)'\"") for u in re.findall(r"https?://[^\s'\"<>\]\\]+", text))
    return seen


def unverified_urls(research: MarketResearch, seen: set[str]) -> list[str]:
    """Source URLs the agent cites that never appeared in a search or scrape result."""
    cited = {u for c in research.competitors for u in c.source_urls}
    cited |= {p.source_url for c in research.competitors for p in c.prices}
    return sorted(u for u in cited if u.rstrip("/") not in seen)
