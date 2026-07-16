from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import Opening, RoomConnection

ALLOWED_CONNECTION_TYPES = {
    "open_passage",
    "threshold",
    "closed_door",
}


def _require_mapping(
    value: Any,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"'{field_name}' må være et JSON-objekt.")

    return value


def _require_string(
    mapping: Mapping[str, Any],
    field_name: str,
) -> str:
    value = mapping.get(field_name)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field_name}' må være en ikke-tom tekstverdi.")

    return value.strip()


def _require_float(
    mapping: Mapping[str, Any],
    field_name: str,
) -> float:
    try:
        return float(mapping[field_name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"'{field_name}' må være et tall.") from exc


def _optional_bool(
    mapping: Mapping[str, Any],
    field_name: str,
    default: bool,
) -> bool:
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


def parse_connection(
    payload: Mapping[str, Any],
    *,
    room_ids: set[str],
) -> RoomConnection:
    connection_id = _require_string(payload, "id")
    room_a = _require_string(payload, "room_a")
    room_b = _require_string(payload, "room_b")
    connection_type = _require_string(payload, "type")

    if room_a not in room_ids:
        raise ValueError(
            f"Forbindelsen '{connection_id}' peker på ukjent rom '{room_a}'."
        )

    if room_b not in room_ids:
        raise ValueError(
            f"Forbindelsen '{connection_id}' peker på ukjent rom '{room_b}'."
        )

    if room_a == room_b:
        raise ValueError(
            f"Forbindelsen '{connection_id}' kan ikke koble et rom til seg selv."
        )

    if connection_type not in ALLOWED_CONNECTION_TYPES:
        allowed = ", ".join(sorted(ALLOWED_CONNECTION_TYPES))
        raise ValueError(
            f"Ugyldig forbindelsestype '{connection_type}'. "
            f"Tillatte verdier: {allowed}."
        )

    opening_payload = _require_mapping(
        payload.get("opening"),
        "opening",
    )
    align_payload = _require_mapping(
        payload.get("align", {}),
        "align",
    )

    try:
        weight = float(payload.get("weight", 1.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("'weight' må være et tall.") from exc

    if weight <= 0:
        raise ValueError("'weight' må være større enn 0.")

    return RoomConnection(
        connection_id=connection_id,
        room_a=room_a,
        room_b=room_b,
        connection_type=connection_type,
        opening=parse_opening(opening_payload),
        align_rows=_optional_bool(
            align_payload,
            "rows",
            True,
        ),
        align_joints=_optional_bool(
            align_payload,
            "joints",
            False,
        ),
        weight=weight,
    )


def parse_connections(
    config: Mapping[str, Any],
) -> list[RoomConnection]:
    raw_connections = config.get("connections", [])

    if not isinstance(raw_connections, list):
        raise ValueError("'connections' må være en liste.")

    rooms = config.get("rooms", [])

    if not isinstance(rooms, list):
        raise ValueError("'rooms' må være en liste.")

    room_ids = {
        str(room["id"]) for room in rooms if isinstance(room, Mapping) and "id" in room
    }

    result: list[RoomConnection] = []
    seen_ids: set[str] = set()

    for index, raw_connection in enumerate(raw_connections):
        payload = _require_mapping(
            raw_connection,
            f"connections[{index}]",
        )

        connection = parse_connection(
            payload,
            room_ids=room_ids,
        )

        if connection.connection_id in seen_ids:
            raise ValueError(f"Duplisert forbindelse-id: {connection.connection_id}")

        seen_ids.add(connection.connection_id)
        result.append(connection)

    return result


def connection_payload(
    connection: RoomConnection,
) -> dict[str, Any]:
    return {
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
        "align": {
            "rows": connection.align_rows,
            "joints": connection.align_joints,
        },
        "weight": connection.weight,
    }
