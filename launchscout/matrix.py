"""The competitor comparison matrix, built in code from the checked research and reviews.

Numbers from code, words from the LLM: the Strategy Analyst reasons over this table,
and the report prints it as is, so no price or rating can be retyped wrongly.
"""

from launchscout.schemas import MarketResearch, ReviewResearch

PREFERRED_UNITS = ("per month", "per class", "per course", "per hour", "other")


def headline_price(competitor) -> dict | None:
    """One comparable price per competitor: monthly if published, otherwise the next best unit."""
    prices = [p for p in competitor.prices if p.unit != "joining fee"]
    for unit in PREFERRED_UNITS:
        same = [p for p in prices if p.unit == unit]
        if same:
            lowest = min(same, key=lambda p: p.amount_inr)
            return {"amount_inr": lowest.amount_inr, "unit": unit, "label": lowest.label, "source_url": lowest.source_url}
    return None


def build_matrix(research: MarketResearch, reviews: ReviewResearch | None) -> list[dict]:
    by_name = {r.competitor: r for r in (reviews.competitors if reviews else [])}
    rows = []
    for c in research.competitors:
        r = by_name.get(c.name)
        rows.append({
            "name": c.name,
            "locality": c.locality,
            "price": headline_price(c),
            "price_status": c.price_status,
            "schedule": c.schedule,
            "channels": c.channels,
            "rating": r.rating if r else None,
            "rating_count": r.rating_count if r else None,
            "likes": [p.point for p in r.likes] if r else [],
            "complaints": [p.point for p in r.complaints] if r else [],
        })
    return rows


def matrix_markdown(rows: list[dict]) -> str:
    lines = ["| Competitor | Price | Schedule | Google rating | Customers like | Customers complain |",
             "|---|---|---|---|---|---|"]
    for row in rows:
        p = row["price"]
        price = f"Rs {p['amount_inr']:,} {p['unit']}" if p else row["price_status"].replace("_", " ")
        rating = f"{row['rating']} ({row['rating_count']})" if row["rating"] else "-"
        cell = lambda items: "; ".join(items[:2]) or "-"  # noqa: E731
        lines.append(f"| {row['name']} | {price} | {row['schedule'][:60]} | {rating} | {cell(row['likes'])} | {cell(row['complaints'])} |")
    return "\n".join(lines)
