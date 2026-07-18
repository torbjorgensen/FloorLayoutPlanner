"""HTTP API for database-backed project management."""

from __future__ import annotations

import json
from typing import Any, Callable

from flask import Blueprint, Flask, Response, jsonify, request

from floor_layout_planner.storage import (
    ProjectConflictError,
    ProjectNotFoundError,
    ProjectRecord,
    ProjectService,
)
from floor_layout_planner.web.config import new_project_config


def _metadata(project: ProjectRecord) -> dict[str, Any]:
    """Serialize project metadata without leaking ORM implementation details."""
    return {
        "id": project.id,
        "name": project.name,
        "version": project.version,
        "archived": project.archived,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        # Optimization history is introduced separately; this stable field lets
        # the project list evolve without changing its response shape.
        "optimization_status": "not_started",
    }


def _project_payload(project: ProjectRecord) -> dict[str, Any]:
    return {**_metadata(project), "config": project.config}


def _json_object() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def _expected_version(payload: dict[str, Any]) -> int:
    value = payload.get("expected_version")
    if isinstance(value, bool):
        raise ValueError("'expected_version' must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("'expected_version' must be an integer.") from exc
    if parsed < 1:
        raise ValueError("'expected_version' must be greater than 0.")
    return parsed


def register_project_routes(
    app: Flask,
    projects: ProjectService,
    *,
    discard_runtime: Callable[[str], None] | None = None,
) -> None:
    """Register stable project endpoints backed by the service boundary."""
    api = Blueprint("projects", __name__, url_prefix="/api/projects")

    @api.errorhandler(ProjectNotFoundError)
    def not_found(exc: ProjectNotFoundError):
        return jsonify({"ok": False, "error": str(exc)}), 404

    @api.errorhandler(ProjectConflictError)
    def conflict(exc: ProjectConflictError):
        return jsonify({"ok": False, "error": str(exc)}), 409

    @api.errorhandler(ValueError)
    def invalid(exc: ValueError):
        return jsonify({"ok": False, "error": str(exc)}), 400

    @api.get("")
    def project_list():
        include_archived = request.args.get("include_archived", "").lower() in {
            "1",
            "true",
            "yes",
        }
        return jsonify(
            {
                "ok": True,
                "projects": [
                    _metadata(project)
                    for project in projects.list(include_archived=include_archived)
                ],
            }
        )

    @api.post("")
    @api.post("/import")
    def project_create():
        payload = _json_object()
        config = (
            new_project_config(str(payload["name"]))
            if set(payload) == {"name"}
            else payload.get("config", payload)
        )
        if not isinstance(config, dict):
            raise ValueError("'config' must be a JSON object.")
        created = projects.create(config)
        return jsonify({"ok": True, "project": _project_payload(created)}), 201

    @api.get("/<project_id>")
    def project_get(project_id: str):
        return jsonify(
            {"ok": True, "project": _project_payload(projects.get(project_id))}
        )

    @api.patch("/<project_id>")
    def project_update(project_id: str):
        payload = _json_object()
        version = _expected_version(payload)
        if "config" in payload:
            config = payload["config"]
            if not isinstance(config, dict):
                raise ValueError("'config' must be a JSON object.")
            updated = projects.update(project_id, config, expected_version=version)
        elif "name" in payload:
            updated = projects.rename(
                project_id, str(payload["name"]), expected_version=version
            )
        else:
            raise ValueError("Provide either 'config' or 'name' to update a project.")
        if discard_runtime is not None:
            discard_runtime(project_id)
        return jsonify({"ok": True, "project": _project_payload(updated)})

    @api.post("/<project_id>/duplicate")
    def project_duplicate(project_id: str):
        payload = _json_object()
        name = payload.get("name")
        duplicate = projects.duplicate(
            project_id,
            expected_version=_expected_version(payload),
            name=str(name).strip() if name is not None else None,
        )
        return jsonify({"ok": True, "project": _project_payload(duplicate)}), 201

    def set_archived(project_id: str, archived: bool):
        payload = _json_object()
        updated = projects.set_archived(
            project_id,
            archived,
            expected_version=_expected_version(payload),
        )
        if archived and discard_runtime is not None:
            discard_runtime(project_id)
        return jsonify({"ok": True, "project": _project_payload(updated)})

    @api.post("/<project_id>/archive")
    def project_archive(project_id: str):
        return set_archived(project_id, True)

    @api.post("/<project_id>/restore")
    def project_restore(project_id: str):
        return set_archived(project_id, False)

    @api.delete("/<project_id>")
    def project_delete(project_id: str):
        payload = _json_object()
        projects.delete(project_id, expected_version=_expected_version(payload))
        if discard_runtime is not None:
            discard_runtime(project_id)
        return jsonify({"ok": True})

    @api.get("/<project_id>/export")
    def project_export(project_id: str):
        project = projects.get(project_id)
        body = json.dumps(project.config, indent=2, ensure_ascii=False) + "\n"
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in project.name
        ).strip("_")
        filename = f"{safe_name or 'project'}.json"
        return Response(
            body,
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    app.register_blueprint(api)
