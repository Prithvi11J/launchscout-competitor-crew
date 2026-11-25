"""Evidence checks: does each source and price really say what the agent claims?

"The URL was seen" only proves a link existed. Here we prove the claim:
  * a source counts for a business only if that page or search result names it;
  * a price counts only if the amount appears next to the business's name on
    the cited page (or anywhere on the business's own website).

Evidence comes from the agent's message history. Each tool call is an
assistant message with arguments (the query or URL), followed by a "tool"
message with the result, linked by tool_call_id. Search results are split
into one evidence unit per result, so a price in one result can't be credited
to a business that only appears in another.
"""

import ast
import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

# Where a business's price may appear, measured from a mention of its name. Listings and
# articles put the name first and the details after (lbb.in: price ~540 characters later),
# while a city-wide range usually sits before the list starts, so the window is lopsided.
BEFORE, AFTER = 100, 600
SCRAPE_PREFIX = "The following text is scraped website content:"
GENERIC_WORDS = {
    "dance", "dances", "dancing", "studio", "studios", "academy", "school", "company", "co", "fitness",
    "the", "and", "of", "with", "class", "classes", "centre", "center", "institute", "pvt", "ltd",
}


@dataclass
class Evidence:
    url: str  # normalised
    text: str  # normalised: lower case, punctuation removed except commas inside numbers
    kind: str  # "search" or "page"
    raw_url: str = ""  # as the agent saw it, for putting back into the report
    subject: str = ""  # for "review" and "place" units: the business the lookup was for


def normalize_url(url: str) -> str:
    parts = urlparse(url.strip())
    host = parts.netloc.lower().removeprefix("www.").removeprefix("m.")
    return f"{host}{parts.path.rstrip('/')}".lower()


def normalize_text(text: str) -> str:
    # Apostrophes vanish rather than becoming spaces: "Sandy's" and "Sandys" must match.
    text = re.sub(r"['’`]", "", text.lower()).replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9,]+", " ", text)).strip()


def _search_units(content: str) -> list[Evidence]:
    try:
        data = ast.literal_eval(content)
    except (ValueError, SyntaxError):
        return []
    units = []
    for item in data.get("organic", []) if isinstance(data, dict) else []:
        text = f"{item.get('title', '')} {item.get('snippet', '')}"
        link = item.get("link", "")
        units.append(Evidence(normalize_url(link), normalize_text(text), "search", link))
    return units


def _review_units(content: str) -> list[Evidence]:
    """Google reviews tool output: one "place" unit (rating, address) and one unit per review."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not data.get("found"):
        return []
    link, subject = data["link"], data["business_name"]
    place = f"{data.get('listing_name', '')} {data.get('address', '')} rating {data.get('rating')} from {data.get('rating_count')}"
    units = [Evidence(normalize_url(link), normalize_text(place), "place", link, subject)]
    units += [Evidence(normalize_url(link), normalize_text(r["text"]), "review", link, subject) for r in data.get("reviews", [])]
    return units


def extract_evidence(messages: list[dict] | None) -> list[Evidence]:
    """Turn an agent's message history into evidence units."""
    calls: dict[str, dict] = {}
    units: list[Evidence] = []
    for message in messages or []:
        m = dict(message)
        for call in m.get("tool_calls") or []:
            try:
                calls[call["id"]] = json.loads(call["function"]["arguments"] or "{}")
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
        if m.get("role") != "tool" or not isinstance(m.get("content"), str):
            continue
        content, args = m["content"], calls.get(m.get("tool_call_id", ""), {})
        if "usage limit" in content[:200].lower() or content.startswith("Tool refusal:"):
            continue  # a tool refusing to run is not evidence about the page it was asked for
        if "business_name" in args:
            units.extend(_review_units(content))
        elif "website_url" in args:
            page = content.removeprefix(SCRAPE_PREFIX)
            url = args["website_url"]
            units.append(Evidence(normalize_url(url), normalize_text(page), "page", url))
        else:
            units.extend(_search_units(content))
    return units


def _name_candidates(name: str) -> list[str]:
    """Ways a business name may appear: full name, as one word (an @handle or #hashtag),
    without trailing generic words, and its rarest word."""
    words = normalize_text(name).split()
    candidates = [" ".join(words), "".join(words)]
    trimmed = list(words)
    while len(trimmed) > 1 and trimmed[-1] in GENERIC_WORDS:
        trimmed.pop()
    distinctive = [w for w in words if w not in GENERIC_WORDS and len(w) >= 3]
    # A shortened name must keep a distinctive word. Bug found by hand: "Dance and Dance Studio"
    # shrank to just "dance", which matched every dance page on the internet.
    if any(w not in GENERIC_WORDS for w in trimmed):
        candidates.append(" ".join(trimmed))
    if distinctive:
        candidates.append(max(distinctive, key=len))
    return [c for c in dict.fromkeys(candidates) if c]


