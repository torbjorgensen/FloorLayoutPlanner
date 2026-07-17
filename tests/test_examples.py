from __future__ import annotations

import json
from pathlib import Path

import pytest

from floor_layout_planner.geometry import build_floor_polygon

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PROJECT_ROOT / "examples"


@pytest.mark.parametrize(
    "filename",
    ["example_layout.json", "example_project.json"],
)
def test_example_json_is_valid(filename: str) -> None:
    path = EXAMPLES_DIR / filename

    assert path.exists(), f"Mangler eksempelkonfigurasjon: {path}"

    with path.open(encoding="utf-8") as file:
        config = json.load(file)

    assert isinstance(config, dict)


def test_all_example_project_rooms_build_valid_geometry() -> None:
    path = EXAMPLES_DIR / "example_project.json"

    assert path.exists(), f"Mangler eksempelkonfigurasjon: {path}"

    with path.open(encoding="utf-8") as file:
        config = json.load(file)

    project_gap = float(config.get("settings", {}).get("expansion_gap_mm", 0))

    for room in config["rooms"]:
        room_gap = float(
            room.get("settings", {}).get(
                "expansion_gap_mm",
                project_gap,
            )
        )

        floor = build_floor_polygon(
            room["rectangles"],
            expansion_gap=room_gap,
        )

        assert not floor.is_empty
        assert floor.area > 0
