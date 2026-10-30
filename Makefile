.PHONY: setup dev api ui test seed build demo-check check-live clean

PY ?= python3
PLACE ?= Nashik, Maharashtra
CROP ?= Onion
VENV = backend/.venv
BIN = $(VENV)/bin

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -r backend/requirements.txt
	cd frontend && npm install
	@test -f .env || cp .env.example .env
	@echo "Setup done. Put LLM_API_KEY in .env (optional: runs offline without it), then: make dev"

api:
	cd backend && ../$(BIN)/uvicorn app.main:app --reload --port 8000

ui:
	cd frontend && npm run dev

dev:
	@$(MAKE) -j2 api ui

test:
	cd backend && ../$(BIN)/python -m pytest -q

seed:
	cd backend && ../$(BIN)/python -m scripts.seed

build:
	cd frontend && npm run build

check-live:
	cd backend && ../$(BIN)/python -m scripts.check_live "$(PLACE)" "$(CROP)"

demo-check:
	@curl -sf localhost:8000/api/health >/dev/null && echo "PASS health" || (echo "FAIL health: is the API running?"; exit 1)
	@curl -sf -X POST localhost:8000/api/chat -H 'content-type: application/json' -d '{"message":"hello"}' | grep -q '"answer"' && echo "PASS chat" || (echo "FAIL chat"; exit 1)
	@curl -sf "localhost:8000/api/live-check" | python3 -c "import sys,json; d=json.load(sys.stdin); bad=[k for k,v in d.items() if not v['ok']]; print('PASS live data' if not bad else 'FAIL live data: '+', '.join(bad)); sys.exit(1 if bad else 0)"

clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist
