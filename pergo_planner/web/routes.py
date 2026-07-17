from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, request

from pergo_planner.web.config import editable_room_settings, update_room_settings
from pergo_planner.web.state import ProjectState

StartRoom = Callable[[str, dict[str, Any]], None]
StartAll = Callable[[dict[str, Any]], None]


def register_command_routes(
    app: Flask,
    *,
    state: ProjectState,
    config_path: Path,
    room_by_id: Callable[[dict[str, Any], str], dict[str, Any]],
    start_room: StartRoom,
    start_all: StartAll,
    notify: Callable[[], None],
) -> None:
    def current_config() -> dict[str, Any]:
        with state.lock:
            return copy.deepcopy(state.active_config)

    def settings_response(config: dict[str, Any], room_id: str):
        return jsonify(
            {
                "ok": True,
                "settings": editable_room_settings(config, room_by_id(config, room_id)),
            }
        )

    @app.post("/api/room/<room_id>/apply")
    def room_apply(room_id: str):
        try:
            updated = update_room_settings(
                current_config(), room_id, request.get_json(silent=True) or {}
            )
            with state.lock:
                state.active_config = copy.deepcopy(updated)
            start_room(room_id, updated)
            return settings_response(updated, room_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/room/<room_id>/save")
    def room_save(room_id: str):
        try:
            updated = update_room_settings(
                current_config(), room_id, request.get_json(silent=True) or {}
            )
            temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(updated, file, indent=2, ensure_ascii=False)
                file.write("\n")
            temp_path.replace(config_path)
            with state.lock:
                state.active_config = copy.deepcopy(updated)
                state.file_config = copy.deepcopy(updated)
            start_room(room_id, updated)
            response = settings_response(updated, room_id).get_json()
            response["message"] = f"Saved to {config_path}"
            return jsonify(response)
        except (ValueError, OSError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/room/<room_id>/reset")
    def room_reset(room_id: str):
        try:
            with state.lock:
                restored = copy.deepcopy(state.file_config)
            room_by_id(restored, room_id)
            with state.lock:
                state.active_config = copy.deepcopy(restored)
            start_room(room_id, restored)
            return settings_response(restored, room_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    def set_paused(room_id: str, paused: bool):
        try:
            with state.lock:
                state.rooms[room_id].paused = paused
        except KeyError:
            return jsonify({"ok": False, "error": f"Unknown room id: {room_id}"}), 404
        notify()
        return jsonify({"ok": True})

    @app.post("/api/room/<room_id>/pause")
    def room_pause(room_id: str):
        return set_paused(room_id, True)

    @app.post("/api/room/<room_id>/resume")
    def room_resume(room_id: str):
        return set_paused(room_id, False)

    @app.post("/api/room/<room_id>/restart")
    def room_restart(room_id: str):
        try:
            config = current_config()
            room_by_id(config, room_id)
            start_room(room_id, config)
            return jsonify({"ok": True})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404

    @app.post("/api/restart-all")
    def restart_all():
        start_all(current_config())
        return jsonify({"ok": True})
