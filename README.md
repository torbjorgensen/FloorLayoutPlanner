# Floor Layout Planner

A browser-based tool for optimizing laminate-floor layouts across connected rooms.

## Stack

- Backend: Flask + Python laying engine
- Frontend: React + TypeScript + Vite
- Component library: React Bootstrap
- Rendering: HTML canvas with client-side laying simulation
- Live state transport: Socket.IO over WebSocket

## Install

### Backend

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install --no-deps -e .
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
floor-layout-planner stue_project.json
```

If no frontend build exists, Flask returns a setup page telling you to build the frontend or use `tools/dev.sh`.

### Naming compatibility

The canonical Python package is `floor_layout_planner` and the canonical CLI is
`floor-layout-planner`. The old `pergo_planner` import package and
`laminate_planner.py` script remain as deprecated compatibility shims for
existing callers. New code should not use them. API routes, Socket.IO events,
database migration identifiers, project files, and existing environment
variables remain unchanged by the package rename.

## Production with Docker

The production stack builds the React frontend, serves it through Nginx, and
proxies `/api`, `/socket.io`, and `/healthz` to a private backend container.
Only the Nginx port is exposed on the host.

Create a writable output directory, then start the stack:

```bash
mkdir -p planner_output planner_data
docker compose up --build -d
```

Open `http://localhost:8080`. By default, `stue_project.json` is mounted as the
project configuration and generated files are stored in `planner_output/`, so
both survive container replacement. Database-backed projects introduced by the
project-management work are stored in `planner_data/planner.db`.

Use a different project, output directory, or public port with environment
variables:

```bash
PLANNER_CONFIG_FILE=/absolute/path/project.json \
PLANNER_OUTPUT_DIR=/absolute/path/output \
PLANNER_DATA_DIR=/absolute/path/database-directory \
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
tar -czf planner-backup.tar.gz stue_project.json planner_output/ planner_data/
```

Restore by stopping the stack, extracting the archive into the same paths, and
starting Compose again. When custom mount paths are configured, back up those
paths instead.

Docker is not used by `tools/dev.sh` and is not needed for local development.
To exercise database persistence during host development, pass a SQLAlchemy URL
without changing the normal startup command:

```bash
PLANNER_DATABASE_URL=sqlite:///planner.db tools/dev.sh stue_project.json
```

## Project API

Opening the web interface now shows the project dashboard. Projects can be
created, renamed, duplicated, archived, restored, permanently deleted after
archiving, imported from JSON, or exported without editing server files. The
planner uses stable browser routes such as `/projects/<project_id>`; refreshing
one of those routes is supported by both the Flask and Nginx SPA fallbacks.

Database-backed project management is available under `/api/projects`:

- `GET /api/projects` lists active projects; add `?include_archived=true` to
  include archived projects.
- `POST /api/projects` and `POST /api/projects/import` validate and create a
  portable JSON project.
- `GET` and `PATCH /api/projects/<id>` open or update a project.
- `POST /api/projects/<id>/duplicate`, `/archive`, and `/restore` manage its
  lifecycle.
- `GET /api/projects/<id>/export` downloads the portable JSON configuration.
- `DELETE /api/projects/<id>` permanently removes an already archived project.

Every mutation of an existing project requires its current `expected_version`.
Stale updates return HTTP 409 instead of overwriting newer changes.

Live planner clients select a project by passing `project_id` in the Socket.IO
connection auth object. Their initial and subsequent `project_state` events are
then isolated to that project. Commands use the matching project-scoped path:

```text
/api/projects/<project_id>/runtime/room/<room_id>/<action>
/api/projects/<project_id>/runtime/restart-all
```

Generated outputs are stored beneath `planner_data/outputs/<project_id>/`.
Unscoped Socket.IO connections and `/api/room/...` commands remain available
temporarily for compatibility with the original startup-file workflow. Set
`PLANNER_ENABLE_LEGACY_RUNTIME=true` to eagerly start that legacy runtime;
normal dashboard usage starts project runtimes lazily when they are opened.

## Frontend checks

The frontend toolchain requires Node.js 20.19+ or 22.12+.

```bash
cd frontend
npm test -- --run
npm run build
npm run audit
```

## Backend checks

```bash
env PYTHONPATH=$PWD MPLCONFIGDIR=/tmp/mplconfig .venv/bin/pytest
```

## Benchmark / Profile

Optimizer process pools share one global budget equal to the host's logical
CPU count. `optimizer_workers` is a per-job maximum; concurrent room and
transition searches divide the global allowance and never create more worker
processes than that host-wide limit.

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
SOCKETIO_ALLOWED_ORIGINS="https://your-forwarded-host.example" floor-layout-planner stue_project.json
```
