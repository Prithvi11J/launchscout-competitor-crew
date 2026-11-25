"""The founder's input form, as data.

Every agent and task description uses {placeholders} such as {idea} and {city}.
CrewAI fills them from the dict that `BusinessBrief.to_inputs()` returns, which
is what lets the same crew research any idea in any city without code changes.
"""

from pydantic import BaseModel, Field, field_validator


class BusinessBrief(BaseModel):
    idea: str = Field(min_length=3, description="What the founder wants to launch")
    city: str = Field(min_length=2)
    target_customer: str = Field(min_length=3)
    known_competitors: list[str] = Field(default_factory=list)

    @field_validator("idea", "city", "target_customer")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("known_competitors")
    @classmethod
    def _clean_names(cls, names: list[str]) -> list[str]:
        return [n.strip() for n in names if n.strip()]

    def to_inputs(self) -> dict[str, str]:
        """Values for the {placeholders} in agent and task text."""
        known = ", ".join(self.known_competitors) if self.known_competitors else "none given"
        return {
            "idea": self.idea,
            "city": self.city,
            "target_customer": self.target_customer,
            "known_competitors": known,
        }


# The demo input used in the README, video and live demo.
DEMO_BRIEF = BusinessBrief(
    idea="Evening and weekend dance classes (Bollywood, hip-hop, dance fitness)",
    city="Coimbatore",
    target_customer="Working professionals, age 22 to 40",
)
