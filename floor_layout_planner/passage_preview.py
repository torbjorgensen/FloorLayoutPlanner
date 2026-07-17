from __future__ import annotations

from shapely.geometry import box
from shapely.ops import unary_union

from .models import Candidate, RoomConnection
from .planner import Piece, create_plan


def global_room_polygon(room: dict):
    origin = room.get("origin", {})
    origin_x = float(origin.get("x", 0))
    origin_y = float(origin.get("y", 0))

    rectangles = [
        box(
            origin_x + float(rectangle["x"]),
            origin_y + float(rectangle["y"]),
            origin_x + float(rectangle["x"]) + float(rectangle["width"]),
            origin_y + float(rectangle["y"]) + float(rectangle["height"]),
        )
        for rectangle in room["rectangles"]
    ]

    return unary_union(rectangles)


def passage_polygon(connection: RoomConnection):
    if connection.passage is None:
        return None

    passage = connection.passage

    return box(
        passage.x,
        passage.y,
        passage.x + passage.width,
        passage.y + passage.height,
    )


def create_passage_preview(
    *,
    connection: RoomConnection,
    master_room: dict,
    candidate: Candidate,
    board_length: float,
    board_width: float,
    orientation: str,
    stagger_step: float,
    minimum_piece_length: float,
) -> list[Piece]:
    """
    Forleng masterrommets rad- og bordnett gjennom passasjen.

    Dette er foreløpig en visualisering. Senere bruker den samlede
    prosjekt-solveren samme geometri til faktisk optimalisering.
    """
    passage = passage_polygon(connection)

    if passage is None:
        return []

    room_floor = global_room_polygon(master_room)
    preview_floor = unary_union([room_floor, passage])

    preview_pieces = create_plan(
        floor=preview_floor,
        board_length=board_length,
        board_width=board_width,
        orientation=orientation,
        stagger_step=stagger_step,
        minimum_piece_length=minimum_piece_length,
        base_offset=candidate.base_offset,
        row_offsets=candidate.row_offsets,
        row_width_offset=candidate.row_width_offset,
    )

    result: list[Piece] = []

    for piece in preview_pieces:
        piece_polygon = box(
            piece.x1,
            piece.y1,
            piece.x2,
            piece.y2,
        )

        clipped = piece_polygon.intersection(passage)

        if clipped.is_empty:
            continue

        for polygon in getattr(clipped, "geoms", [clipped]):
            if polygon.geom_type != "Polygon":
                continue

            min_x, min_y, max_x, max_y = polygon.bounds

            result.append(
                Piece(
                    row=piece.row,
                    segment=piece.segment,
                    piece=piece.piece,
                    x1=min_x,
                    x2=max_x,
                    y1=min_y,
                    y2=max_y,
                    length=(
                        max_x - min_x if orientation == "horizontal" else max_y - min_y
                    ),
                    width=(
                        max_y - min_y if orientation == "horizontal" else max_x - min_x
                    ),
                    source_board_index=piece.source_board_index,
                    physical_board_id=piece.physical_board_id,
                    is_full_length=False,
                )
            )

    return result
