"""Backend logging configuration shared by development and production."""

from __future__ import annotations

import logging
import os


def configure_backend_logging() -> None:
    """Configure concise process logs without replacing host-provided handlers."""
    level_name = os.environ.get("PLANNER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
    )
    logging.getLogger("floor_layout_planner").setLevel(level)
