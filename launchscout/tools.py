"""The web tools agents can choose to use, with a budget per run.

Each Serper search costs a credit, so the budget is a cost line, not a nicety.
CrewAI's own `max_usage_count` turned out not to hold across guardrail retries
(CrewAI rebuilds its internal tool copies on each attempt: one run made 15 page
reads with a cap of 8), so the budget is enforced here, inside `_run`, where
every real call has to pass. Counts live in a registry keyed by a budget id,
so they survive any copying CrewAI does.
"""

from itertools import count
from typing import Any
from urllib.parse import urlparse

from crewai_tools import ScrapeWebsiteTool, SerperDevTool

SEARCHES_PER_RUN = 24  # whole run, including guardrail retries: at most 24 Serper credits (16 left retries with none)
PAGE_READS_PER_RUN = 12

# Pages not worth a read. Listing sites are huge (UrbanPro: 75,000 characters, mostly
# freelance tutors) and their search snippets already hold what we need; social sites
# return only a login wall. A run once spent all its reads on these and none on studios.
SKIP_DOMAINS = (
    "justdial.com", "urbanpro.com", "sulekha.com", "superprof.co.in", "lyfskills.com",
    "instagram.com", "facebook.com", "youtube.com", "google.com",
)
REFUSAL_PREFIX = "Tool refusal:"

_USED: dict[str, dict[str, int]] = {}
_ids = count(1)


def new_budget() -> str:
    budget_id = f"run-{next(_ids)}"
    _USED[budget_id] = {"searches": 0, "page_reads": 0}
    return budget_id


def budget_used(budget_id: str) -> dict[str, int]:
    return dict(_USED.get(budget_id, {}))


def _take(budget_id: str, kind: str, limit: int) -> bool:
    used = _USED.setdefault(budget_id, {})
    used.setdefault(kind, 0)
    if used[kind] >= limit:
        return False
    used[kind] += 1
    return True


def _domain(url: str) -> str:
    return urlparse(url.strip()).netloc.lower().removeprefix("www.").removeprefix("m.")


class BudgetedSearch(SerperDevTool):
    budget_id: str = "unbudgeted"
    limit: int = SEARCHES_PER_RUN

    def _run(self, **kwargs: Any) -> Any:
        if not _take(self.budget_id, "searches", self.limit):
            return f"{REFUSAL_PREFIX} the search budget for this run ({self.limit}) is used up. Answer with what you have."
        return super()._run(**kwargs)


class BusinessPageReader(ScrapeWebsiteTool):
    """ScrapeWebsiteTool that only opens businesses' own websites.

    Rules in code rather than in the prompt: the agent may still try to open a
    listing page, but the tool says no and explains why. Refusals cost no budget.
    """

    name: str = "Read a business website"
    description: str = (
        "Open a business's OWN website (for example its fees, packages, classes or contact page) "
        "and return the page text. Listing sites (Justdial, UrbanPro, Sulekha) and social media "
        "pages cannot be opened; use their search results instead."
    )
    budget_id: str = "unbudgeted"
    limit: int = PAGE_READS_PER_RUN

    def _run(self, **kwargs: Any) -> Any:
        url = kwargs.get("website_url") or ""
        if _domain(url).endswith(SKIP_DOMAINS):
            return (
                f"{REFUSAL_PREFIX} {url} is a listing or social page and is not opened. Use its search "
                "results, and open the business's own website for prices, timings and address."
            )
        if not _take(self.budget_id, "page_reads", self.limit):
            return f"{REFUSAL_PREFIX} the page-read budget for this run ({self.limit}) is used up. Answer with what you have."
        return super()._run(**kwargs)


def research_tools(budget_id: str, searches: int = SEARCHES_PER_RUN, page_reads: int = PAGE_READS_PER_RUN) -> list:
    # country="in" asks Google for Indian results (prices in rupees, local listings).
    return [
        BudgetedSearch(n_results=8, country="in", budget_id=budget_id, limit=searches),
        BusinessPageReader(budget_id=budget_id, limit=page_reads),
    ]


# --- Google reviews via Serper's Maps endpoints ------------------------------------------
# One lookup = /maps (3 credits) + /reviews most relevant (1) + /reviews lowest rated (1).
REVIEW_LOOKUPS_PER_RUN = 6
REVIEW_MAX_AGE_YEARS = 3  # a complaint from 2018 says little about the studio today
REVIEW_MIN_WORDS = 5  # drops empty reviews and spam such as a lone name or phone number
MATCH_THRESHOLD = 0.7

