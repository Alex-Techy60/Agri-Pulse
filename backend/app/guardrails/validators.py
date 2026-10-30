"""Deterministic guardrails. The LLM proposes, plain code disposes.

(Pattern from Demeter: `validate_hard_limits` + reject-with-critique loop.)
A validator takes the draft answer text and returns a list of violation strings.
Empty list == OK. Violations are fed back to the agent once as a critique; if it
still fails, the orchestrator returns the domain's safe fallback instead.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable

Validator = Callable[[str], list[str]]


def forbid_patterns(rules: dict[str, str]) -> Validator:
    """rules: {regex: message}. Flags any regex that matches (case-insensitive)."""
    compiled = [(re.compile(p, re.I), m) for p, m in rules.items()]

    def check(text: str) -> list[str]:
        return [m for rx, m in compiled if rx.search(text)]

    return check


_NEGATION = re.compile(r"\b(?:not|no|never|cannot|can't|cant|without|nobody|nothing)\b|n't", re.I)


def forbid_unless_negated(rules: dict[str, str], window: int = 30) -> Validator:
    """Like forbid_patterns, but a match is ignored when the same clause negates it ("I cannot guarantee profit",
    "this is not risk-free"). Needed so a correct refusal is not rejected as if it were the forbidden claim."""
    compiled = [(re.compile(p, re.I), m) for p, m in rules.items()]

    def check(text: str) -> list[str]:
        out = []
        for rx, msg in compiled:
            for m in rx.finditer(text):
                clause = re.split(r"[.!?;\n]", text[max(0, m.start() - window):m.start()])[-1]
                if not _NEGATION.search(clause):
                    out.append(msg)
                    break
        return out

    return check


def numeric_limit(label: str, pattern: str, lo: float | None = None, hi: float | None = None, unit: str = "") -> Validator:
    """Extract a number via regex group 1 and enforce a hard range.

    numeric_limit("pH", r"pH\\s*(?:of|to|=)?\\s*([\\d.]+)", 5.0, 7.5)
    """
    rx = re.compile(pattern, re.I)

    def check(text: str) -> list[str]:
        out = []
        for m in rx.finditer(text):
            try:
                v = float(m.group(1))
            except ValueError:
                continue
            if lo is not None and v < lo:
                out.append(f"{label}={v}{unit} is below the safe minimum {lo}{unit}.")
            if hi is not None and v > hi:
                out.append(f"{label}={v}{unit} is above the safe maximum {hi}{unit}.")
        return out

    return check


def max_words(n: int) -> Validator:
    def check(text: str) -> list[str]:
        w = len(text.split())
        return [f"Answer is {w} words; limit is {n}. Shorten it."] if w > n else []

    return check


_NUM = re.compile(r"\d+(?:\.\d+)?")


def _ascii_digits(s: str) -> str:
    out = []
    for c in s:
        if c.isdigit() and not c.isascii():
            try:
                c = str(unicodedata.digit(c))
            except ValueError:
                pass
        out.append(c)
    return "".join(out)


def _norm_num(n: str) -> str:
    return (str(float(n)).rstrip("0").rstrip(".")) if "." in n else str(int(n))


def numbers_in(s: str) -> set[str]:
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", _ascii_digits(s))  # 2,450 -> 2450
    return {_norm_num(n) for n in _NUM.findall(s)}


def grounded_numbers(min_value: float = 10.0) -> Validator:
    """Anti-hallucination: every number >= min_value (or with decimals) in the answer must appear in the
    CONTEXT (tool outputs + user message). Rounded versions of context numbers are allowed (33.1 -> 33)."""

    def check(text: str, context: str = "") -> list[str]:
        allowed = numbers_in(context)
        for a in list(allowed):
            f = float(a)
            allowed.update({str(int(f)), str(round(f))})
        bad = sorted(n for n in numbers_in(text) if (float(n) >= min_value or "." in n) and n not in allowed)
        return [f"These numbers are not in the provided data: {', '.join(bad)}. Use only numbers from the CONTEXT."] if bad else []

    check.wants_context = True  # type: ignore[attr-defined]
    return check


_INJECTION = re.compile(
    r"ignore\s+(?:all\s+|your\s+|the\s+|any\s+)?(?:previous\s+|prior\s+|above\s+)?(?:rules|instructions|system|prompt)"
    r"|you\s+are\s+now\s+(?:a|an)\s+|disregard\s+(?:your|the|all)\s+|reveal\s+(?:your\s+)?(?:system\s+)?prompt|system\s+prompt",
    re.I,
)


def looks_like_injection(text: str) -> bool:
    """Input-side screen for instruction-override attempts. Flags only: grounding + output rules still decide."""
    return bool(_INJECTION.search(text or ""))


_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2212": "-"})


def grounded_dates() -> Validator:
    """Every ISO date (YYYY-MM-DD) in the answer must appear in the CONTEXT. grounded_numbers alone would accept a
    made-up date whose parts (2026, 11, 03) happen to occur elsewhere in the data. Handles typographic hyphens."""

    def check(text: str, context: str = "") -> list[str]:
        known = set(_ISO_DATE.findall(context.translate(_DASHES)))
        bad = sorted({d for d in _ISO_DATE.findall(text.translate(_DASHES)) if d not in known})
        return [f"These dates are not in the provided data: {', '.join(bad)}. Use only dates from the CONTEXT."] if bad else []

    check.wants_context = True  # type: ignore[attr-defined]
    return check


def run_all(validators: list[Validator], text: str, context: str = "") -> list[str]:
    out: list[str] = []
    for v in validators:
        out.extend(v(text, context) if getattr(v, "wants_context", False) else v(text))
    return out
