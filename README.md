# KisaanMitra — live-data farm decision agent (FORGE '26 · Theme 2)

> **TODO before submission:** screenshot/GIF, live URL, demo video link, team.

KisaanMitra turns a farmer's *place + crop* into a clear, spoken decision — **sell now, hold, spray today, skip irrigation, protect the crop** — using only **live** data: Open-Meteo (weather, soil moisture, rain history) and data.gov.in/Agmarknet (mandi prices). Risk flags and the sell/hold signal are computed by deterministic code; the LLM only explains them in the farmer's language, and guardrails reject any number or date that is not in the tool output. If a source is down it says so — it never invents data.

## How it works
```
React UI ──SSE──▶ FastAPI /api/chat/stream ──▶ Orchestrator
  Router (fast LLM, keyword fallback)
  → Planner (LLM picks extra tools; code validates) → Tools in parallel: weather · rain_history · mandi
  → one retry for unreachable sources ("replan") → post-tools: cross_check (price position/trend × rain), crop_stage (cited crop rules)
  → Retriever → Specialist (LLM, user's language) → Guardrails in code ⟲ self-correct → answer + cards + sources
Photo: Vision model → structured diagnosis card (symptoms, severity, possible causes; no brands or doses)
```
Every step appears in the live **Agent Trace**. LLM calls go Groq → OpenRouter fallback → offline mode (live data only, no AI summary).

## Run it
```bash
make setup                 # venv, pip, npm, .env
# put LLM_API_KEY (Groq) and DATA_GOV_API_KEY (data.gov.in) in .env; FALLBACK_* is optional
make check-live            # confirms every live source works from your machine
make test && make dev      # API :8000, UI :5173
make build && docker build -t kisaanmitra .   # one container: API serves the built UI
```
Weather and rain history need no key. Without `LLM_API_KEY` the app shows live data only ("AI summary unavailable"). Mandi prices need `DATA_GOV_API_KEY`.

## API
`POST /api/chat`, `POST /api/chat/stream` (SSE trace events then one final result), `POST /api/voice/transcribe`, `GET /api/health`, `GET /api/domain`, `GET /api/live-check`, `GET /api/stats` (aggregate counters, no user text), `POST /api/ingest` (disabled unless `INGEST_API_KEY` is set; send it as `X-Admin-Key`). Chat routes are rate limited (`RATE_LIMIT_PER_MIN`, default 20 per client+session, 3× that per client IP).

## Safety and honesty rules (enforced in code, tested)
- No dummy data. A failed source shows "source unavailable"; stale-but-real cached data is labelled with its true time.
- Numbers and dates in an answer must exist in the tool output; numbers typed by the user do not count as evidence (prompt-injection defence).
- No pesticide brands, doses or application rates; no profit guarantees (refusals like "I cannot guarantee" are allowed).
- Rule thresholds are labelled **IMD** (read from the IMD glossary) or **HEURISTIC** (no verified Indian source). Crop rules exist only where a primary source was read: tomato (NHB) and Punjab wheat (ICAR). Onion has no crop rule on purpose.

## Starter vs built during FORGE (disclosure)
| Pre-event generic boilerplate | Built during FORGE '26 (after 30 Oct 7:30 PM IST) |
|---|---|
| LLM client w/ provider fallback, vector-store wrapper, SSE API shell, React/Vite shell, Docker/CI files | Farm domain, live weather/soil + mandi tools, decision rules, grounded-number guardrail, parallel tools, ask-for-missing-input, source-failure handling, profile + forecast/price cards UI |
| | **Track 1 additions:** planner + one-retry re-plan, rain-history tool and card, crop-photo diagnosis card, cited crop-stage rules, per-session place/crop memory, prompt-injection defences, date grounding, negation-aware guarantee rule, circuit breaker + cache cap, rate limiting, `/api/stats`, locked-down ingest, safe API fallbacks, hermetic tests (about 117) |

The commit history is the evidence: `git log` shows the work added after the starter.

## Status — what was and was not verified
- **Verified live (30 Oct 2026):** Open-Meteo weather and rain history; data.gov.in mandi prices (real records for Maharashtra, Punjab, Karnataka, Kerala and others); Groq chat, router and vision (a real tomato-blight photo gave a Hindi answer and a diagnosis card); OpenRouter failover; the Docker image; a fresh clone running `make setup` and `make test` with no keys.
- **What the mandi source really is** (found by testing the live API and its downloadable file):
  - It publishes **only the current day** (17,000+ records, all dated the same day), and the API ignores the date filter. So a multi-day price **trend and the SELL_NOW / HOLD signal are not available from this source**; the app says so ("a price trend is not available").
  - What it does compute from real data: today's prices, the farmer's district vs the state median (`ABOVE/NEAR/BELOW_STATE_MEDIAN`), and the best-paying market in the state. If heavy rain is forecast, `cross_check` uses that position to say sell-before-rain or protect-stock, and states that it is based on today's snapshot, not a trend.
  - The API's commodity filter is a loose text match (asking for Onion also returns Onion Green), so records are cut to exact commodity matches. State spellings differ from the geocoder's (Kerala is Keralam, Delhi is NCT of Delhi), so they are translated.
  - The trend code (3 or more days, +/-5 % band) is tested with fixtures only. It has never been run on real multi-day data and the +/-5 % band is an untested heuristic.
- **Known limits:** the place finder lacks some places or uses old names (it finds "Panjim" and "Ahilyanagar" but not "Panaji" or "Ahmednagar"); if a typed state has no match the agent asks for a nearer town instead of guessing. Crop names were checked against real data; some crops have no records in some states on a given day, and the app says so. Voice transcription has not been tested with real audio. Hinglish typed in Latin script is answered in Hindi.

MIT License.