import json as _json  # noqa: E402
import os as _os  # noqa: E402
import urllib.request as _request  # noqa: E402
from datetime import datetime as _datetime, timezone as _timezone  # noqa: E402
from difflib import SequenceMatcher as _SequenceMatcher  # noqa: E402

from crewai.tools import BaseTool  # noqa: E402
from pydantic import BaseModel as _BaseModel, Field as _Field  # noqa: E402

from launchscout.evidence import CITY_ALIASES, GENERIC_WORDS, normalize_text  # noqa: E402


class _ReviewArgs(_BaseModel):
    business_name: str = _Field(description="Exact competitor name from the research")
    city: str = _Field(description="The founder's city")


def _serper(path: str, body: dict) -> dict:
    request = _request.Request(
        f"https://google.serper.dev/{path}",
        data=_json.dumps(body).encode(),
        headers={"X-API-KEY": _os.environ.get("SERPER_API_KEY", ""), "Content-Type": "application/json"},
    )
    with _request.urlopen(request, timeout=30) as response:
        return _json.load(response)


def _core(name: str) -> str:
    """Name without leading 'the' and trailing type words: 'Dance and Dance Studio' -> 'dance and dance'."""
    words = normalize_text(name).split()
    while words and words[0] == "the":
        words.pop(0)
    while len(words) > 1 and words[-1] in GENERIC_WORDS:
        words.pop()
    return " ".join(words)


def pick_place(places: list[dict], name: str, city: str) -> dict | None:
    """Code, not the model, decides which Maps result is the competitor: in the city, closest name."""
    city_words = [normalize_text(city), *CITY_ALIASES.get(normalize_text(city), [])]
    best, best_score = None, 0.0
    for place in places:
        address = normalize_text(place.get("address", ""))
        if not any(c in address for c in city_words):
            continue
        score = _SequenceMatcher(None, _core(name), _core(place.get("title", ""))).ratio()
        if score > best_score:
            best, best_score = place, score
    return best if best_score >= MATCH_THRESHOLD else None


def _recent_and_real(review: dict, now: _datetime) -> bool:
    if len((review.get("snippet") or "").split()) < REVIEW_MIN_WORDS:
        return False
    try:
        written = _datetime.fromisoformat(review["isoDate"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False
    return (now - written).days <= REVIEW_MAX_AGE_YEARS * 365


class GoogleReviewsTool(BaseTool):
    """Look up a business on Google Maps and return its rating, address and recent reviews."""

    name: str = "Google reviews"
    description: str = (
        "Give a business name and city. Returns its Google Maps listing (name, address, rating, number of "
        "ratings, link) and recent customer reviews, including the lowest-rated ones. Quote reviews from here."
    )
    args_schema: type[_BaseModel] = _ReviewArgs
    budget_id: str = "unbudgeted"
    limit: int = REVIEW_LOOKUPS_PER_RUN

    def _run(self, business_name: str, city: str) -> str:
        if not _take(self.budget_id, "review_lookups", self.limit):
            return f"{REFUSAL_PREFIX} the review-lookup budget for this run ({self.limit}) is used up."
        place = pick_place(_serper("maps", {"q": f"{business_name} {city}", "gl": "in"}).get("places", []), business_name, city)
        if place is None:
            return _json.dumps({"business_name": business_name, "found": False,
                                "note": f"No Google Maps listing in {city} matches this name."})
        now = _datetime.now(_timezone.utc)
        reviews, seen = [], set()
        for sort in ("mostRelevant", "lowestRating"):
            for review in _serper("reviews", {"cid": place["cid"], "gl": "in", "sortBy": sort}).get("reviews", []):
                if review.get("id") not in seen and _recent_and_real(review, now):
                    seen.add(review.get("id"))
                    reviews.append({"stars": review.get("rating"), "date": review.get("date"), "text": review["snippet"]})
        return _json.dumps({
            "business_name": business_name,
            "found": True,
            "listing_name": place.get("title"),
            "address": place.get("address"),
            "rating": place.get("rating"),
            "rating_count": place.get("ratingCount"),
            "link": f"https://maps.google.com/?cid={place['cid']}",
            "reviews": reviews,
        }, ensure_ascii=False)


def review_tools(budget_id: str) -> list:
    return [GoogleReviewsTool(budget_id=budget_id)]
