"""Deprecated compatibility package; use :mod:`floor_layout_planner`."""

from __future__ import annotations

import warnings

import floor_layout_planner as _canonical
from floor_layout_planner import *  # noqa: F403

warnings.warn(
    "pergo_planner is deprecated; import floor_layout_planner instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Let legacy submodule imports resolve the canonical source tree. New
# application code imports only floor_layout_planner, so this path exists
# solely for callers migrating from the old package name.
__path__ = _canonical.__path__
__all__ = _canonical.__all__
