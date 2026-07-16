from __future__ import annotations

from dataclasses import asdict
from typing import Any

from shapely.affinity import translate
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.ops import unary_union

from .geometry import build_floor_polygon
from .models import Candidate, CutPlan, RoomConnection


def _polygon_parts(geometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        result: list[Polygon] = []
        for item in geometry.geoms:
            result.extend(_polygon_parts(item))
        return result
    return []


def global_room_polygon(room: dict[str, Any]) -> Polygon:
    local = build_floor_polygon(room["rectangles"], 0)
    origin = room.get("origin", {})
    return translate(
        local, xoff=float(origin.get("x", 0)), yoff=float(origin.get("y", 0))
    )


def passage_polygon(connection: RoomConnection) -> Polygon:
    if connection.passage is None:
        raise ValueError("continuous_then_cut krever passage.")
    p = connection.passage
    return box(p.x, p.y, p.x + p.width, p.y + p.height)


def build_continuous_floor(
    room_a: dict[str, Any],
    room_b: dict[str, Any],
    connection: RoomConnection,
    expansion_gap_mm: float,
) -> Polygon:
    raw = unary_union(
        [
            global_room_polygon(room_a),
            passage_polygon(connection),
            global_room_polygon(room_b),
        ]
    )
    if raw.geom_type != "Polygon":
        raise ValueError(
            f"Forbindelsen '{
                connection.connection_id
            }' lager ikke ett sammenhengende gulvareal. "
            "Kontroller passage-koordinatene."
        )
    floor = raw.buffer(-float(expansion_gap_mm), join_style=2)
    if floor.is_empty or floor.geom_type != "Polygon":
        raise ValueError("Ekspansjonsfugen gjør det kontinuerlige gulvarealet ugyldig.")
    return floor


def _cut_strip(connection: RoomConnection, position: float) -> Polygon:
    assert connection.passage is not None and connection.cut is not None
    p = connection.passage
    half = connection.cut.gap_width_mm / 2
    if connection.cut.axis == "y":
        return box(p.x, position - half, p.x + p.width, position + half)
    return box(position - half, p.y, position + half, p.y + p.height)


def _candidate_positions(
    candidate: Candidate, connection: RoomConnection
) -> list[float]:
    assert connection.passage is not None and connection.cut is not None
    p = connection.passage
    c = connection.cut
    low = (p.x if c.axis == "x" else p.y) + c.edge_clearance_mm + c.gap_width_mm / 2
    high = (
        (p.x + p.width if c.axis == "x" else p.y + p.height)
        - c.edge_clearance_mm
        - c.gap_width_mm / 2
    )
    values: set[float] = set()
    value = low
    while value <= high + 1e-6:
        values.add(round(value, 6))
        value += c.search_step_mm
    values.add(round((low + high) / 2, 6))
    if c.prefer_existing_joint:
        for piece in candidate.pieces:
            boundaries = (piece.x1, piece.x2) if c.axis == "x" else (piece.y1, piece.y2)
            for boundary in boundaries:
                if low <= boundary <= high:
                    values.add(round(boundary, 6))
    return sorted(values)


def evaluate_cut_position(
    candidate: Candidate,
    connection: RoomConnection,
    position: float,
    orientation: str,
    minimum_piece_length: float,
    minimum_row_width: float,
    preferred_minimum_row_width: float,
) -> CutPlan:
    strip = _cut_strip(connection, position)
    cut_boards = 0
    short = very_short = narrow = very_narrow = 0
    shortest = float("inf")
    narrowest = float("inf")
    natural_joint = True

    for piece in candidate.pieces:
        geometry = box(piece.x1, piece.y1, piece.x2, piece.y2)
        if geometry.intersection(strip).area <= 1e-8:
            continue
        cut_boards += 1
        if connection.cut and connection.cut.axis == "x":
            if piece.x1 + 1e-6 < position < piece.x2 - 1e-6:
                natural_joint = False
        else:
            if piece.y1 + 1e-6 < position < piece.y2 - 1e-6:
                natural_joint = False
        remaining = geometry.difference(strip)
        for part in _polygon_parts(remaining):
            min_x, min_y, max_x, max_y = part.bounds
            length = max_x - min_x if orientation == "horizontal" else max_y - min_y
            width = max_y - min_y if orientation == "horizontal" else max_x - min_x
            shortest = min(shortest, length)
            narrowest = min(narrowest, width)
            if length < minimum_piece_length:
                short += 1
            if length < min(100.0, minimum_piece_length):
                very_short += 1
            if width < preferred_minimum_row_width:
                narrow += 1
            if width < minimum_row_width:
                very_narrow += 1

    if shortest == float("inf"):
        shortest = 0.0
    if narrowest == float("inf"):
        narrowest = 0.0
    assert connection.passage is not None
    center = (
        connection.passage.x + connection.passage.width / 2
        if connection.cut and connection.cut.axis == "x"
        else connection.passage.y + connection.passage.height / 2
    )
    center_distance = abs(position - center)
    method = "natural_joint" if natural_joint else "saw_cut"
    score = (
        very_narrow,
        very_short,
        narrow,
        short,
        0 if method == "natural_joint" else 1,
        cut_boards,
        center_distance,
        -narrowest,
        -shortest,
    )
    return CutPlan(
        connection_id=connection.connection_id,
        axis=connection.cut.axis if connection.cut else "x",
        position_mm=position,
        gap_width_mm=connection.cut.gap_width_mm if connection.cut else 0.0,
        method=method,
        cut_boards=cut_boards,
        short_fragments=short,
        very_short_fragments=very_short,
        narrow_fragments=narrow,
        very_narrow_fragments=very_narrow,
        shortest_fragment_mm=shortest,
        narrowest_fragment_mm=narrowest,
        center_distance_mm=center_distance,
        score=score,
    )


def best_cut_plan(
    candidate: Candidate,
    connection: RoomConnection,
    orientation: str,
    minimum_piece_length: float,
    minimum_row_width: float,
    preferred_minimum_row_width: float,
) -> CutPlan:
    plans = [
        evaluate_cut_position(
            candidate,
            connection,
            position,
            orientation,
            minimum_piece_length,
            minimum_row_width,
            preferred_minimum_row_width,
        )
        for position in _candidate_positions(candidate, connection)
    ]
    return min(plans, key=lambda plan: plan.score)


def continuous_candidate_score(candidate: Candidate, cut_plan: CutPlan) -> tuple:
    return (*cut_plan.score[:6], *candidate.score, *cut_plan.score[6:])


def cut_plan_payload(plan: CutPlan) -> dict[str, Any]:
    payload = asdict(plan)
    payload["score"] = list(plan.score)
    return payload
