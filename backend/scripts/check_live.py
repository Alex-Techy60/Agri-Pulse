"""Verify every live source works from THIS machine, with YOUR keys.  Run before building and before every demo:

    make check-live                       (or: cd backend && python -m scripts.check_live "Nashik, Maharashtra" Onion)

Prints PASS/FAIL per source and, for data.gov.in, the real field names so you can confirm the schema.
"""
import sys

from app.core.config import get_settings
from app.tools import NeedsInput
from app.tools.http import get_json
from app.tools.mandi import API, mandi
from app.tools.weather import weather


def main() -> int:
    place = sys.argv[1] if len(sys.argv) > 1 else "Nashik, Maharashtra"
    crop = sys.argv[2] if len(sys.argv) > 2 else "Onion"
    s = get_settings()
    bad = 0
    print(f"Place={place!r} Crop={crop!r}\n")

    for name, tool in (("weather + soil (Open-Meteo)", weather), ("mandi prices (data.gov.in)", mandi)):
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

    print("\nRESULT:", "ALL LIVE SOURCES OK" if bad == 0 else f"{bad} source(s) failing - fix before the demo")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
