"""Commands addressed to isolated database-backed project runtimes."""

from __future__ import annotations

import copy
from typing import Any

from flask import Blueprint, Flask, jsonify, request

from pergo_planner.storage import ProjectConflictError, ProjectNotFoundError
from pergo_planner.web.config import editable_room_settings, update_room_settings
from pergo_planner.web.runtime import (
    ProjectRuntime,
    ProjectRuntimeRegistry,
    ProjectUnavailableError,
)


def register_runtime_routes(app: Flask, registry: ProjectRuntimeRegistry) -> None:
    """Register commands whose path identifies the owning project runtime."""
    api = Blueprint(
        "project_runtime",
        __name__,
        url_prefix="/api/projects/<project_id>/runtime",
    )

    @api.errorhandler(ProjectNotFoundError)
    @api.errorhandler(ProjectUnavailableError)
    def unavailable(exc: LookupError):
        return jsonify({"ok": False, "error": str(exc)}), 404

    @api.errorhandler(ProjectConflictError)
    def conflict(exc: ProjectConflictError):
        return jsonify({"ok": False, "error": str(exc)}), 409

    @api.errorhandler(ValueError)
    def invalid(exc: ValueError):
        return jsonify({"ok": False, "error": str(exc)}), 400

    def current_config(runtime: ProjectRuntime) -> dict[str, Any]:
        with runtime.state.lock:
            return copy.deepcopy(runtime.state.active_config)

    def settings_response(runtime: ProjectRuntime, room_id: str):
        config = current_config(runtime)
        room = runtime.workers.room_by_id(config, room_id)
        return jsonify(
            {
                "ok": True,
                "project_version": runtime.project_version,
                "settings": editable_room_settings(config, room),
            }
        )

    @api.post("/room/<room_id>/apply")
    def room_apply(project_id: str, room_id: str):
        runtime = registry.get(project_id)
        updated = update_room_settings(
            current_config(runtime), room_id, request.get_json(silent=True) or {}
        )
        with runtime.state.lock:
            runtime.state.active_config = copy.deepcopy(updated)
        runtime.workers.start_room(room_id, updated)
        return settings_response(runtime, room_id)

    @api.post("/room/<room_id>/save")
    def room_save(project_id: str, room_id: str):
        runtime = registry.get(project_id)
        updated_config = update_room_settings(
            current_config(runtime), room_id, request.get_json(silent=True) or {}
        )
        stored = registry.projects.update(
            project_id,
            updated_config,
            expected_version=runtime.project_version,
        )
        runtime.project_version = stored.version
        with runtime.state.lock:
            runtime.state.active_config = copy.deepcopy(stored.config)
            runtime.state.file_config = copy.deepcopy(stored.config)
        runtime.workers.start_room(room_id, stored.config)
        response = settings_response(runtime, room_id).get_json()
        response["message"] = "Saved to project database."
        return jsonify(response)

    @api.post("/room/<room_id>/reset")
    def room_reset(project_id: str, room_id: str):
        runtime = registry.get(project_id)
        stored = registry.projects.get(project_id)
        runtime.workers.room_by_id(stored.config, room_id)
        runtime.project_version = stored.version
        with runtime.state.lock:
            runtime.state.active_config = copy.deepcopy(stored.config)
            runtime.state.file_config = copy.deepcopy(stored.config)
        runtime.workers.start_room(room_id, stored.config)
        return settings_response(runtime, room_id)

    def set_paused(project_id: str, room_id: str, paused: bool):
        runtime = registry.get(project_id)
        try:
            with runtime.state.lock:
                runtime.state.rooms[room_id].paused = paused
        except KeyError as exc:
            raise ValueError(f"Unknown room id: {room_id}") from exc
        runtime.emitter.notify()
        return jsonify({"ok": True})

    @api.post("/room/<room_id>/pause")
    def room_pause(project_id: str, room_id: str):
        return set_paused(project_id, room_id, True)

    @api.post("/room/<room_id>/resume")
    def room_resume(project_id: str, room_id: str):
        return set_paused(project_id, room_id, False)

    @api.post("/room/<room_id>/restart")
    def room_restart(project_id: str, room_id: str):
        runtime = registry.get(project_id)
        config = current_config(runtime)
        runtime.workers.room_by_id(config, room_id)
        runtime.workers.start_room(room_id, config)
        return jsonify({"ok": True})

    @api.post("/restart-all")
    def restart_all(project_id: str):
        runtime = registry.get(project_id)
        runtime.workers.start_all(current_config(runtime))
        return jsonify({"ok": True})

    app.register_blueprint(api)
