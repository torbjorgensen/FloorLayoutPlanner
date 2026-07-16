from __future__ import annotations

import matplotlib
import pytest

from pergo_planner.geometry import build_floor_polygon

matplotlib.use("Agg")


@pytest.fixture
def simple_rectangles() -> list[dict]:
    return [
        {
            "name": "Simple room",
            "x": 0,
            "y": 0,
            "width": 2050,
            "height": 480,
        }
    ]


@pytest.fixture
def l_rectangles() -> list[dict]:
    return [
        {"x": 0, "y": 0, "width": 3000, "height": 2000},
        {"x": 0, "y": 2000, "width": 1000, "height": 1000},
    ]


@pytest.fixture
def l_floor(l_rectangles):
    return build_floor_polygon(l_rectangles, expansion_gap=0)
