# Floor Layout Planner

## Stack

- Backend: Flask + Python laying engine
- Frontend: React + TypeScript + Vite
- Component library: Material UI
- Rendering: HTML canvas with client-side laying simulation

## Install

### Backend

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Run

### One command dev stack

Starts Flask on `127.0.0.1:8765` and Vite on `127.0.0.1:5173`:

```bash
tools/dev.sh stue_project.json
```

### Backend only

Serves the built frontend from `frontend/dist`:

```bash
cd frontend
npm run build
cd ..
python laminate_planner.py stue_project.json
```

If no frontend build exists, Flask returns a setup page telling you to build the frontend or use `tools/dev.sh`.

## Frontend checks

```bash
cd frontend
npm test -- --run
npm run build
```

## Backend checks

```bash
env PYTHONPATH=$PWD MPLCONFIGDIR=/tmp/mplconfig .venv/bin/pytest
```

## Benchmark / Profile

Benchmark plan generation for all rooms in a project:

```bash
python tools/benchmark_engine.py stue_project.json --mode plan --repeat 20
```

Benchmark coarse candidate evaluation for one room:

```bash
python tools/benchmark_engine.py stue_project.json --room hallway --mode coarse --sample-size 20
```

Run a `cProfile` capture for one representative refine evaluation:

```bash
python tools/benchmark_engine.py stue_project.json --room hallway --mode refine --profile --profile-output refine.prof
```

Compare two configs and print timing deltas for the same room ids:

```bash
python tools/benchmark_engine.py stue_project.json --compare-config stue_project_optimized.json --room gang --mode plan --repeat 20
```

## Pre-commit checks

Install the hooks once:

```bash
pre-commit install
```

Frontend changes run the Vitest suite and production build automatically. To run every check manually:

```bash
pre-commit run --all-files
```
