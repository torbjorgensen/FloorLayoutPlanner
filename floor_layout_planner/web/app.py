from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, redirect, send_from_directory
from flask_socketio import SocketIO

from floor_layout_planner.storage import ProjectService, initialize_project_storage
from floor_layout_planner.web.config import load_config
from floor_layout_planner.web.project_routes import register_project_routes
from floor_layout_planner.web.routes import register_command_routes
from floor_layout_planner.web.runtime import ProjectRuntimeRegistry
from floor_layout_planner.web.runtime_routes import register_runtime_routes
from floor_layout_planner.web.serialization import build_state_payload
from floor_layout_planner.web.sockets import (
    StateUpdateEmitter,
    register_state_socket_handlers,
)
from floor_layout_planner.web.state import ProjectState
from floor_layout_planner.web.workers import create_worker_manager


@dataclass
class PlannerApplication:
    app: Flask
    socketio: SocketIO
    state: ProjectState
    output_dir: Path
    projects: ProjectService
    runtimes: ProjectRuntimeRegistry
    start_all: Callable[[dict[str, Any]], None]
    shutdown: Callable[[], None]


def create_app(
    config_path: Path,
    *,
    start_workers: bool = True,
    database_url: str | None = None,
) -> PlannerApplication:
    """Create the planner runtime and its database-backed project catalog."""
    initial_config = load_config(config_path)
    configured_database_url = (
        database_url
        or os.environ.get("PLANNER_DATABASE_URL")
        or _default_database_url(config_path)
    )
    projects = initialize_project_storage(configured_database_url)
    if not projects.list(include_archived=True):
        # Preserve the existing CLI contract while making its JSON project
        # immediately available to the new database-backed project catalog.
        projects.create(initial_config)
    state = ProjectState(initial_config)
    app = Flask(__name__)
    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    frontend_dev_url = os.environ.get("FRONTEND_DEV_URL", "").rstrip("/")
    socket_origins_value = os.environ.get("SOCKETIO_ALLOWED_ORIGINS", "")
    socket_allowed_origins = [
        origin.strip() for origin in socket_origins_value.split(",") if origin.strip()
    ] or None
    socketio = SocketIO(
        app,
        async_mode="threading",
        always_connect=True,
        cors_allowed_origins=socket_allowed_origins,
    )
    project_output_root = Path(
        os.environ.get(
            "PLANNER_PROJECT_OUTPUT_ROOT",
            str(config_path.resolve().parent / "planner_data" / "outputs"),
        )
    )
    runtimes = ProjectRuntimeRegistry(
        projects=projects,
        socketio=socketio,
        output_root=project_output_root,
        start_workers=start_workers,
    )

    output_dir = config_path.parent / f"{config_path.stem}_output"
    output_dir.mkdir(exist_ok=True)
    state_emitter: StateUpdateEmitter | None = None

    def notify_state_changed() -> None:
        if state_emitter is not None:
            state_emitter.notify()

    workers = create_worker_manager(state, output_dir, notify_state_changed)
    room_by_id = workers.room_by_id
    start_room = workers.start_room
    start_all = workers.start_all

    def frontend_response(path: str = ""):
        if frontend_dev_url:
            suffix = f"/{path}" if path else ""
            return redirect(f"{frontend_dev_url}{suffix}")

        if frontend_dist.exists():
            if path:
                asset_path = frontend_dist / path
                if asset_path.is_file():
                    return send_from_directory(frontend_dist, path)
            return send_from_directory(frontend_dist, "index.html")

        return (
            "<h1>Frontend build missing</h1>"
            "<p>Run <code>npm install</code> and <code>npm run build</code> "
            "inside <code>frontend/</code>, or start the dev stack with "
            "<code>tools/dev.sh</code>.</p>",
            503,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/healthz")
    def health():
        """Report that the web process is ready to accept requests."""
        return jsonify({"status": "ok"})

    @app.get("/")
    def index():
        return frontend_response()

    @app.get("/<path:path>")
    def frontend(path: str):
        return frontend_response(path)

    def socket_state_payload() -> dict[str, Any]:
        return build_state_payload(state, output_dir)

    state_emitter = StateUpdateEmitter(socketio, socket_state_payload)
    register_state_socket_handlers(
        socketio,
        state_emitter,
        project_emitter=lambda project_id: runtimes.get(project_id).emitter,
    )

    def shutdown() -> None:
        """Release timers and optimizer coordinators owned by this app."""
        state_emitter.close()
        workers.shutdown()
        runtimes.close()
        projects.close()

    register_command_routes(
        app,
        state=state,
        config_path=config_path,
        room_by_id=room_by_id,
        start_room=start_room,
        start_all=start_all,
        notify=notify_state_changed,
    )
    register_project_routes(app, projects, discard_runtime=runtimes.discard)
    register_runtime_routes(app, runtimes)

    legacy_runtime_enabled = os.environ.get(
        "PLANNER_ENABLE_LEGACY_RUNTIME", ""
    ).lower() in {"1", "true", "yes"}
    if start_workers and legacy_runtime_enabled:
        start_all(initial_config)

    return PlannerApplication(
        app=app,
        socketio=socketio,
        state=state,
        output_dir=output_dir,
        projects=projects,
        runtimes=runtimes,
        start_all=start_all,
        shutdown=shutdown,
    )


def _default_database_url(config_path: Path) -> str:
    """Locate ignored SQLite storage beside the current project configuration."""
    data_dir = config_path.resolve().parent / "planner_data"
    data_dir.mkdir(exist_ok=True)
    return f"sqlite:///{data_dir / 'planner.db'}"
