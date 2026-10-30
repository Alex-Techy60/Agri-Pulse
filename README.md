# KisaanMitra — live-data farm decision agent (FORGE '26 · Theme 2)

> **TODO before submission:** screenshot/GIF, live URL, demo video link, team.

KisaanMitra turns a farmer's *place + crop* into a clear, spoken decision — **sell now, hold, spray today, skip irrigation, protect the crop** — using only **live** data: Open-Meteo (weather, soil moisture) and data.gov.in/Agmarknet (mandi prices). Risk flags and the sell/hold signal are computed by deterministic code; the LLM only explains them in the farmer's language, and a guardrail rejects any number that is not in the tool output. If a source is down it says so — it never invents data.

## Run it
```bash
make setup                 # venv, pip, npm, .env
# put LLM_API_KEY (Groq) and DATA_GOV_API_KEY (data.gov.in) in .env
make check-live            # confirms every live source works from your machine
make test && make dev      # API :8000, UI :5173
```

## Starter vs built during FORGE (disclosure)
| Pre-event generic boilerplate | Built during FORGE '26 (after 30 Oct 7:30 PM IST) |
|---|---|
| LLM client w/ provider fallback, vector-store wrapper, SSE API shell, React/Vite shell, Docker/CI files | Farm domain, live weather/soil + mandi tools, decision rules, grounded-number guardrail, orchestrator upgrades (parallel tools, ask-for-missing-input, source-failure handling), profile + forecast/price cards UI, tests, evaluation |

_Keep this table accurate as the project evolves._

## Status
Logic tests (rules, tools with response-shape fixtures, orchestrator behaviours) were run with stubs because package registries were unreachable while writing; run `make test` for the full suite. Live API calls (Open-Meteo, data.gov.in), voice transcription and vision have **not** been exercised from this environment — `make check-live` is the first thing to run.

MIT License.
