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

from launchscout.evidence import GENERIC_WORDS, Evidence, extract_evidence, normalize_text, repair_claims
from launchscout.schemas import FitVerdict, MarketResearch

MIN_COMPETITORS = 3
MAX_COMPETITORS = 6
MIN_PRICED = 3
MAX_FROM_ONE_SITE = 2

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


def domain(url: str) -> str:
    host = urlparse(url.strip()).netloc.lower()
    return host.removeprefix("www.").removeprefix("m.")


def _looks_like_listing_site(name: str) -> bool:
    squashed = re.sub(r"[^a-z0-9]", "", name.lower())
    return any(site == squashed or squashed.startswith(site) for site in LISTING_SITES)


def has_class_price(c) -> bool:
    """A joining fee alone doesn't tell a founder what the service costs, so it doesn't count."""
    return c.price_status == "published" and any(p.unit != "joining fee" for p in c.prices)


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

        if not c.fit_reason.strip():
            problems.append(f"'{c.name}' needs a fit_reason: why it competes for the target customer.")

    # Variety: one listing page must not supply most of the market.
    per_domain: dict[str, list[str]] = {}
    for c in comps:
        domains = {domain(u) for u in c.source_urls if is_url(u)}
        if len(domains) == 1:
            per_domain.setdefault(domains.pop(), []).append(c.name)
    for site, names in per_domain.items():
        if len(names) > MAX_FROM_ONE_SITE:
            problems.append(
                f"{len(names)} competitors ({', '.join(names)}) come only from {site}. At most "
                f"{MAX_FROM_ONE_SITE} may rely on one website; confirm others from a second source or find different ones."
            )

    priced = [c for c in comps if has_class_price(c)]
    if len(priced) < MIN_PRICED:
        problems.append(
            f"At least {MIN_PRICED} competitors need a published price (not just a joining fee) with its source page; "
            f"only {len(priced)} have one. Search for more competitors or for their fee pages, Instagram posts or listing pages."
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


FIT_PROMPT = """A founder plans to launch: {idea}
City: {city}
Target customer: {target_customer}

For each business below, decide whether it is a DIRECT competitor: it sells the same kind of
product or service, to roughly the same customer, as an ongoing offer in that city.
Not direct: mainly a different category or style, mainly a different audience (for example only
children when the target is adults), a one-off event or workshop, a listing site, outside the city,
or an individual freelancer or home tutor (a person teaching on their own rather than a business
with its own venue or brand).
Judge only from the facts given. If the facts are thin but plausible, count it as direct.

Businesses:
{businesses}"""


def llm_fit_judge(brief, research: MarketResearch, llm) -> FitVerdict:
    """Ask the LLM, with the founder's brief in hand, which competitors really compete."""
    lines = [
        f"- {c.name} (locality: {c.locality}): offers {c.offering}; schedule: {c.schedule}; "
        f"prices: {', '.join(p.label for p in c.prices) or c.price_status}; claimed fit: {c.fit_reason}"
        for c in research.competitors
    ]
    prompt = FIT_PROMPT.format(**brief.to_inputs(), businesses="\n".join(lines))
    answer = llm.call(prompt, response_model=FitVerdict)
    return answer if isinstance(answer, FitVerdict) else FitVerdict.model_validate_json(str(answer))


class ResearchGuardrail:
    """One guardrail that runs every check, cheapest first.

    1. Evidence repair (free): drop sources that never name the business, move a price to
       the page that really shows it, drop prices no page supports. Evidence is collected
       from every attempt, because a retry may not repeat the searches it already did.
    2. Code rules on what is left (free, exact): counts, prices, URLs, source variety, duplicates.
    3. Fit judge (one small LLM call): does each business really compete for THIS customer?
       Code can't judge "a Bharatanatyam diploma school vs after-work Bollywood"; a model can,
       as long as it sees the founder's brief, which CrewAI's built-in text guardrail never does.

    Both live in one function on purpose: with a list of guardrails, a retry caused by the
    second one is not re-checked by the first.

    Give CrewAI the bound method `guard.check`, not the object: CrewAI reads a function
    guardrail's source code for its logs, and that only works for functions and methods.
    """

    def __init__(self, brief, llm=None, judge=llm_fit_judge):
        self.brief = brief
        self.llm = llm
        self.judge = judge
        self.verdicts: list[FitVerdict] = []  # one per attempt that reached the fit check
        self.evidence: list[Evidence] = []
        self.attempts: list[dict] = []  # which check stopped each attempt, for the run record
        self.last_research: MarketResearch | None = None  # kept so a failed run still has an answer to review
        self.dead_ends: dict[str, str] = {}  # businesses checked without a usable price, across attempts

    def _collect(self, messages) -> None:
        known = {(e.url, e.text) for e in self.evidence}
        for unit in extract_evidence(messages):
            if (unit.url, unit.text) not in known:
                known.add((unit.url, unit.text))
                self.evidence.append(unit)

    def _steering(self, repaired: MarketResearch, parsed: MarketResearch) -> str:
        """Point a retry at NEW businesses when prices are short.

        Seen in real runs: told only "find more priced competitors", the agent went back to
        the same studios and searched them again. Naming the dead ends (studios checked with
        no usable published price, across all attempts) sends the remaining budget elsewhere.
        """
        kept = {c.name for c in repaired.competitors}
        priced = [c.name for c in repaired.competitors if has_class_price(c)]
        if len(priced) >= MIN_PRICED:
            return ""
        for c in repaired.competitors:
            if not has_class_price(c):
                self.dead_ends.setdefault(c.name, "no published price found on any page you saw")
        for c in parsed.competitors:
            if c.name not in kept:
                self.dead_ends.setdefault(c.name, "no page you saw supports it")
        lines = "\n- ".join(f"{name}: {why}" for name, why in self.dead_ends.items() if name not in priced)
        keep = ", ".join(priced) or "none yet"
        return (
            f"\nAlready checked, do not spend searches on these again:\n- {lines}\n"
            f"Keep the priced ones ({keep}). Use your remaining searches to find NEW businesses in "
            f"{self.brief.city} that publish prices, for example on their own fees or packages page. "
            f"You may list up to {MAX_COMPETITORS} competitors."
        )

    def check(self, task_output: Any) -> tuple[bool, Any]:
        self._collect(getattr(task_output, "messages", None))
        try:
            parsed = parse_research(task_output.raw)
        except (json.JSONDecodeError, ValueError, ValidationError) as err:
            feedback = f"Your answer must be one JSON object matching the MarketResearch schema. Error: {err}"
            self.attempts.append({"stopped_by": "format", "feedback": feedback, "repairs": []})
            return False, feedback

        # Repair first, then judge what is left: unsupported claims are removed in code,
        # so the agent is only sent back when the remaining answer needs more research.
        value, repairs = repair_claims(parsed, self.evidence, city=self.brief.city)
        self.last_research = value
        problems = find_problems(value) + duplicate_problems(value)
        if problems:
            feedback = "Fix these problems and answer again:\n- " + "\n- ".join(problems)
            if repairs:
                feedback += "\nCode already removed or corrected these claims, which no page you saw supports:\n- " + "\n- ".join(repairs)
            feedback += self._steering(value, parsed)
            self.attempts.append({"stopped_by": "rules after repair", "feedback": feedback, "repairs": repairs})
            return False, feedback

        verdict = self.judge(self.brief, value, self.llm)
        self.verdicts.append(verdict)
        rejected = [j for j in verdict.judgements if not j.direct_competitor]
        if rejected:
            listed = "\n- ".join(f"{j.name}: {j.reason}" for j in rejected)
            self.attempts.append({"stopped_by": "fit check", "feedback": listed, "repairs": repairs})
            return False, (
                f"These are not direct competitors for '{self.brief.target_customer}' and must be replaced "
                f"by businesses that are (keep the other rules):\n- {listed}"
            )
        self.attempts.append({"stopped_by": None, "feedback": "passed", "repairs": repairs})
        return True, drop_duplicate_prices(value)


def _distinctive_words(name: str) -> frozenset[str]:
    return frozenset(w for w in normalize_text(name).split() if w not in GENERIC_WORDS)


def duplicate_problems(research: MarketResearch) -> list[str]:
    """The same business listed twice under two names (seen: 'Dance Studio Chennai' and
    'Chennai Dance and Dance Studio' with identical prices) inflates the competitor count."""
    problems = []
    comps = research.competitors
    for i, a in enumerate(comps):
        for b in comps[i + 1 :]:
            same_words = bool(_distinctive_words(a.name)) and _distinctive_words(a.name) == _distinctive_words(b.name)
            prices_a = sorted((p.amount_inr, p.unit) for p in a.prices)
            same_prices = len(prices_a) >= 2 and prices_a == sorted((p.amount_inr, p.unit) for p in b.prices)
            if same_words or same_prices:
                problems.append(
                    f"'{a.name}' and '{b.name}' look like the same business. List it once and find another competitor."
                )
    return problems


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
