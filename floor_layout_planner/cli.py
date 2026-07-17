"""Command-line entry point for the Floor Layout Planner web application."""

from __future__ import annotations

import argparse
import signal
import threading
import webbrowser
from pathlib import Path

from floor_layout_planner.web.app import create_app
from floor_layout_planner.web.sockets import (
    STATE_EVENT,
    StateUpdateEmitter,
    register_state_socket_handlers,
)

__all__ = [
    "STATE_EVENT",
    "StateUpdateEmitter",
    "main",
    "parse_args",
    "register_state_socket_handlers",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Floor Layout Planner with multiple rooms."
    )
    parser.add_argument("config", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = create_app(args.config)
    browser_host = "localhost" if args.host in {"0.0.0.0", "127.0.0.1"} else args.host
    url = f"http://{browser_host}:{args.port}"

    print(f"\nFloor Layout Planner running at: {url}")
    print("Press Ctrl+C to stop the server.")

    if not args.no_browser:
        browser_timer = threading.Timer(1.0, lambda: webbrowser.open(url))
        browser_timer.daemon = True
        browser_timer.start()

    def request_shutdown(_signal_number, _frame) -> None:
        """Turn service-manager termination into normal Python cleanup."""
        raise KeyboardInterrupt

    previous_sigterm = signal.signal(signal.SIGTERM, request_shutdown)
    try:
        runtime.socketio.run(
            runtime.app,
            host=args.host,
            port=args.port,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        runtime.shutdown()


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
