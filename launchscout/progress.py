"""Live progress events: which agent is working and what it just did or found.

Tools and checks call `emit(role, message)`. The app sets a sink (a thread-safe
queue's `put`) and shows the events while the crew runs in a background thread.
With no sink set (tests, scripts), events go nowhere.
"""

from collections.abc import Callable

_sink: Callable[[dict], None] | None = None


def set_sink(sink: Callable[[dict], None] | None) -> None:
    global _sink
    _sink = sink


def emit(role: str, message: str) -> None:
    if _sink is not None:
        _sink({"role": role, "message": message})
