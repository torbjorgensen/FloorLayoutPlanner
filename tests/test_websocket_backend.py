from __future__ import annotations

from flask import Flask
from flask_socketio import SocketIO

from laminate_planner import (
    STATE_EVENT,
    StateUpdateEmitter,
    register_state_socket_handlers,
)


def test_socket_client_receives_initial_snapshot_and_updates() -> None:
    app = Flask(__name__)
    socketio = SocketIO(app, async_mode="threading")
    project_state = {"version": 1}
    emitter = StateUpdateEmitter(
        socketio,
        lambda: dict(project_state),
        minimum_interval_s=0,
    )
    register_state_socket_handlers(socketio, emitter)

    client = socketio.test_client(app)

    assert client.is_connected()
    assert client.get_received() == [
        {
            "name": STATE_EVENT,
            "args": [{"version": 1}],
            "namespace": "/",
        }
    ]

    project_state["version"] = 2
    emitter.notify()

    assert client.get_received() == [
        {
            "name": STATE_EVENT,
            "args": [{"version": 2}],
            "namespace": "/",
        }
    ]


def test_emitter_does_not_serialize_without_connected_clients() -> None:
    app = Flask(__name__)
    socketio = SocketIO(app, async_mode="threading")
    serialization_count = 0

    def payload() -> dict[str, int]:
        nonlocal serialization_count
        serialization_count += 1
        return {"count": serialization_count}

    emitter = StateUpdateEmitter(socketio, payload, minimum_interval_s=0)
    register_state_socket_handlers(socketio, emitter)

    emitter.notify()
    assert serialization_count == 0

    client = socketio.test_client(app)
    assert serialization_count == 1
    client.get_received()

    client.disconnect()
    emitter.notify()
    assert serialization_count == 1
