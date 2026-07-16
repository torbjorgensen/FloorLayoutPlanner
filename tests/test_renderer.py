from __future__ import annotations

from pergo_planner.geometry import build_floor_polygon
from pergo_planner.planner import create_plan
from pergo_planner.renderer import plot_plan


def test_plot_plan_creates_non_empty_png(tmp_path) -> None:
    rectangles = [
        {
            "name": "Test room",
            "x": 0,
            "y": 0,
            "width": 2050,
            "height": 480,
        }
    ]
    floor = build_floor_polygon(rectangles, expansion_gap=0)
    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )
    output = tmp_path / "plan.png"

    plot_plan(
        output_path=output,
        floor=floor,
        pieces=pieces,
        rectangles=rectangles,
        orientation="horizontal",
        section_name="Test room",
        minimum_piece_length=300,
    )

    assert output.exists()
    assert output.stat().st_size > 1000
