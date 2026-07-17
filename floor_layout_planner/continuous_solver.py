from __future__ import annotations

from dataclasses import asdict
from typing import Any

from shapely.affinity import translate
from shapely.geometry import (
    GeometryCollection,
    MultiPolygon,
    Polygon,
    box,
)
from shapely.ops import unary_union

from .geometry import build_floor_polygon
from .models import Candidate, CutPlan, RoomConnection
from .planner import Piece
from .validation import length_meets_minimum

_GEOMETRY_LIMIT = 1_000_000_000.0
_EPSILON = 1e-6


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
        local,
        xoff=float(origin.get("x", 0)),
        yoff=float(origin.get("y", 0)),
    )


def passage_polygon(connection: RoomConnection) -> Polygon:
    if connection.passage is None:
        raise ValueError("continuous_then_cut krever passage.")

    passage = connection.passage

    return box(
        passage.x,
        passage.y,
        passage.x + passage.width,
        passage.y + passage.height,
    )


def build_continuous_floor(
    room_a: dict[str, Any],
    room_b: dict[str, Any],
    connection: RoomConnection,
    expansion_gap_mm: float,
) -> Polygon:
    """
    Build the temporary laying surface.

    The optimizer uses one connected polygon so both rooms share the exact
    same board grid, just as when laminate is laid through the opening before
    the expansion joint is sawn.

    The finished result is split back into two room layouts by
    split_candidate_at_cut().
    """
    raw = unary_union(
        [
            global_room_polygon(room_a),
            passage_polygon(connection),
            global_room_polygon(room_b),
        ]
    )

    if raw.geom_type != "Polygon":
        raise ValueError(
            f"Connection '{connection.connection_id}' does not form one "
            "connected floor area. Check the passage coordinates."
        )

    floor = raw.buffer(
        -float(expansion_gap_mm),
        join_style=2,
    )

    if floor.is_empty or floor.geom_type != "Polygon":
        raise ValueError("The expansion gap makes the continuous floor area invalid.")

    return floor


def _cut_strip(
    connection: RoomConnection,
    position: float,
) -> Polygon:
    assert connection.passage is not None
    assert connection.cut is not None

    passage = connection.passage
    half = connection.cut.gap_width_mm / 2

    if connection.cut.axis == "y":
        return box(
            passage.x,
            position - half,
            passage.x + passage.width,
            position + half,
        )

    return box(
        position - half,
        passage.y,
        position + half,
        passage.y + passage.height,
    )


def _candidate_positions(
    candidate: Candidate,
    connection: RoomConnection,
) -> list[float]:
    assert connection.passage is not None
    assert connection.cut is not None

    passage = connection.passage
    cut = connection.cut

    low = (
        (passage.x if cut.axis == "x" else passage.y)
        + cut.edge_clearance_mm
        + cut.gap_width_mm / 2
    )

    high = (
        (passage.x + passage.width if cut.axis == "x" else passage.y + passage.height)
        - cut.edge_clearance_mm
        - cut.gap_width_mm / 2
    )

    values: set[float] = set()
    value = low

    while value <= high + _EPSILON:
        values.add(round(value, 6))
        value += cut.search_step_mm

    values.add(round((low + high) / 2, 6))

    if cut.prefer_existing_joint:
        for piece in candidate.pieces:
            boundaries = (
                (piece.x1, piece.x2) if cut.axis == "x" else (piece.y1, piece.y2)
            )

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
    """
    Score the finished two-room result after the expansion strip is removed.

    Pieces crossing the strip are split. Both resulting fragments are included
    in the short-piece and narrow-piece penalties.
    """
    strip = _cut_strip(connection, position)

    cut_boards = 0
    short = 0
    very_short = 0
    narrow = 0
    very_narrow = 0
    shortest = float("inf")
    narrowest = float("inf")
    natural_joint = True

    for piece in candidate.pieces:
        geometry = box(
            piece.x1,
            piece.y1,
            piece.x2,
            piece.y2,
        )

        if geometry.intersection(strip).area <= 1e-8:
            continue

        cut_boards += 1

        if connection.cut and connection.cut.axis == "x":
            if piece.x1 + _EPSILON < position < piece.x2 - _EPSILON:
                natural_joint = False
        elif piece.y1 + _EPSILON < position < piece.y2 - _EPSILON:
            natural_joint = False

        remaining = geometry.difference(strip)

        for part in _polygon_parts(remaining):
            min_x, min_y, max_x, max_y = part.bounds

            length = max_x - min_x if orientation == "horizontal" else max_y - min_y
            width = max_y - min_y if orientation == "horizontal" else max_x - min_x

            shortest = min(shortest, length)
            narrowest = min(narrowest, width)

            if not length_meets_minimum(length, minimum_piece_length):
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
        gap_width_mm=(connection.cut.gap_width_mm if connection.cut else 0.0),
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
        for position in _candidate_positions(
            candidate,
            connection,
        )
    ]

    # A valid expansion-gap position always outranks one that creates an
    # undersized fragment, regardless of advisory row-width penalties.
    return min(
        plans,
        key=lambda plan: (plan.short_fragments > 0, plan.score),
    )


