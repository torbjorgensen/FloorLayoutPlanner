from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from flask import Flask, redirect, send_from_directory
from flask_socketio import SocketIO

from pergo_planner.web.config import load_config
from pergo_planner.web.routes import register_command_routes
from pergo_planner.web.serialization import build_state_payload
from pergo_planner.web.sockets import (
    StateUpdateEmitter,
    register_state_socket_handlers,
)
from pergo_planner.web.state import ProjectState
from pergo_planner.web.workers import create_worker_manager


@dataclass
class PlannerApplication:
    app: Flask
    socketio: SocketIO
    state: ProjectState
    output_dir: Path
    start_all: Callable[[dict[str, Any]], None]
    shutdown: Callable[[], None]


def create_app(config_path: Path, *, start_workers: bool = True) -> PlannerApplication:
    initial_config = load_config(config_path)
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

    output_dir = config_path.parent / f"{config_path.stem}_output"
    output_dir.mkdir(exist_ok=True)
    state_emitter: StateUpdateEmitter | None = None

    def notify_state_changed() -> None:
        if state_emitter is not None:
            state_emitter.notify()

    workers = create_worker_manager(
        state, output_dir, config_path, notify_state_changed
    )
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

    @app.get("/")
    def index():
        return frontend_response()

    @app.get("/<path:path>")
    def frontend(path: str):
        return frontend_response(path)

    def socket_state_payload() -> dict[str, Any]:
        return build_state_payload(state, output_dir)

    state_emitter = StateUpdateEmitter(socketio, socket_state_payload)
    register_state_socket_handlers(socketio, state_emitter)

    def shutdown() -> None:
        """Release timers and optimizer coordinators owned by this app."""
        state_emitter.close()
        workers.shutdown()

    register_command_routes(
        app,
        state=state,
        config_path=config_path,
        room_by_id=room_by_id,
        start_room=start_room,
        start_all=start_all,
        notify=notify_state_changed,
    )

    if start_workers:
        start_all(initial_config)

    return PlannerApplication(
        app=app,
        socketio=socketio,
        state=state,
        output_dir=output_dir,
        start_all=start_all,
        shutdown=shutdown,
    )
