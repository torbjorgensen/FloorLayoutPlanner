# Floor Layout Planner

A browser-based tool for optimizing laminate-floor layouts across connected rooms.

## Stack

- Backend: Flask + Python laying engine
- Frontend: React + TypeScript + Vite
- Component library: Material UI
- Rendering: HTML canvas with client-side laying simulation
- Live state transport: Socket.IO over WebSocket

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

This is the recommended development workflow. It runs directly on the host,
supports Vite hot reload, and does not require Docker.

### Backend only

Serves the built frontend from `frontend/dist`:

```bash
cd frontend
npm run build
cd ..
python laminate_planner.py stue_project.json
```

If no frontend build exists, Flask returns a setup page telling you to build the frontend or use `tools/dev.sh`.

## Production with Docker

The production stack builds the React frontend, serves it through Nginx, and
proxies `/api`, `/socket.io`, and `/healthz` to a private backend container.
Only the Nginx port is exposed on the host.

Create a writable output directory, then start the stack:

```bash
mkdir -p planner_output
docker compose up --build -d
```

Open `http://localhost:8080`. By default, `stue_project.json` is mounted as the
project configuration and generated files are stored in `planner_output/`, so
both survive container replacement.

Use a different project, output directory, or public port with environment
variables:

```bash
PLANNER_CONFIG_FILE=/absolute/path/project.json \
PLANNER_OUTPUT_DIR=/absolute/path/output \
PLANNER_PORT=8088 \
docker compose up --build -d
```

The backend runs as UID/GID 1000 by default so files normally remain editable
by the host user. Override that mapping when your account uses different IDs:

```bash
PLANNER_UID=$(id -u) PLANNER_GID=$(id -g) docker compose up --build -d
```

The project file and output directory must be writable by that user. Stop the
deployment with:

```bash
docker compose down
```

The Nginx setup is same-origin by default and needs no CORS configuration. If
another trusted proxy or public origin connects directly to the backend, set a
comma-separated allowlist such as
`SOCKETIO_ALLOWED_ORIGINS=https://planner.example.com`.

Common production operations:

```bash
# Follow logs from both services.
docker compose logs --follow

# Rebuild and replace containers after updating the checkout.
docker compose up --build --detach --remove-orphans

# Back up the persisted project and generated output.
tar -czf planner-backup.tar.gz stue_project.json planner_output/
```

Restore by stopping the stack, extracting the archive into the same paths, and
starting Compose again. When custom mount paths are configured, back up those
paths instead.

Docker is not used by `tools/dev.sh` and is not needed for local development.

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

For a frontend that connects directly to Flask instead of using the Vite proxy, configure allowed Socket.IO origins explicitly:

```bash
SOCKETIO_ALLOWED_ORIGINS="https://your-forwarded-host.example" python laminate_planner.py stue_project.json
```