def continuous_candidate_score(
    candidate: Candidate,
    cut_plan: CutPlan,
) -> tuple:
    return (
        *cut_plan.score[:6],
        *candidate.score,
        *cut_plan.score[6:],
    )


def _room_side(
    room: dict[str, Any],
    axis: str,
    cut_position: float,
) -> str:
    centroid = global_room_polygon(room).centroid
    coordinate = centroid.x if axis == "x" else centroid.y

    return "low" if coordinate < cut_position else "high"


def _side_clip(
    *,
    axis: str,
    side: str,
    cut_position: float,
    gap_width_mm: float,
) -> Polygon:
    half = gap_width_mm / 2

    if axis == "x":
        if side == "low":
            return box(
                -_GEOMETRY_LIMIT,
                -_GEOMETRY_LIMIT,
                cut_position - half,
                _GEOMETRY_LIMIT,
            )

        return box(
            cut_position + half,
            -_GEOMETRY_LIMIT,
            _GEOMETRY_LIMIT,
            _GEOMETRY_LIMIT,
        )

    if side == "low":
        return box(
            -_GEOMETRY_LIMIT,
            -_GEOMETRY_LIMIT,
            _GEOMETRY_LIMIT,
            cut_position - half,
        )

    return box(
        -_GEOMETRY_LIMIT,
        cut_position + half,
        _GEOMETRY_LIMIT,
        _GEOMETRY_LIMIT,
    )


def _piece_from_polygon(
    *,
    source: Piece,
    polygon: Polygon,
    orientation: str,
    piece_number: int,
) -> Piece:
    min_x, min_y, max_x, max_y = polygon.bounds

    return Piece(
        row=source.row,
        segment=source.segment,
        piece=piece_number,
        x1=min_x,
        x2=max_x,
        y1=min_y,
        y2=max_y,
        length=(max_x - min_x if orientation == "horizontal" else max_y - min_y),
        width=(max_y - min_y if orientation == "horizontal" else max_x - min_x),
        source_board_index=source.source_board_index,
        physical_board_id=source.physical_board_id,
        is_full_length=False,
    )


def _clip_candidate_pieces(
    *,
    candidate: Candidate,
    clip_geometry: Polygon,
    orientation: str,
) -> list[Piece]:
    result: list[Piece] = []

    for source in candidate.pieces:
        geometry = box(
            source.x1,
            source.y1,
            source.x2,
            source.y2,
        )
        clipped = geometry.intersection(clip_geometry)

        for index, part in enumerate(
            _polygon_parts(clipped),
            start=1,
        ):
            if part.area <= 1e-8:
                continue

            result.append(
                _piece_from_polygon(
                    source=source,
                    polygon=part,
                    orientation=orientation,
                    piece_number=index,
                )
            )

    return result


def split_candidate_at_cut(
    *,
    candidate: Candidate,
    room_a: dict[str, Any],
    room_b: dict[str, Any],
    connection: RoomConnection,
    cut_plan: CutPlan,
    orientation: str,
) -> dict[str, list[Piece]]:
    """
    Convert the temporary continuous laying plan into two finished room plans.

    Both sides retain the exact same board grid and source-board indices, but
    no rendered piece crosses the expansion joint. The passage is divided at
    the selected cut position, so the finished UI still behaves as two rooms.
    """
    side_a = _room_side(
        room_a,
        cut_plan.axis,
        cut_plan.position_mm,
    )
    side_b = _room_side(
        room_b,
        cut_plan.axis,
        cut_plan.position_mm,
    )

    if side_a == side_b:
        raise ValueError(
            f"Connection '{connection.connection_id}' places both "
            "rooms on the same side of the saw cut. Check passage and cut.axis."
        )

    clips = {
        connection.room_a: _side_clip(
            axis=cut_plan.axis,
            side=side_a,
            cut_position=cut_plan.position_mm,
            gap_width_mm=cut_plan.gap_width_mm,
        ),
        connection.room_b: _side_clip(
            axis=cut_plan.axis,
            side=side_b,
            cut_position=cut_plan.position_mm,
            gap_width_mm=cut_plan.gap_width_mm,
        ),
    }

    return {
        room_id: _clip_candidate_pieces(
            candidate=candidate,
            clip_geometry=clip_geometry,
            orientation=orientation,
        )
        for room_id, clip_geometry in clips.items()
    }


def cut_plan_payload(
    plan: CutPlan,
) -> dict[str, Any]:
    payload = asdict(plan)
    payload["score"] = list(plan.score)

    return payload
