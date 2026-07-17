#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
BENCHMARK_TOOL="$ROOT_DIR/tools/benchmark_engine.py"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Missing venv python: $VENV_PYTHON" >&2
    exit 1
fi

CONFIG="${CONFIG:-$ROOT_DIR/stue_project.json}"
MODE="${MODE:-plan}"
REPEAT="${REPEAT:-20}"
SAMPLE_SIZE="${SAMPLE_SIZE:-10}"
PROFILE_SORT="${PROFILE_SORT:-cumtime}"
PROFILE_TOP="${PROFILE_TOP:-20}"

ARGS=(
    "$BENCHMARK_TOOL"
    "$CONFIG"
    --mode "$MODE"
    --repeat "$REPEAT"
    --sample-size "$SAMPLE_SIZE"
    --profile-sort "$PROFILE_SORT"
    --profile-top "$PROFILE_TOP"
)

if [[ -n "${ROOM:-}" ]]; then
    ARGS+=(--room "$ROOM")
fi

if [[ -n "${COMPARE_CONFIG:-}" ]]; then
    ARGS+=(--compare-config "$COMPARE_CONFIG")
fi

if [[ "${PROFILE:-0}" == "1" ]]; then
    ARGS+=(--profile)
fi

if [[ -n "${PROFILE_OUTPUT:-}" ]]; then
    ARGS+=(--profile-output "$PROFILE_OUTPUT")
fi

if [[ $# -gt 0 ]]; then
    ARGS+=("$@")
fi

echo "Running benchmark tool with:"
printf '  %q' "$VENV_PYTHON" "${ARGS[@]}"
echo

env PYTHONPATH="$ROOT_DIR" "$VENV_PYTHON" "${ARGS[@]}"
