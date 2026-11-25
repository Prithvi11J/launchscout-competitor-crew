"""Pydantic shapes for what each task must hand back.

A task's `expected_output` tells the agent the format in words; these models
make the same format checkable in code. Field descriptions are sent to the
model too, so they double as instructions.
"""

from typing import Literal

from pydantic import BaseModel, Field

# General enough for most local businesses: classes, meals, services, rentals.
PriceUnit = Literal[
    "per month", "per week", "per day", "per meal", "per class", "per visit", "per order", "per item",
    "per course", "per hour", "per year", "joining fee", "other",
]


class PricePoint(BaseModel):
    label: str = Field(description="What this price is for, e.g. 'Adults, 2 classes a week'")
    amount_inr: int = Field(description="Price in Indian rupees as a whole number, e.g. 800")
    unit: PriceUnit
    source_url: str = Field(description="The exact page where this price appears")


class Competitor(BaseModel):
    name: str = Field(description="The business itself, never a listing site such as Justdial or UrbanPro")
    locality: str = Field(description="Area of the city, or 'unknown'")
    offering: str = Field(description="What they sell, e.g. styles, batch timings, formats")
    price_status: Literal["published", "on_enquiry", "not_found"] = Field(
        description="'published' only if a real price was found on a page; never guess a number"
    )
    prices: list[PricePoint] = Field(description="Empty unless price_status is 'published'")
    schedule: str = Field(
        description="When customers can use it, e.g. batch timings, opening hours, delivery slots; 'unknown' if not found"
    )
    fit_reason: str = Field(description="One sentence: why this business competes for the founder's target customer")
    channels: list[str] = Field(description="Where they sell or take bookings, e.g. Instagram, website, Justdial, walk-in")
    offers: list[str] = Field(description="Trial classes, discounts, packages; empty if none found")
    source_urls: list[str] = Field(description="Every page used for this competitor")


class MarketPriceNote(BaseModel):
    summary: str = Field(description="A city-wide price range from a listing or guide site, e.g. 'Rs 750-1,000 per month'")
    source_url: str


class MarketResearch(BaseModel):
    competitors: list[Competitor]
    market_price_context: list[MarketPriceNote] = Field(
        description="City averages and ranges from listing sites; kept apart from any single competitor's price"
    )


class FitJudgement(BaseModel):
    name: str
    direct_competitor: bool
    reason: str = Field(description="One short sentence")


class FitVerdict(BaseModel):
    """The fit judge's answer: one judgement per competitor."""

    judgements: list[FitJudgement]


class ReviewPoint(BaseModel):
    point: str = Field(description="One short sentence in your own words, e.g. 'Batches start late'")
    quote: str = Field(description="The exact words (5 to 25) from the search result or page that show this")
    source_url: str = Field(description="The page or search result the quote comes from")


class CompetitorReviews(BaseModel):
    competitor: str = Field(description="Exactly the competitor name from the research")
    rating: float | None = Field(default=None, description="Average star rating if shown, e.g. 4.5; null if not found")
    rating_count: int | None = Field(default=None, description="Number of ratings or reviews if shown")
    rating_source_url: str | None = None
    likes: list[ReviewPoint] = Field(description="What customers praise; empty if nothing found")
    complaints: list[ReviewPoint] = Field(description="What customers complain about; empty if nothing found")


class ReviewResearch(BaseModel):
    competitors: list[CompetitorReviews]


class StrategyAnalysis(BaseModel):
    market_gap: str = Field(description="2 to 3 sentences: the one opportunity no competitor serves well today")
    gap_evidence: list[str] = Field(description="Names of the competitors whose prices, schedules or reviews show this gap")
    positioning: str = Field(description="One line a founder could put on a poster, including the price")
    recommended_price_inr: int = Field(description="Launch price in rupees, as a whole number")
    price_unit: PriceUnit
    price_reason: str = Field(description="1 to 2 sentences comparing the price with competitors' prices")


class WeekPlan(BaseModel):
    week: int = Field(description="1, 2, 3 or 4")
    focus: str = Field(description="The week's goal in a few words, e.g. 'Book a studio and trial batch'")
    actions: list[str] = Field(description="2 to 4 concrete, checkable actions for the founder")


class LaunchPlan(BaseModel):
    summary: str = Field(description="2 to 3 plain sentences for the founder: who to beat, the gap, the offer")
    weeks: list[WeekPlan] = Field(description="Exactly 4 weeks, in order")
