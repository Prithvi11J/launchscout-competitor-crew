"""The evidence trail: for every price, rating, like and complaint, the snippet that proves it.

Built in code from the evidence the checks already used, so a founder (or a reviewer of
this project) can click any number in the report and see where it came from.
"""

import re

from launchscout.evidence import Evidence, normalize_text, normalize_url, owns_domain, price_grounded

EXCERPT = 300


def _page_excerpt(unit: Evidence, amount: int) -> str:
    """Pages are long: show the words around the amount."""
    pattern = rf"\b({amount:,}|{amount})\b"
    match = re.search(pattern, unit.text)
    if not match:
        return unit.text[:EXCERPT]
    start = max(0, match.start() - 160)
    return ("..." if start else "") + unit.text[start : match.end() + 100] + "..."


def _excerpt(unit: Evidence, amount: int | None = None) -> str:
    if unit.raw:
        return unit.raw[:EXCERPT]
    return _page_excerpt(unit, amount) if amount is not None else unit.text[:EXCERPT]


def build_trail(research, reviews, research_evidence: list[Evidence], review_evidence: list[Evidence]) -> list[dict]:
    items: list[dict] = []
    for c in research.competitors:
        for p in c.prices:
            key = normalize_url(p.source_url)
            unit = next((e for e in research_evidence if e.url == key and price_grounded(e, c.name, p.amount_inr)), None)
            items.append({
                "competitor": c.name, "kind": "price",
                "claim": f"Rs {p.amount_inr:,} {p.unit} ({p.label})",
                "source_url": p.source_url,
                "excerpt": _excerpt(unit, p.amount_inr) if unit else "",
                "from": "business's own website" if owns_domain(key, c.name) else (unit.kind if unit else ""),
            })

    for r in reviews.competitors if reviews else []:
        subject = normalize_text(r.competitor)
        mine = [e for e in review_evidence if normalize_text(e.subject) == subject]
        if r.rating is not None:
            place = next((e for e in mine if e.kind == "place"), None)
            items.append({"competitor": r.competitor, "kind": "rating", "claim": f"Google rating {r.rating} ({r.rating_count} ratings)",
                          "source_url": r.rating_source_url, "excerpt": place.raw if place else "", "from": "Google Maps listing"})
        for kind, points in (("like", r.likes), ("complaint", r.complaints)):
            for point in points:
                quote = normalize_text(point.quote)
                review = next((e for e in mine if e.kind == "review" and quote in e.text), None)
                items.append({"competitor": r.competitor, "kind": kind, "claim": point.point, "source_url": point.source_url,
                              "excerpt": review.raw if review else point.quote, "from": "Google review"})
    return items
