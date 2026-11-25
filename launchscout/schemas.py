"""Pydantic shapes for what each task must hand back.

A task's `expected_output` tells the agent the format in words; these models
make the same format checkable in code. Field descriptions are sent to the
model too, so they double as instructions.
"""

from typing import Literal

from pydantic import BaseModel, Field

PriceUnit = Literal["per month", "per class", "per hour", "per course", "joining fee", "other"]


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
