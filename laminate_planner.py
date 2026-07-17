#!/usr/bin/env python3
"""Deprecated CLI shim for :mod:`floor_layout_planner.cli`."""

from __future__ import annotations

import warnings

from floor_layout_planner.cli import (
    STATE_EVENT,
    StateUpdateEmitter,
    main,
    register_state_socket_handlers,
)

__all__ = [
    "STATE_EVENT",
    "StateUpdateEmitter",
    "register_state_socket_handlers",
]

warnings.warn(
    "laminate_planner.py is deprecated; use floor-layout-planner instead.",
    FutureWarning,
    stacklevel=2,
)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
