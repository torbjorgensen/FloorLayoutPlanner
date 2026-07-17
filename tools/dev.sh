#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-$ROOT_DIR/stue_project.json}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8765}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

cleanup() {
    if [[ -n "${BACKEND_PID:-}" ]]; then
        kill "$BACKEND_PID" >/dev/null 2>&1 || true
    fi
    if [[ -n "${FRONTEND_PID:-}" ]]; then
        kill "$FRONTEND_PID" >/dev/null 2>&1 || true
    fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR/frontend"

if [[ ! -d node_modules ]]; then
    npm install
fi

cd "$ROOT_DIR"

FRONTEND_DEV_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}" \
    .venv/bin/python laminate_planner.py "$CONFIG_PATH" \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --no-browser &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

wait "$FRONTEND_PID"
