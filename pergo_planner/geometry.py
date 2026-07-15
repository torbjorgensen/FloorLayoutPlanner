from __future__ import annotations

from shapely.geometry import Polygon, box
from shapely.ops import unary_union


def build_floor_polygon(rectangles: list[dict], expansion_gap: float) -> Polygon:
    parts = []

    for index, rectangle in enumerate(rectangles, start=1):
        for key in ("x", "y", "width", "height"):
            if key not in rectangle:
                raise ValueError(f"Rektangel {index} mangler '{key}'.")

        x = float(rectangle["x"])
        y = float(rectangle["y"])
        width = float(rectangle["width"])
        height = float(rectangle["height"])

        if width <= 0 or height <= 0:
            raise ValueError(
                f"Rektangel {index} må ha positiv bredde og høyde."
            )

        parts.append(box(x, y, x + width, y + height))

    floor = unary_union(parts)

    if floor.geom_type != "Polygon":
        raise ValueError(
            "Rektanglene må danne ett sammenhengende område. "
            f"Resultatet ble {floor.geom_type}."
        )

    if expansion_gap > 0:
        floor = floor.buffer(-expansion_gap, join_style=2)

        if floor.is_empty:
            raise ValueError(
                "Ekspansjonsfugen er så stor at gulvarealet forsvinner."
            )

        if floor.geom_type != "Polygon":
            raise ValueError(
                "Ekspansjonsfugen delte gulvet i flere deler. "
                "Reduser expansion_gap_mm."
            )

    return floor


def swap_xy_polygon(polygon: Polygon) -> Polygon:
    exterior = [(y, x) for x, y in polygon.exterior.coords]
    holes = [
        [(y, x) for x, y in ring.coords]
        for ring in polygon.interiors
    ]
    return Polygon(exterior, holes)
