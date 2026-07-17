"""Project-scoped optimizer runtimes and lifecycle registry."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from flask_socketio import SocketIO

from pergo_planner.storage import ProjectService
from pergo_planner.web.serialization import build_state_payload
from pergo_planner.web.sockets import StateUpdateEmitter
from pergo_planner.web.state import ProjectState
from pergo_planner.web.workers import WorkerManager, create_worker_manager


class ProjectUnavailableError(LookupError):
    """Raised when an archived project cannot own a live planner runtime."""


@dataclass
class ProjectRuntime:
    """All mutable optimizer resources belonging to one project snapshot."""

    project_id: str
    project_version: int
    state: ProjectState
    output_dir: Path
    workers: WorkerManager
    emitter: StateUpdateEmitter

    def close(self) -> None:
        """Stop workers and pending emissions owned by this project."""
        self.emitter.close()
        self.workers.shutdown()


class ProjectRuntimeRegistry:
    """Lazily create and safely dispose isolated project runtimes."""

    def __init__(
        self,
        *,
        projects: ProjectService,
        socketio: SocketIO,
        output_root: Path,
        start_workers: bool = True,
    ) -> None:
        self.projects = projects
        self.socketio = socketio
        self.output_root = output_root
        self.start_workers = start_workers
        self.lock = threading.RLock()
        self.runtimes: dict[str, ProjectRuntime] = {}

    def get(self, project_id: str) -> ProjectRuntime:
        """Return an existing runtime or create one from a stored snapshot."""
        with self.lock:
            existing = self.runtimes.get(project_id)
            if existing is not None:
                return existing

            project = self.projects.get(project_id)
            if project.archived:
                raise ProjectUnavailableError(
                    f"Archived project cannot be opened: {project_id}"
                )

            output_dir = self.output_root / project.id
            output_dir.mkdir(parents=True, exist_ok=True)
            state = ProjectState(project.config)
            emitter: StateUpdateEmitter | None = None

            def notify() -> None:
                if emitter is not None:
                    emitter.notify()

            workers = create_worker_manager(
                state,
                output_dir,
                notify,
            )
            runtime_ref: ProjectRuntime | None = None

            def payload() -> dict:
                return {
                    **build_state_payload(state, output_dir),
                    "project_id": project.id,
                    "project_version": (
                        runtime_ref.project_version
                        if runtime_ref is not None
                        else project.version
                    ),
                }

            emitter = StateUpdateEmitter(self.socketio, payload)
            runtime = ProjectRuntime(
                project_id=project.id,
                project_version=project.version,
                state=state,
                output_dir=output_dir,
                workers=workers,
                emitter=emitter,
            )
            runtime_ref = runtime
            self.runtimes[project.id] = runtime
            if self.start_workers:
                workers.start_all(project.config)
            return runtime

    def discard(self, project_id: str) -> None:
        """Dispose one runtime after archive, deletion, or explicit eviction."""
        with self.lock:
            runtime = self.runtimes.pop(project_id, None)
        if runtime is not None:
            runtime.close()

    def close(self) -> None:
        """Dispose every active project runtime during application shutdown."""
        with self.lock:
            runtimes = tuple(self.runtimes.values())
            self.runtimes.clear()
        for runtime in runtimes:
            runtime.close()

    def active_project_ids(self) -> set[str]:
        """Return a snapshot of currently allocated runtime identifiers."""
        with self.lock:
            return set(self.runtimes)
