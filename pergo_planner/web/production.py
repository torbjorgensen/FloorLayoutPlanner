"""WSGI entry point for the production container."""

from __future__ import annotations

import atexit
import os
from pathlib import Path

from pergo_planner.web.app import create_app


def _config_path() -> Path:
    """Resolve the project file mounted into the production container."""
    return Path(os.environ.get("PLANNER_CONFIG_PATH", "/data/project.json"))


# Gunicorn imports this module once in its sole worker. The planner keeps live
# optimization state in memory, so running multiple WSGI workers is unsafe.
runtime = create_app(_config_path())
app = runtime.app
atexit.register(runtime.shutdown)
