from __future__ import annotations

from shapely.geometry import Polygon, box
from shapely.ops import unary_union


def build_floor_polygon(rectangles: list[dict], expansion_gap: float) -> Polygon:
    parts = []

    for index, rectangle in enumerate(rectangles, start=1):
        for key in ("x", "y", "width", "height"):
            if key not in rectangle:
                raise ValueError(f"Rectangle {index} is missing '{key}'.")

        x = float(rectangle["x"])
        y = float(rectangle["y"])
        width = float(rectangle["width"])
        height = float(rectangle["height"])

        if width <= 0 or height <= 0:
            raise ValueError(f"Rectangle {index} must have positive width and height.")

        parts.append(box(x, y, x + width, y + height))

    floor = unary_union(parts)

    if floor.geom_type != "Polygon":
        raise ValueError(
            "The rectangles must form one connected area. "
            f"The result was {floor.geom_type}."
        )

    if expansion_gap > 0:
        floor = floor.buffer(-expansion_gap, join_style=2)

        if floor.is_empty:
            raise ValueError(
                "The expansion gap is so large that the floor area disappears."
            )

        if floor.geom_type != "Polygon":
            raise ValueError(
                "The expansion gap split the floor into multiple parts. "
                "Reduce expansion_gap_mm."
            )

    return floor


def swap_xy_polygon(polygon: Polygon) -> Polygon:
    exterior = [(y, x) for x, y in polygon.exterior.coords]
    holes = [[(y, x) for x, y in ring.coords] for ring in polygon.interiors]
    return Polygon(exterior, holes)
