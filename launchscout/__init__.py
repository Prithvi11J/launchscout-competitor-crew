"""LaunchScout: a four-agent CrewAI crew that researches competitors for a new business idea."""

# Load settings first: config switches off CrewAI telemetry, which only works
# if it happens before any module imports crewai. A package's __init__ always
# runs before its submodules, so this guarantees the order.
from launchscout import config  # noqa: F401
