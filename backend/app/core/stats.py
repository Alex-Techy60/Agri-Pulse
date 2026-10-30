"""In-process counters for GET /api/stats (reset on restart). Aggregates only: never user text, never keys."""
from __future__ import annotations

import threading
from collections import Counter

_lock = threading.Lock()
_c: Counter = Counter()
_langs: Counter = Counter()
_intents: Counter = Counter()
_latency_total_ms = 0


def record(result: dict, ms: int) -> None:
    """result = ChatResult.dict(). Counts pipeline events from its trace."""
    global _latency_total_ms
    trace = result.get("trace") or []
    acts = [(t.get("agent"), t.get("action"), t.get("ok", True)) for t in trace]
    with _lock:
        _c["total_answers"] += 1
        _c["degraded_answers"] += bool(result.get("degraded"))
        _c["guardrail_rejections"] += sum(1 for a, act, _ in acts if a == "Guardrail" and act == "REJECTED")
        _c["guardrail_fallbacks"] += sum(1 for a, act, _ in acts if a == "Guardrail" and act == "fallback")
        _c["injection_attempts_flagged"] += sum(1 for a, act, _ in acts if a == "Guardrail" and act == "injection attempt flagged")
        _c["tool_failures"] += sum(1 for a, _, ok in acts if a == "Tool" and not ok)
        _c["replans"] += sum(1 for a, act, _ in acts if a == "Planner" and act == "replan")
        _langs[result.get("language") or "unknown"] += 1
        _intents[result.get("intent") or "unknown"] += 1
        _latency_total_ms += ms


def snapshot() -> dict:
    with _lock:
        n = _c["total_answers"]
        return {
            "total_answers": n,
            "degraded_answers": _c["degraded_answers"],
            "guardrail_rejections": _c["guardrail_rejections"],
            "guardrail_fallbacks": _c["guardrail_fallbacks"],
            "injection_attempts_flagged": _c["injection_attempts_flagged"],
            "tool_failures": _c["tool_failures"],
            "replans": _c["replans"],
            "avg_latency_ms": round(_latency_total_ms / n) if n else 0,
            "languages_used": dict(_langs),
            "intents_used": dict(_intents),
        }


def reset() -> None:  # tests only
    global _latency_total_ms
    with _lock:
        _c.clear(), _langs.clear(), _intents.clear()
        _latency_total_ms = 0
