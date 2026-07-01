# AGENTS.md

This file provides guidance to agents (i.e., ADAL) when working with code in this repository.

## Scope & Purpose

This repository is a split frontend/backend project for **LLM-driven trading strategy generation and backtesting**:

- `frontend/`: React + Vite UI
- `backend/`: LangGraph workflow + Dockerized strategy compilation/evaluation
- Root: orchestration (`Makefile`, `Dockerfile`, `docker-compose.yml`)

Use this guide to quickly find commands, entry points, and non-obvious flow constraints.

---

## 1) Essential Commands (Verified)

## Root-level orchestration

```bash
# Start both frontend and backend (Makefile)
make dev

# Start frontend only
make dev-frontend

# Start backend only
make dev-backend
```

Source: `Makefile`

### Gotcha
- `make dev` runs `make dev-frontend & make dev-backend` in one shell; stopping one process may not gracefully stop the other.

---

## Frontend (`frontend/`)

```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
npm run preview
```

Source: `frontend/package.json`

### Single-test/subset tests
- No frontend test scripts are defined in `package.json` (no `test` command present).

---

## Backend (`backend/`)

```bash
cd backend

# Install backend package and dependencies
pip install .

# Run backend dev server (LangGraph API dev mode)
langgraph dev
```

Sources: root `README.md`, `Makefile`, `backend/setup.py`, `backend/langgraph.json`

### Single-test/subset tests
- No Python test suite was found (`**/*test*.py` matched none).
- Closest reproducible evaluation command is strategy metrics execution inside runner/container:
  ```bash
  python metrics.py --strategy-path strategies/strategy-<id>.py --result-path logs/res-<id>.json
  ```
  (this is executed inside the backend runner container by `implement.py`)

---

## Docker / production-like run

```bash
# Build image from project root
docker build -t gemini-fullstack-langgraph -f Dockerfile .

# Run full stack with Redis + Postgres + API
GEMINI_API_KEY=<key> LANGSMITH_API_KEY=<key> docker-compose up
```

Sources: root `README.md`, `Dockerfile`, `docker-compose.yml`

### Infra dependencies in compose
- Redis service: `langgraph-redis`
- Postgres service: `langgraph-postgres` (mapped host `5433 -> 5432`)
- API service: `langgraph-api` on port `8123`

---

## 2) Critical Gotchas (Read Before Editing)

1. **API key mismatch in docs vs runtime path**
   - Root README emphasizes `GEMINI_API_KEY`.
   - Actual graph workflow nodes use Anthropic client and require `ANTHROPIC_API_KEY` in `initialize.py`; it raises immediately if missing.

2. **Frontend currently ignores user stock input**
   - In `frontend/src/App.tsx`, submit always sends:
     ```ts
     stock_symbol: "QQQ"
     ```
   - User-entered text/effort/model values are collected but effectively not passed through for backend strategy generation.

3. **Frontend activity timeline expects different event names than backend graph**
   - UI listens for `generate_query`, `web_research`, `reflection`, `finalize_answer`.
   - Backend trading graph nodes are `initialize`, `think`, `implement`, `aggregate`, `finish`.
   - Result: timeline semantics may not reflect current backend flow.

4. **Frontend serving path differs between dev and production**
   - Dev frontend runs via Vite (`localhost:5173`), backend API expected at `localhost:2024`.
   - In production image, FastAPI serves static frontend under `/app` and API via container port mapping (`8123` externally).

5. **Backend graph refinement loop hard-capped by think_count logic**
   - Route condition in `graph.py`:
     - Continue while `think_count < 3` and metric condition.
   - Practical iteration count is constrained regardless of UI “Iteration” selector.

6. **Potential state key inconsistency in aggregation path**
   - `aggregate.py` writes `previous_code` in one branch, but other stages expect/use `pre_code`.
   - This can silently drop previous code context for subsequent improvement cycles.

7. **No formal test harness in repo**
   - No standard unit/integration test files discovered.
   - Validate behavior using lint/build/dev runs and targeted strategy execution paths.

---

## 3) Non-Obvious Architecture & Data Flow

## High-level runtime flow

1. UI (`frontend/src/main.tsx`) mounts `App`.
2. `App.tsx` uses `useStream` from `@langchain/langgraph-sdk/react` with:
   - `assistantId: "agent"`
   - `apiUrl`: `localhost:2024` in dev, `localhost:8123` otherwise
3. Backend `langgraph.json` maps:
   - graph `agent` -> `./src/agent/graph.py:graph`
   - HTTP app -> `./src/agent/app.py:app`
4. Graph executes node chain:
   - `initialize -> think -> implement -> aggregate -> (think|finish) -> finish`

### Node responsibilities

- **initialize** (`nodes/initialize/initialize.py`)
  - Loads `.env`, requires `ANTHROPIC_API_KEY`.
  - Starts `PersistentDockerRunner`.
  - Verifies expected files are present in container.

- **think** (`nodes/think.py`)
  - Uses Anthropic model (`claude-opus-4-20250514`) to generate initial strategy ideas or iterative improvements.
  - Stores strategy descriptions/improvement text in graph state.