def mention_positions(text: str, name: str) -> list[int]:
    for candidate in _name_candidates(name):
        hits = [m.start() for m in re.finditer(rf"\b{re.escape(candidate)}\b", text)]
        if hits:
            return hits
    return []


def _amounts(text: str) -> set[int]:
    return {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text) if n.replace(",", "").isdigit()}


def owns_domain(url: str, name: str) -> bool:
    """True if the URL is on the business's own website, e.g. swingersdance.com for 'The Swingers Dance'."""
    label = url.split("/")[0].split(".")[0]
    squashed = re.sub(r"[^a-z0-9]", "", name.lower().replace("&", "and"))
    core = "".join(w for w in normalize_text(name).split() if w not in GENERIC_WORDS)
    if len(label) < 4 or label in GENERIC_WORDS:
        return False
    initials = "".join(w[0] for w in normalize_text(name).split() if w not in {"the", "and", "of"})
    if len(initials) >= 3 and label.startswith(initials):
        return True  # wsda.in is Winning Steps Dance Academy's own site
    return (label in squashed or (len(core) >= 4 and core in label))


def names_business(unit: Evidence, name: str) -> bool:
    return owns_domain(unit.url, name) or bool(mention_positions(unit.text, name))


# Words that make a number a price. Bug found by hand: raackdance.com says "4000 events
# performed", and that statistic "proved" a price the agent had copied from another studio.
PRICE_CUES = {
    "rs", "inr", "fee", "fees", "price", "prices", "pricing", "cost", "month", "monthly", "per", "class",
    "classes", "session", "sessions", "hour", "hr", "course", "package", "only", "just", "joining",
    "admission", "membership",
}
CUE_REACH = 30  # characters either side of the number


def _priced_amounts(text: str) -> set[int]:
    """Numbers that sit next to price wording."""
    found = set()
    for m in re.finditer(r"\d[\d,]*", text):
        digits = m.group().replace(",", "")
        if not digits.isdigit():
            continue
        nearby = text[max(0, m.start() - CUE_REACH) : m.end() + CUE_REACH].split()
        if PRICE_CUES.intersection(nearby):
            found.add(int(digits))
    return found


def price_grounded(unit: Evidence, name: str, amount: int) -> bool:
    if owns_domain(unit.url, name):
        return amount in _priced_amounts(unit.text)
    for pos in mention_positions(unit.text, name):
        window = unit.text[max(0, pos - BEFORE) : pos + AFTER]
        if amount in _priced_amounts(window):
            return True
    return False


def grounding_problems(research, evidence: list[Evidence]) -> list[str]:
    """Claims the evidence does not support, written as instructions for the agent."""
    by_url: dict[str, list[Evidence]] = {}
    for unit in evidence:
        by_url.setdefault(unit.url, []).append(unit)

    problems = []
    for c in research.competitors:
        for url in c.source_urls:
            units = by_url.get(normalize_url(url), [])
            if not units:
                problems.append(f"Source {url} for '{c.name}' was never in a search result or opened page. Remove it.")
            elif not any(names_business(u, c.name) for u in units):
                problems.append(
                    f"Source {url} does not mention '{c.name}' in any search result or page you saw. "
                    "Remove it, or replace it with a page that names this business."
                )
        for p in c.prices:
            units = by_url.get(normalize_url(p.source_url), [])
            if not units:
                problems.append(f"Price '{p.label}' for '{c.name}': {p.source_url} was never in a search result or opened page.")
            elif not any(price_grounded(u, c.name, p.amount_inr) for u in units):
                problems.append(
                    f"Price Rs {p.amount_inr} ('{p.label}') for '{c.name}' does not appear next to '{c.name}' on "
                    f"{p.source_url}. Use only prices shown for this business; city-wide ranges belong in market_price_context."
                )
    return problems


# Redirect and search-engine pages are evidence, but not links to hand a founder.
NOT_CITABLE = ("google.com", "bing.com")


def citable(url: str) -> bool:
    return not normalize_url(url).startswith(NOT_CITABLE)


