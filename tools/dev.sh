#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-$ROOT_DIR/stue_project.json}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8765}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

cleanup() {
    if [[ "${CLEANUP_DONE:-false}" == "true" ]]; then
        return
    fi
    CLEANUP_DONE=true

    # Each service owns a separate process group. Terminating the group also
    # reaches Vite children and Python optimizer workers rather than only the
    # npm/Python wrapper process recorded by this script.
    for pid in "${BACKEND_PID:-}" "${FRONTEND_PID:-}"; do
        if [[ -n "$pid" ]]; then
            kill -TERM -- "-$pid" >/dev/null 2>&1 || true
        fi
    done

    for _attempt in {1..20}; do
        groups_running=false
        for pid in "${BACKEND_PID:-}" "${FRONTEND_PID:-}"; do
            if [[ -n "$pid" ]] && kill -0 -- "-$pid" >/dev/null 2>&1; then
                groups_running=true
            fi
        done
        [[ "$groups_running" == "false" ]] && break
        sleep 0.1
    done

    for pid in "${BACKEND_PID:-}" "${FRONTEND_PID:-}"; do
        if [[ -n "$pid" ]] && kill -0 -- "-$pid" >/dev/null 2>&1; then
            kill -KILL -- "-$pid" >/dev/null 2>&1 || true
        fi
        [[ -n "$pid" ]] && wait "$pid" >/dev/null 2>&1 || true
    done
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$ROOT_DIR/frontend"

if [[ ! -d node_modules ]]; then
    npm install
fi

cd "$ROOT_DIR"

setsid env FRONTEND_DEV_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}" \
    .venv/bin/python laminate_planner.py "$CONFIG_PATH" \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --no-browser &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
setsid env VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://${BACKEND_HOST}:${BACKEND_PORT}}" \
    npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

# Stop the complete stack when either service exits; otherwise a failed
# backend can leave a healthy-looking but unusable Vite process behind.
set +e
wait -n "$BACKEND_PID" "$FRONTEND_PID"
STACK_STATUS=$?
set -e
exit "$STACK_STATUS"
