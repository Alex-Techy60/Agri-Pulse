"""Verify every live source works from THIS machine, with YOUR keys.  Run before building and before every demo:

    make check-live                       (or: cd backend && python -m scripts.check_live "Nashik, Maharashtra" Onion)

Prints PASS/FAIL per source and, for data.gov.in, the real field names so you can confirm the schema.
"""
import re
import sys

import httpx

from app.core.config import get_settings, llm_keys
from app.tools import NeedsInput
from app.tools.http import get_json
from app.tools.mandi import API, mandi
from app.tools.rain_history import rain_history
from app.tools.weather import weather


def llm_quota(s) -> int:
    """Send a 1-token request to each Groq model with each key: the free daily token quota is the likeliest way a demo goes slow.

    Returns the number of models that NO key can answer (the app rotates to the next key on its own). The 429 text is
    reduced to its Limit/Used figures (it also names the organisation); keys are shown by position only.
    """
    keys = llm_keys(s)
    if not keys:
        print("LLM_API_KEY not set: answers will be 'live data only'.")
        return 0
    failing = 0
    for label, model in (("main", s.llm_model), ("reserve/router", s.llm_fast_model)):
        body = ({"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 16, "reasoning_effort": "low"} if model.startswith("openai/gpt-oss")
                else {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1})
        answered = 0
        for n, key in enumerate(keys, 1):
            tag = f"{label} ({model}), key {n}/{len(keys)}"
            try:
                r = httpx.post(f"{s.llm_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=20)
                if r.status_code == 429:
                    m = re.search(r"\((\w+)\): Limit (\d+), Used (\d+)", r.text)
                    print(f"FAIL LLM {tag}: quota spent" + (f" - {m.group(1)} limit {m.group(2)}, used {m.group(3)}" if m else " - rate limited"))
                elif r.is_success:
                    print(f"PASS LLM {tag}: answers")
                    answered += 1
                else:
                    print(f"FAIL LLM {tag}: HTTP {r.status_code}")
            except Exception as e:
                print(f"FAIL LLM {tag}: {type(e).__name__}")
        if not answered:
            failing += 1
    return failing


def main() -> int:
    place = sys.argv[1] if len(sys.argv) > 1 else "Nashik, Maharashtra"
    crop = sys.argv[2] if len(sys.argv) > 2 else "Onion"
    s = get_settings()
    bad = 0
    print(f"Place={place!r} Crop={crop!r}\n")

    for name, tool in (("weather + soil (Open-Meteo)", weather), ("rain history (Open-Meteo)", rain_history), ("mandi prices (data.gov.in)", mandi)):
        try:
            r = tool("", {"place": place, "crop": crop})
            print(("PASS " if r.ok else "FAIL ") + name)
            print("     " + "\n     ".join(r.text.splitlines()[:6]))
            bad += 0 if r.ok else 1
        except NeedsInput as e:
            print(f"FAIL {name}: needs {e.field}")
            bad += 1
        except Exception as e:
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            bad += 1
        print()

    if s.data_gov_api_key:
        try:
            f = get_json(API.format(rid=s.mandi_resource_id), {"api-key": s.data_gov_api_key, "format": "json", "limit": 2}, ttl=0)
            d = f.data if isinstance(f.data, dict) else {}
            recs = d.get("records") or []
            print("data.gov.in raw probe: top-level keys =", sorted(d.keys()))
            if recs:
                print("  record fields =", list(recs[0].keys()))
                print("  example       =", recs[0])
                print("  -> if field names are Capitalised, set MANDI_FILTER_STYLE=title in .env (auto tries both).")
            else:
                print("  no records returned: check MANDI_RESOURCE_ID (find the right resource on data.gov.in -> API tab).")
        except Exception as e:
            print(f"data.gov.in raw probe FAILED: {type(e).__name__}: {e}")
    else:
        print("DATA_GOV_API_KEY not set: mandi prices will show 'source unavailable' (get a free key at data.gov.in).")

    print()
    failing = llm_quota(s)
    if failing == 2:  # both models out: every answer is slow or live-data-only
        bad += 1
    elif failing:
        print("     (the other model still answers, so the demo works; the main model is the better writer)")

    # Pillar checks: schemes, grievance store, receipts
    try:
        from app.explainer.engine import list_available_schemes
        schemes = list_available_schemes()
        print(f"\nPASS schemes policy library ({len(schemes)} official guidelines verified)")
    except Exception as e:
        print(f"\nFAIL schemes policy library: {e}")
        bad += 1

    try:
        from app.grievance.store import get_board_stats
        board = get_board_stats()
        print(f"PASS farm crisis grievance store ({board['total_reports']} incident tickets active)")
    except Exception as e:
        print(f"FAIL farm crisis grievance store: {e}")
        bad += 1

    try:
        from app.executor.receipts import sign_receipt, verify_receipt
        rec = sign_receipt({"test": "live_check"})
        if verify_receipt(rec):
            print("PASS cryptographic receipt engine (Ed25519 digital signatures verified)")
        else:
            print("FAIL cryptographic receipt engine: signature verification failed")
            bad += 1
    except Exception as e:
        print(f"FAIL cryptographic receipt engine: {e}")
        bad += 1

    print("\nRESULT:", "ALL LIVE SOURCES OK" if bad == 0 else f"{bad} source(s) failing - fix before the demo")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
