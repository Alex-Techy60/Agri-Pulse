"""THE ONLY PLACE A NEW PROBLEM NEEDS EDITING (plus app/tools/ and app/decision/ for live data + rules).

A Domain bundles: persona, intents (router labels), tools per intent, hard-limit validators,
safe fallback, suggested prompts and UI languages. The orchestrator, LLM client, memory, API and UI are generic.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable

from app.core.config import get_settings
from app.guardrails.validators import Validator
from app.tools import ToolResult

Tool = Callable[[str, dict], ToolResult]  # (user text, profile) -> ToolResult


@dataclass
class Intent:
    name: str
    description: str  # shown to the router LLM; also used for keyword fallback
    instructions: str  # extra system instructions when this intent is chosen
    keywords: list[str] = field(default_factory=list)


@dataclass
class Domain:
    name: str
    title: str
    tagline: str
    persona: str
    intents: list[Intent]
    validators: list[Validator]
    safe_fallback: str
    suggested_prompts: list[str]
    languages: dict[str, str] = field(default_factory=lambda: {"en": "English"})
    tools: dict[str, Tool] = field(default_factory=dict)
    intent_tools: dict[str, list[str]] = field(default_factory=dict)  # run in parallel
    post_tools: dict[str, list[str]] = field(default_factory=dict)  # run after, in order (cross-checks)
    vision_prompt: str = "Describe what is visible in this photo. Be factual and brief."
    vision_parser: Callable[[str], dict | None] | None = None  # vision text -> {summary, card} or None
    tool_help: dict[str, str] = field(default_factory=dict)  # one line per tool, shown to the planner
    profile_fields: list[dict] = field(default_factory=list)  # UI profile form: {key,label,placeholder,options?}


def load_domain() -> Domain:
    mod = importlib.import_module(f"app.domain.{get_settings().domain}")
    return mod.DOMAIN
