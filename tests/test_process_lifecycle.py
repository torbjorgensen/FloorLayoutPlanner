from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def available_port() -> int:
    """Reserve an ephemeral loopback port long enough to learn its number."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_listener(port: int, timeout: float = 8.0) -> None:
    """Wait until the test backend accepts loopback connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"Backend did not listen on port {port} within {timeout}s")


def test_backend_port_is_reusable_immediately_after_termination(tmp_path: Path) -> None:
    """Optimizer children must not inherit and retain the HTTP listener."""
    config_path = tmp_path / "lifecycle.json"
    config_path.write_text(
        json.dumps(
            {
                "project_name": "Lifecycle",
                "board": {"length_mm": 2050, "width_mm": 240},
                "settings": {
                    "optimizer_workers": 2,
                    "optimization_step_mm": 20,
                    "row_width_optimization_step_mm": 10,
                    "local_optimize_top_n": 2,
                    "frame_delay_ms": 0,
                },
                "rooms": [
                    {
                        "id": "room",
                        "name": "Room",
                        "rectangles": [{"x": 0, "y": 0, "width": 4000, "height": 2400}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    port = available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "laminate_planner.py",
            str(config_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-browser",
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    try:
        wait_for_listener(port)
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)

        # SO_REUSEADDR is intentionally not used: the assertion verifies that
        # no live process still owns the listening socket.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
