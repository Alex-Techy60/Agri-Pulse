"""Tool contract used by the orchestrator.

    tool(text: str, profile: dict) -> ToolResult

Rules (CLAUDE.md): tools return REAL data from a live source or an explicit
failure. They never invent values. Recoverable problems are expressed as
exceptions that `guarded()` turns into a clear ToolResult(ok=False):

    NeedsInput(field)   -> the agent asks the user for that field
    PlaceNotFound       -> the agent asks for a better place name
    SourceUnavailable   -> the agent says the live source is down (no guessing)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps


class NeedsInput(Exception):
    def __init__(self, field_name: str, hint: str = ""):
        super().__init__(field_name)
        self.field = field_name
        self.hint = hint or field_name


class PlaceNotFound(Exception):
    pass


class SourceUnavailable(Exception):
    pass


@dataclass
class ToolResult:
    text: str  # goes into the LLM CONTEXT block: facts only
    ok: bool = True
    sources: list[dict] = field(default_factory=list)  # {name, url, fetched_at, stale}
    cards: list[dict] = field(default_factory=list)  # UI cards {type, title, ...}
    facts: dict = field(default_factory=dict)  # structured output for other tools / UI


def guarded(name: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(text: str, profile: dict) -> ToolResult:
            try:
                return fn(text, profile)
            except NeedsInput:
                raise
            except PlaceNotFound as e:
                return ToolResult(
                    f"{name.upper()} FAILED: place not found ({e}). Ask the user for the nearest town or district.", ok=False
                )
            except SourceUnavailable as e:
                return ToolResult(
                    f"{name.upper()} SOURCE UNAVAILABLE ({e}). Do NOT guess these values; "
                    "tell the user this live source is not reachable right now.",
                    ok=False,
                )

        return wrapper

    return deco
