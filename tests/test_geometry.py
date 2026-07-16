from __future__ import annotations

import pytest

from pergo_planner.geometry import build_floor_polygon, swap_xy_polygon


def test_single_rectangle_area() -> None:
    floor = build_floor_polygon(
        [{"x": 0, "y": 0, "width": 5000, "height": 4000}],
        expansion_gap=0,
    )

    assert floor.area == pytest.approx(20_000_000)


def test_l_shape_area(l_rectangles) -> None:
    floor = build_floor_polygon(l_rectangles, expansion_gap=0)

    assert floor.area == pytest.approx(7_000_000)
    assert floor.geom_type == "Polygon"


def test_expansion_gap_reduces_rectangle_on_all_sides() -> None:
    floor = build_floor_polygon(
        [{"x": 0, "y": 0, "width": 1000, "height": 800}],
        expansion_gap=10,
    )

    assert floor.bounds == pytest.approx((10, 10, 990, 790))
    assert floor.area == pytest.approx(980 * 780)


def test_disconnected_rectangles_are_rejected() -> None:
    with pytest.raises(ValueError, match="sammenhengende"):
        build_floor_polygon(
            [
                {"x": 0, "y": 0, "width": 1000, "height": 1000},
                {"x": 2000, "y": 0, "width": 1000, "height": 1000},
            ],
            expansion_gap=0,
        )


def test_swap_xy_preserves_area_and_swaps_bounds() -> None:
    floor = build_floor_polygon(
        [{"x": 100, "y": 200, "width": 1000, "height": 500}],
        expansion_gap=0,
    )

    swapped = swap_xy_polygon(floor)

    assert swapped.area == pytest.approx(floor.area)
    assert swapped.bounds == pytest.approx((200, 100, 700, 1100))
