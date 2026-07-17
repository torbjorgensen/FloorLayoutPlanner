from __future__ import annotations

import threading
import time
from typing import Any, Callable

from flask import request
from flask_socketio import SocketIO

STATE_EVENT = "project_state"


class StateUpdateEmitter:
    """Broadcast project snapshots at a bounded rate when state changes."""

    def __init__(
        self,
        socketio: SocketIO,
        payload_factory: Callable[[], dict[str, Any]],
        minimum_interval_s: float = 0.2,
    ) -> None:
        self.socketio = socketio
        self.payload_factory = payload_factory
        self.minimum_interval_s = minimum_interval_s
        self.lock = threading.Lock()
        self.clients: set[str] = set()
        self.last_emit_at = 0.0
        self.timer: threading.Timer | None = None

    def connect(self, session_id: str) -> None:
        with self.lock:
            self.clients.add(session_id)
        self.socketio.emit(STATE_EVENT, self.payload_factory(), to=session_id)

    def disconnect(self, session_id: str) -> None:
        with self.lock:
            self.clients.discard(session_id)

    def close(self) -> None:
        """Cancel a pending broadcast timer during application shutdown."""
        with self.lock:
            self.clients.clear()
            timer = self.timer
            self.timer = None
        if timer is not None:
            timer.cancel()

    def notify(self) -> None:
        emit_now = False
        with self.lock:
            if not self.clients or self.timer is not None:
                return

            elapsed = time.monotonic() - self.last_emit_at
            delay = max(0.0, self.minimum_interval_s - elapsed)
            if delay == 0.0:
                self.last_emit_at = time.monotonic()
                emit_now = True
            else:
                self.timer = threading.Timer(delay, self._flush)
                self.timer.daemon = True
                self.timer.start()

        if emit_now:
            self._emit()

    def _flush(self) -> None:
        with self.lock:
            self.timer = None
            if not self.clients:
                return
            self.last_emit_at = time.monotonic()
        self._emit()

    def _emit(self) -> None:
        self.socketio.emit(STATE_EVENT, self.payload_factory())


def register_state_socket_handlers(
    socketio: SocketIO,
    emitter: StateUpdateEmitter,
) -> None:
    def on_connect(_auth=None) -> None:
        emitter.connect(request.sid)

    def on_disconnect(_reason=None) -> None:
        emitter.disconnect(request.sid)

    socketio.on_event("connect", on_connect)
    socketio.on_event("disconnect", on_disconnect)
