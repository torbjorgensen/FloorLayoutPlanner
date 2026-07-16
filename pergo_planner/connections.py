from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import CutSettings, Opening, Passage, RoomConnection

ALLOWED_CONNECTION_TYPES = {
    "open_passage",
    "threshold",
    "closed_door",
    "continuous_then_cut",
}


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"'{field_name}' må være et JSON-objekt.")
    return value


def _require_string(mapping: Mapping[str, Any], field_name: str) -> str:
    value = mapping.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field_name}' må være en ikke-tom tekstverdi.")
    return value.strip()


def _require_float(mapping: Mapping[str, Any], field_name: str) -> float:
    try:
        return float(mapping[field_name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"'{field_name}' må være et tall.") from exc


def _optional_bool(mapping: Mapping[str, Any], field_name: str, default: bool) -> bool:
    if field_name not in mapping:
        return default
    value = mapping[field_name]
    if not isinstance(value, bool):
        raise ValueError(f"'{field_name}' må være true eller false.")
    return value


def parse_opening(payload: Mapping[str, Any]) -> Opening:
    opening = Opening(
        x1=_require_float(payload, "x1"),
        y1=_require_float(payload, "y1"),
        x2=_require_float(payload, "x2"),
        y2=_require_float(payload, "y2"),
    )
    if opening.x1 == opening.x2 and opening.y1 == opening.y2:
        raise ValueError("En åpning må ha to forskjellige endepunkter.")
    return opening


def parse_passage(payload: Mapping[str, Any]) -> Passage:
    passage = Passage(
        x=_require_float(payload, "x"),
        y=_require_float(payload, "y"),
        width=_require_float(payload, "width"),
        height=_require_float(payload, "height"),
    )
    if passage.width <= 0 or passage.height <= 0:
        raise ValueError("Passasjens bredde og høyde må være større enn 0.")
    return passage


def parse_cut_settings(payload: Mapping[str, Any], passage: Passage) -> CutSettings:
    axis = str(payload.get("axis", "")).lower()
    if axis not in {"x", "y"}:
        raise ValueError("'cut.axis' må være 'x' eller 'y'.")
    try:
        gap = float(payload.get("gap_width_mm", 5.0))
        clearance = float(payload.get("edge_clearance_mm", 15.0))
        step = float(payload.get("search_step_mm", 5.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Sagbredde, kantklaring og søkesteg må være tall.") from exc
    if gap <= 0 or step <= 0:
        raise ValueError("Sagbredde og søkesteg må være større enn 0.")
    if clearance < 0:
        raise ValueError("Kantklaringen kan ikke være negativ.")
    depth = passage.width if axis == "x" else passage.height
    if depth - 2 * clearance <= gap:
        raise ValueError("Kantklaringen etterlater ikke et gyldig område for fugen.")
    return CutSettings(
        axis=axis,
        gap_width_mm=gap,
        edge_clearance_mm=clearance,
        prefer_existing_joint=_optional_bool(payload, "prefer_existing_joint", True),
        search_step_mm=step,
    )


def parse_connection(
    payload: Mapping[str, Any], *, room_ids: set[str]
) -> RoomConnection:
    connection_id = _require_string(payload, "id")
    room_a = _require_string(payload, "room_a")
    room_b = _require_string(payload, "room_b")
    connection_type = _require_string(payload, "type")
    if room_a not in room_ids or room_b not in room_ids:
        unknown = room_a if room_a not in room_ids else room_b
        raise ValueError(
            f"Forbindelsen '{connection_id}' peker på ukjent rom '{unknown}'."
        )
    if room_a == room_b:
        raise ValueError(
            f"Forbindelsen '{connection_id}' kan ikke koble et rom til seg selv."
        )
    if connection_type not in ALLOWED_CONNECTION_TYPES:
        allowed = ", ".join(sorted(ALLOWED_CONNECTION_TYPES))
        raise ValueError(
            f"Ugyldig forbindelsestype '{connection_type}'. Tillatte verdier: {
                allowed
            }."
        )
    opening = parse_opening(_require_mapping(payload.get("opening"), "opening"))
    align = _require_mapping(payload.get("align", {}), "align")
    try:
        weight = float(payload.get("weight", 1.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("'weight' må være et tall.") from exc
    if weight <= 0:
        raise ValueError("'weight' må være større enn 0.")
    passage = None
    cut = None
    if connection_type == "continuous_then_cut":
        passage = parse_passage(_require_mapping(payload.get("passage"), "passage"))
        cut = parse_cut_settings(
            _require_mapping(payload.get("cut", {}), "cut"), passage
        )
    return RoomConnection(
        connection_id=connection_id,
        room_a=room_a,
        room_b=room_b,
        connection_type=connection_type,
        opening=opening,
        align_rows=_optional_bool(align, "rows", True),
        align_joints=_optional_bool(align, "joints", False),
        weight=weight,
        passage=passage,
        cut=cut,
    )


def parse_connections(config: Mapping[str, Any]) -> list[RoomConnection]:
    raw_connections = config.get("connections", [])
    if not isinstance(raw_connections, list):
        raise ValueError("'connections' må være en liste.")
    rooms = config.get("rooms", [])
    if not isinstance(rooms, list):
        raise ValueError("'rooms' må være en liste.")
    room_ids = {
        str(room["id"]) for room in rooms if isinstance(room, Mapping) and "id" in room
    }
    result = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_connections):
        connection = parse_connection(
            _require_mapping(raw, f"connections[{index}]"), room_ids=room_ids
        )
        if connection.connection_id in seen_ids:
            raise ValueError(f"Duplisert forbindelse-id: {connection.connection_id}")
        seen_ids.add(connection.connection_id)
        result.append(connection)
    return result


def connection_payload(connection: RoomConnection) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": connection.connection_id,
        "room_a": connection.room_a,
        "room_b": connection.room_b,
        "type": connection.connection_type,
        "opening": {
            "x1": connection.opening.x1,
            "y1": connection.opening.y1,
            "x2": connection.opening.x2,
            "y2": connection.opening.y2,
        },
        "align": {"rows": connection.align_rows, "joints": connection.align_joints},
        "weight": connection.weight,
    }
    if connection.passage:
        payload["passage"] = {
            "x": connection.passage.x,
            "y": connection.passage.y,
            "width": connection.passage.width,
            "height": connection.passage.height,
        }
    if connection.cut:
        payload["cut"] = {
            "axis": connection.cut.axis,
            "gap_width_mm": connection.cut.gap_width_mm,
            "edge_clearance_mm": connection.cut.edge_clearance_mm,
            "prefer_existing_joint": connection.cut.prefer_existing_joint,
            "search_step_mm": connection.cut.search_step_mm,
        }
    return payload
