# KisaanMitra — live-data farm decision agent (FORGE '26 · Theme 2)

> **TODO before submission:** screenshot/GIF, live URL, demo video link, team.

KisaanMitra turns a farmer's *place + crop* into a clear, spoken recommendation — **sell or hold on the recent price trend, spray today, skip irrigation, protect the crop** — using only **live** data: Open-Meteo (weather, soil moisture, rain history) and data.gov.in/Agmarknet (mandi prices). Risk flags and the sell/hold signal (a recent-trend indicator, not a price forecast) are computed by deterministic code; the LLM only explains them in the farmer's language, and guardrails reject any number or date that is not in the tool output. If a source is down it says so — it never invents data.

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
| | **Track 1 additions:** planner + one-retry re-plan, rain-history tool and card, crop-photo diagnosis card, cited crop-stage rules, per-session place/crop memory, prompt-injection defences, date grounding, negation-aware guarantee rule, circuit breaker + cache cap, rate limiting, `/api/stats`, locked-down ingest, safe API fallbacks, hermetic tests (166, no network or keys needed) |

The commit history is the evidence: `git log` shows the work added after the starter.

## Status — what was and was not verified
- **Verified live (30 Oct 2026):** Open-Meteo weather and rain history; data.gov.in mandi prices (real records for Maharashtra, Punjab, Karnataka, Kerala and others); Groq chat, router and vision (a real tomato-blight photo gave a Hindi answer and a diagnosis card); OpenRouter failover; the Docker image; a fresh clone running `make setup` and `make test` with no keys.
- **What the mandi source really is** (found by testing the live API and its downloadable file):
  - Two data.gov.in resources are used. The daily one publishes **only the current day** and ignores the date filter. The second (`35985678-...`, Variety-wise Daily Market Prices) holds dated prices up to yesterday; one sorted call gives the last 10 days (the trend compares today with a day 5 to 9 days back), which is what makes the trend and SELL_NOW / HOLD possible. If it fails, the app falls back to today's prices and says no trend is available.
  - The API rate limits bursts (429), so history is one call per crop and state, cached for an hour, and a failure never blocks today's prices.
  - It also computes the farmer's district vs the state median (`ABOVE/NEAR/BELOW_STATE_MEDIAN`) and the best-paying market in the state. When no trend exists, `cross_check` uses that position instead and says it is based on today's snapshot.
  - The API's commodity filter is a loose text match (asking for Onion also returns Onion Green), so records are cut to exact commodity matches. State spellings differ from the geocoder's (Kerala is Keralam, Delhi is NCT of Delhi), so they are translated.
  - **The sell/hold signal is a recent-trend indicator, not a price forecast.** It compares the same markets today and about a week ago: a rise of 5 % or more is HOLD, a fall of 5 % or more is SELL_NOW, otherwise NEUTRAL (using the same markets means a changing set of reporting markets cannot fake a move). The first version said "above the recent average, so sell"; a backtest on a year of real prices showed it pointed the wrong way, because prices here tend to continue a move. It was reversed and measured again on data not used to choose it.
  - **Measured** with `python -m scripts.backtest_signal` (add `--cache DIR` to reuse a download; it downloads slowly on purpose): 6 real series (Maharashtra onion, tomato, potato; Karnataka onion, tomato; Punjab potato), 31 Oct 2025 to 29 Oct 2026. The newest 40 % of days (762 days) were never used to choose the rule. After HOLD, prices rose by more than 1 % over the next week 51 % of the time, while they rose that much on 26 % of all days. The average following week was +4.0 % after HOLD and +0.2 % after SELL_NOW, a gap of 3.8 points; the 90 % interval is -1.1 to +8.7 points (whole weeks resampled), so it is **not statistically proven**. The retired rule's gap on the same days was -3.1 points.
  - **By crop:** onion worked (HOLD was followed by a rise 65 % and 68 % of the time in the two onion series). Tomato did not (no better than chance), and potato prices barely move, so the app tells the farmer how reliable the trend is for that crop, and for crops not tested. The test covers one year and one season in which onion prices rose strongly: treat the signal as one input beside weather and market position.
- **Measured speed:** 10 questions in 10 different cities (cold cache, one at a time, local run, 31 Oct 2026): median 5.3 s, slowest 9.8 s, none degraded. Reproduce by posting questions to `/api/chat` in a loop and timing each. When Groq is unreachable the free fallback model answers in roughly 20 to 35 s, so treat that path as a backup, not a demo path.
- **Known limits:** the NHB tomato bulletin cited for the tomato rules returned HTTP 404 on 31 Oct 2026 and could not be re-checked, so the tomato 10 C cold rule is unconfirmed. the place finder (Open-Meteo geocoding) lacks some places or knows them under new names, so a small table maps a few old names to the ones it knows (Panaji, Ahmednagar, Bangalore, Allahabad, Gurgaon). If a typed state or district has no match, the agent asks for a nearer town instead of using another district's data ("Sawantwadi, Sindhudurg" is rejected because the finder only knows a Sawantwadi in Latur). Crop names were checked against real data; some crops have no records in some states on a given day, and the app says so. Places and crops typed in Devanagari (for example येवला, कांदा) work: the place is searched in Marathi, then Hindi, and re-read in English, and 62 Hindi and Marathi crop names (33 crops) are mapped (checked live on 31 Oct 2026); villages the geocoder does not know in Devanagari (for example लासलगाव) are not found, and the agent asks for a nearer town. Voice transcription was checked only with synthesised speech (an English sentence came back word for word; robot-voice Hindi and Marathi came back garbled), never with a human voice, so Hindi and Marathi accuracy is unknown. Hinglish typed in Latin script is answered in Hindi.

MIT License.
