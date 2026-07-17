from __future__ import annotations

from floor_layout_planner.connections import parse_connections
from floor_layout_planner.continuous_solver import (
    best_cut_plan,
    build_continuous_floor,
    continuous_candidate_score,
)
from floor_layout_planner.models import Candidate
from floor_layout_planner.planner import create_plan


def config():
    return {
        "rooms": [
            {
                "id": "a",
                "name": "A",
                "origin": {"x": 0, "y": 0},
                "rectangles": [{"x": 0, "y": 0, "width": 3000, "height": 2000}],
            },
            {
                "id": "b",
                "name": "B",
                "origin": {"x": 0, "y": 2120},
                "rectangles": [{"x": 0, "y": 0, "width": 3000, "height": 1800}],
            },
        ],
        "connections": [
            {
                "id": "a_b",
                "room_a": "a",
                "room_b": "b",
                "type": "continuous_then_cut",
                "opening": {"x1": 1000, "y1": 2000, "x2": 2000, "y2": 2000},
                "passage": {"x": 1000, "y": 2000, "width": 1000, "height": 120},
                "cut": {
                    "axis": "y",
                    "gap_width_mm": 5,
                    "edge_clearance_mm": 15,
                    "search_step_mm": 5,
                },
            }
        ],
    }


def test_continuous_floor_is_connected_and_contains_passage():
    cfg = config()
    connection = parse_connections(cfg)[0]
    floor = build_continuous_floor(cfg["rooms"][0], cfg["rooms"][1], connection, 5)
    assert floor.geom_type == "Polygon"
    assert floor.area > 0


def test_cut_plan_is_in_allowed_passage_range():
    cfg = config()
    connection = parse_connections(cfg)[0]
    floor = build_continuous_floor(cfg["rooms"][0], cfg["rooms"][1], connection, 5)
    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        base_offset=0,
        row_width_offset=0,
    )
    candidate = Candidate(
        attempt=1,
        total_attempts=1,
        phase="coarse",
        base_offset=0,
        row_width_offset=0,
        pieces=pieces,
        short_count=0,
        very_short_count=0,
        shortest_piece=300,
        joint_violations=0,
        narrow_row_count=0,
        very_narrow_row_count=0,
        narrowest_row_width=100,
        row_offsets={},
        score=(0, 0, 0, 0, 0, -100, -300),
        timings={},
    )
    plan = best_cut_plan(candidate, connection, "horizontal", 300, 60, 100)
    assert 2020 <= plan.position_mm <= 2100
    assert plan.gap_width_mm == 5
    assert continuous_candidate_score(candidate, plan)
