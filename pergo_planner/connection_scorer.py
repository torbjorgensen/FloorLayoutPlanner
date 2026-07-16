from __future__ import annotations

from typing import Any

from .models import Candidate, RoomConnection


def _circular_distance(
    first: float,
    second: float,
    period: float,
) -> float:
    """Returner korteste avstand mellom to posisjoner i et periodisk rutenett."""
    difference = abs(first - second) % period
    return min(difference, period - difference)


def room_grid_phase(
    *,
    room: dict[str, Any],
    candidate: Candidate,
    board_width: float,
    orientation: str,
    local_floor_min_x: float,
    local_floor_min_y: float,
) -> float:
    """
    Beregn radnettets globale fase.

    Horisontale bord forskyves på Y-aksen.
    Vertikale bord forskyves på X-aksen.
    """
    origin = room.get("origin", {})
    origin_x = float(origin.get("x", 0))
    origin_y = float(origin.get("y", 0))

    if orientation == "horizontal":
        grid_origin = origin_y + local_floor_min_y - candidate.row_width_offset
    elif orientation == "vertical":
        grid_origin = origin_x + local_floor_min_x - candidate.row_width_offset
    else:
        raise ValueError("orientation må være 'horizontal' eller 'vertical'.")

    return grid_origin % board_width


def score_row_alignment(
    *,
    connection: RoomConnection,
    room_a: dict[str, Any],
    candidate_a: Candidate,
    orientation_a: str,
    floor_bounds_a: tuple[float, float, float, float],
    room_b: dict[str, Any],
    candidate_b: Candidate,
    orientation_b: str,
    floor_bounds_b: tuple[float, float, float, float],
    board_width: float,
) -> dict[str, float | bool | str]:
    if orientation_a != orientation_b:
        return {
            "available": False,
            "reason": "Rom med forskjellig leggeretning kan ikke radjusteres.",
            "row_mismatch_mm": board_width,
            "row_alignment_percent": 0.0,
            "weighted_penalty": board_width * connection.weight,
        }

    phase_a = room_grid_phase(
        room=room_a,
        candidate=candidate_a,
        board_width=board_width,
        orientation=orientation_a,
        local_floor_min_x=floor_bounds_a[0],
        local_floor_min_y=floor_bounds_a[1],
    )
    phase_b = room_grid_phase(
        room=room_b,
        candidate=candidate_b,
        board_width=board_width,
        orientation=orientation_b,
        local_floor_min_x=floor_bounds_b[0],
        local_floor_min_y=floor_bounds_b[1],
    )

    mismatch = _circular_distance(
        phase_a,
        phase_b,
        board_width,
    )

    # Maksimal relevant feil er en halv bordbredde.
    maximum_mismatch = board_width / 2
    alignment_percent = max(
        0.0,
        100.0 * (1.0 - mismatch / maximum_mismatch),
    )

    return {
        "available": True,
        "reason": "",
        "row_mismatch_mm": mismatch,
        "row_alignment_percent": alignment_percent,
        "weighted_penalty": mismatch * connection.weight,
    }
