from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pytest

from floor_layout_planner.geometry import build_floor_polygon

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


@pytest.fixture
def stue_project_config() -> dict:
    path = Path(__file__).resolve().parent.parent / "stue_project.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def hallway_room(stue_project_config: dict) -> dict:
    return next(
        room for room in stue_project_config["rooms"] if room["name"] == "Hallway"
    )


@pytest.fixture
def hallway_settings(stue_project_config: dict, hallway_room: dict) -> dict:
    return {
        **stue_project_config.get("settings", {}),
        **hallway_room.get("settings", {}),
    }


@pytest.fixture
def hallway_floor(hallway_room: dict, hallway_settings: dict):
    return build_floor_polygon(
        hallway_room["rectangles"],
        expansion_gap=float(hallway_settings["expansion_gap_mm"]),
    )
