
.PHONY: fe be dev

# Venv path for backend (relative to backend/, since recipes cd there first)
VENV := .venv
ifeq ($(OS),Windows_NT)
    VENV_PY := $(VENV)/Scripts/python
else
    VENV_PY := $(VENV)/bin/python
endif

# Start frontend (Next.js)
fe:
	cd frontend && npm run dev

# Start backend (FastAPI via uvicorn). Uses backend venv python if present.
be:
	cd backend && if [ -x "$(VENV_PY)" ]; then "$(VENV_PY)" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000; else uvicorn main:app --reload --host 0.0.0.0 --port 8000; fi

# Start both concurrently using npx concurrently. Backend uses venv python if present.
dev:
	npx concurrently --kill-others "cd frontend && npm run dev" "cd backend && if [ -x '$(VENV_PY)' ]; then '$(VENV_PY)' -m uvicorn main:app --reload --host 0.0.0.0 --port 8000; else uvicorn main:app --reload --host 0.0.0.0 --port 8000; fi"
