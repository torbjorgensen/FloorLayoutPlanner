from __future__ import annotations

import copy

import pytest

from pergo_planner.web.config import editable_room_settings, update_room_settings


def project() -> dict:
    return {
        "project_name": "Kerf",
        "board": {"length_mm": 2050, "width_mm": 240},
        "settings": {},
        "rooms": [
            {
                "id": "room",
                "name": "Room",
                "rectangles": [{"x": 0, "y": 0, "width": 1000, "height": 1000}],
            }
        ],
    }


def test_saw_kerf_defaults_and_can_be_updated() -> None:
    config = project()
    room = config["rooms"][0]
    payload = editable_room_settings(config, room)

    assert payload["saw_kerf_mm"] == 3.2
    payload["saw_kerf_mm"] = 2.4
    updated = update_room_settings(copy.deepcopy(config), "room", payload)

    assert updated["board"]["saw_kerf_mm"] == 2.4
    assert "saw_kerf_mm" not in updated["rooms"][0]["settings"]


@pytest.mark.parametrize("kerf", [-1, 2050])
def test_saw_kerf_must_fit_within_board_length(kerf: float) -> None:
    config = project()
    payload = editable_room_settings(config, config["rooms"][0])
    payload["saw_kerf_mm"] = kerf

    with pytest.raises(ValueError, match="Saw kerf"):
        update_room_settings(config, "room", payload)