# Old and new names of the same city, so "Madras" on an old page still counts for Chennai.
CITY_ALIASES = {
    "chennai": ["madras"], "bengaluru": ["bangalore"], "mumbai": ["bombay"], "kolkata": ["calcutta"],
    "gurugram": ["gurgaon"], "puducherry": ["pondicherry"], "thiruvananthapuram": ["trivandrum"],
    "kochi": ["cochin"], "coimbatore": ["kovai"], "mysuru": ["mysore"], "vadodara": ["baroda"],
}


def place_names(city: str, locality: str) -> list[str]:
    """Words that would place a business in the city: the city, its old names, and the
    localities the agent claims (only if a page names the business next to them, see below)."""
    key = normalize_text(city)
    names = [key, *CITY_ALIASES.get(key, [])]
    for part in re.split(r"[/,;&]| and ", locality.lower()):
        part = normalize_text(part)
        if len(part) >= 4 and part not in {"unknown", key, "india", "tamil nadu"}:
            names.append(part)
    return names


def located_in(unit: Evidence, name: str, places: list[str]) -> bool:
    """Does this evidence name the business AND a place in the city? A listing page's URL
    counts too: justdial.com/chennai/... places every business it lists in Chennai."""
    if not names_business(unit, name):
        return False
    haystack = f"{unit.url.replace('/', ' ').replace('-', ' ')} {unit.text}"
    return any(re.search(rf"\b{re.escape(p)}\b", haystack) for p in places)


def repair_claims(research, evidence: list[Evidence], city: str | None = None):
    """Fix in code what code can fix, and remove what no evidence supports.

    * a price shown for the business on a different page it saw: point to that page;
    * a price or a source no evidence supports: remove it;
    * a competitor left with no supported source: remove it;
    * with a city: a competitor no page places in that city (by its name or a claimed
      locality next to the business's name): remove it.
    Returns (repaired copy, notes). The agent is only sent back if the repaired answer
    breaks a rule (too few competitors or prices), which needs new research, not editing.
    """
    research = research.model_copy(deep=True)
    by_url: dict[str, list[Evidence]] = {}
    for unit in evidence:
        by_url.setdefault(unit.url, []).append(unit)
    notes: list[str] = []
    kept = []
    for c in research.competitors:
        sources = []
        for u in c.source_urls:
            if not citable(u):
                notes.append(f"Removed source {u[:60]}... for '{c.name}': a search-engine redirect, not a page a founder can open.")
            elif any(names_business(e, c.name) for e in by_url.get(normalize_url(u), [])):
                sources.append(u)
            else:
                notes.append(f"Removed source {u} for '{c.name}': it never names the business.")
        prices = []
        for p in c.prices:
            if p.amount_inr <= 0:
                notes.append(f"Removed price Rs {p.amount_inr} ('{p.label}') for '{c.name}': a free offer is not a price.")
                continue
            if citable(p.source_url) and any(
                price_grounded(e, c.name, p.amount_inr) for e in by_url.get(normalize_url(p.source_url), [])
            ):
                prices.append(p)
                continue
            other = next((e for e in evidence if citable(e.url) and price_grounded(e, c.name, p.amount_inr)), None)
            if other:
                new_url = other.raw_url or f"https://{other.url}"
                notes.append(f"Moved price Rs {p.amount_inr} for '{c.name}' to {new_url}, the page that shows it.")
                p.source_url = new_url
                prices.append(p)
            else:
                notes.append(f"Removed price Rs {p.amount_inr} ('{p.label}') for '{c.name}': no page shows it next to the business.")
        for p in prices:
            if p.source_url not in sources:
                sources.append(p.source_url)
        c.prices, c.source_urls = prices, sources
        if c.price_status == "published" and not prices:
            c.price_status = "not_found"
        if not sources:
            notes.append(f"Removed '{c.name}': no page you saw names it.")
        elif city and not any(located_in(e, c.name, place_names(city, c.locality)) for e in evidence):
            notes.append(
                f"Removed '{c.name}': no page you saw places it in {city} "
                f"(neither '{city}' nor its claimed locality '{c.locality}' appears next to its name)."
            )
        else:
            kept.append(c)
    research.competitors = kept
    return research, notes


def evidence_to_json(evidence: list[Evidence]) -> list[dict]:
    return [asdict(e) for e in evidence]


def evidence_from_json(items: list[dict]) -> list[Evidence]:
    return [Evidence(**item) for item in items]