- **implement** (`nodes/implement.py`)
  - Parallelizes solution processing with `ThreadPoolExecutor`.
  - For each strategy:
    1. Ask LLM for Python strategy code
    2. Upload to runner container (`strategies/strategy-<id>.py`)
    3. Compile (`python -m py_compile ...`)
    4. Evaluate via metrics script (`metrics.py ...`)
  - Pulls JSON results back into graph state.

- **aggregate** (`nodes/aggregate.py`)
  - Builds next iteration candidates from latest results.
  - Sorts by `final_value`, keeps top half.

- **finish** (`nodes/finish.py`)
  - Picks best final solution by `result.final_value`.
  - Stops and cleans runner/container resources.

## Container-backed strategy evaluation path (important)

`PersistentDockerRunner` (`nodes/container/container.py`) dynamically:

1. Copies all files from `nodes/container/data/` into a temp workdir.
2. Builds a throwaway Docker image (`python:3.11-slim`) with `backtrader` + `pandas`.
3. Runs a persistent container mounting that workdir.
4. Uploads generated strategy files into `/app/strategies`.
5. Runs evaluation command calling `metrics.py`.
6. Downloads generated logs/results and tears down image/container at finish.

This means generated strategy execution is **isolated from host Python env** and depends on runner build correctness.

## Static frontend hosting in backend service

`backend/src/agent/app.py` mounts frontend static files under `/app` using `create_frontend_router()`.

- Expects build output at path resolving from app file to `../frontend/dist`.
- If build files missing, it serves a `503` fallback message indicating frontend not built.

`Dockerfile` explicitly copies built frontend dist into `/deps/frontend/dist` to satisfy this path expectation.

---

## 4) Domain-Specific / Team Workflow Observations

No explicit team automation conventions were found for:
- `.github/workflows`
- `.pre-commit-config.yaml`
- `.husky/`
- `.cursor/rules` / `.cursorrules`
- `CLAUDE.md`

Implication: use repository commands/docs as source of truth; do not assume CI-enforced formatting or test gates exist.

Backend README domain note:
- Data context references `QQQ_15min_2023-2025` (see `backend/README.md`).

---

## 5) Key Entry Points & Config Files

## Core entry points

- Graph entry: `backend/src/agent/graph.py` (`graph = workflow.compile(name="invest-agent")`)
- HTTP app/static mount: `backend/src/agent/app.py` (`app.mount("/app", ...)`)
- Frontend boot: `frontend/src/main.tsx`
- Frontend app logic/stream submit: `frontend/src/App.tsx`

## Runtime/config files

- Root guide/setup: `README.md`
- Backend package/runtime declaration: `backend/setup.py`, `backend/langgraph.json`
- Backend env template: `backend/.env.example`
- Frontend scripts/deps: `frontend/package.json`
- Local orchestrator: `Makefile`
- Containerized deployment: `Dockerfile`, `docker-compose.yml`

## Environment variables (observed)

- Backend local/dev docs: `GEMINI_API_KEY` (README)
- Backend runtime code path: `ANTHROPIC_API_KEY` required by initialize node
- Docker Compose runtime: `GEMINI_API_KEY`, `LANGSMITH_API_KEY`, plus Redis/Postgres URIs

When debugging startup failures, check `.env` alignment with actual codepath in `initialize.py`.

---

## 6) Fast Navigation (Where to Change What)

- Change graph control flow/iteration routing:
  - `backend/src/agent/graph.py`, `backend/src/agent/nodes/aggregate.py`
- Change strategy generation prompts/models:
  - `backend/src/agent/nodes/think.py`, `backend/src/agent/nodes/implement.py`
- Change execution sandbox behavior:
  - `backend/src/agent/nodes/container/container.py`
  - `backend/src/agent/nodes/container/data/metrics.py`
- Change frontend submit payload / API URL behavior:
  - `frontend/src/App.tsx`
  - `frontend/src/components/InputForm.tsx`
- Change deployment/static serving:
  - `backend/src/agent/app.py`, `Dockerfile`, `docker-compose.yml`

---

## 7) Practical Validation Checklist (No Test Suite Present)

After backend edits:

```bash
cd backend
pip install .
langgraph dev
```

After frontend edits:

```bash
cd frontend
npm install
npm run lint
npm run build
npm run dev
```

Full-stack smoke test:

```bash
make dev
# Confirm frontend loads and backend stream endpoint is reachable.
```

Production-like smoke test:

```bash
docker build -t gemini-fullstack-langgraph -f Dockerfile .
GEMINI_API_KEY=<key> LANGSMITH_API_KEY=<key> docker-compose up
# Open http://localhost:8123/app/
```

If strategy pipeline fails:
- Verify Docker daemon is running (runner requires local Docker socket access).
- Verify required API key for active code path (`ANTHROPIC_API_KEY` in initialize node).
- Verify container data files exist under `backend/src/agent/nodes/container/data/`.
