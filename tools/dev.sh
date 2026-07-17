#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-$ROOT_DIR/stue_project.json}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8765}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

FRONTEND_NPM=(npm)
NODE_VERSION="$(node --version 2>/dev/null || true)"
NODE_VERSION="${NODE_VERSION#v}"
NODE_MAJOR="${NODE_VERSION%%.*}"
NODE_REMAINDER="${NODE_VERSION#*.}"
NODE_MINOR="${NODE_REMAINDER%%.*}"

if ! {
    [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]]
    [[ "$NODE_MINOR" =~ ^[0-9]+$ ]]
    (( NODE_MAJOR > 22 || NODE_MAJOR == 22 && NODE_MINOR >= 12 || NODE_MAJOR == 20 && NODE_MINOR >= 19 ))
}; then
    if ! command -v npx >/dev/null 2>&1; then
        echo "Frontend development requires Node.js 20.19+ or 22.12+." >&2
        echo "Install a supported Node.js version and rerun tools/dev.sh." >&2
        exit 1
    fi

    NPM_CLI_PATH="$(readlink -f "$(command -v npm)")"
    FRONTEND_NPM=(npx --yes --package node@22 node "$NPM_CLI_PATH")
    echo "System Node.js ${NODE_VERSION:-not found} is unsupported; using Node.js 22 via npx."
fi

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
    "${FRONTEND_NPM[@]}" install
fi

cd "$ROOT_DIR"

setsid env FRONTEND_DEV_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}" \
    .venv/bin/python -m floor_layout_planner.cli "$CONFIG_PATH" \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --no-browser &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
setsid env VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://${BACKEND_HOST}:${BACKEND_PORT}}" \
    "${FRONTEND_NPM[@]}" run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

# Stop the complete stack when either service exits; otherwise a failed
# backend can leave a healthy-looking but unusable Vite process behind.
set +e
wait -n "$BACKEND_PID" "$FRONTEND_PID"
STACK_STATUS=$?
set -e
exit "$STACK_STATUS"
