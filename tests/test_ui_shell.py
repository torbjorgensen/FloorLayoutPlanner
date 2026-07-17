from __future__ import annotations

import json
from pathlib import Path


def project_file(relative_path: str) -> Path:
    return Path(__file__).resolve().parent.parent / relative_path


def test_frontend_package_declares_react_vite_toolchain() -> None:
    package = json.loads(
        project_file("frontend/package.json").read_text(encoding="utf-8")
    )

    assert package["scripts"]["dev"] == "vite"
    assert package["scripts"]["build"] == "tsc -b && vite build"
    assert package["dependencies"]["react"]
    assert package["dependencies"]["@mui/material"]
    assert package["dependencies"]["socket.io-client"]
    assert package["devDependencies"]["vite"]
    assert package["devDependencies"]["vitest"]


def test_frontend_source_exposes_simulation_ui() -> None:
    page_source = project_file("frontend/src/pages/PlannerPage.tsx").read_text(
        encoding="utf-8"
    )

    assert 'id="simulateDelayInput"' in page_source
    assert 'id="simulateButton"' in page_source
    assert 'id="stopSimulationButton"' in page_source
    assert 'id="simulationStatus"' in page_source
    assert "buildSimulationSteps" in page_source
    assert "renderFloorPlan" in page_source
    assert "useProjectState" in page_source
    assert 'fetch("/api/state")' not in page_source


def test_vite_config_proxies_api_requests() -> None:
    vite_config = project_file("frontend/vite.config.ts").read_text(encoding="utf-8")

    assert '"/api"' in vite_config
    assert '"/socket.io"' in vite_config
    assert "ws: true" in vite_config
    assert "rewriteWsOrigin: true" in vite_config
    assert "VITE_API_PROXY_TARGET" in vite_config
    assert "http://127.0.0.1:8765" in vite_config


def test_flask_backend_serves_frontend_build_or_dev_url() -> None:
    backend = project_file("laminate_planner.py").read_text(encoding="utf-8")

    assert (
        'frontend_dist = Path(__file__).resolve().parent / "frontend" / "dist"'
        in backend
    )
    assert "FRONTEND_DEV_URL" in backend
    assert "send_from_directory" in backend
    assert "redirect(" in backend
    assert "socketio = SocketIO(" in backend
    assert "cors_allowed_origins=socket_allowed_origins" in backend
    assert '@app.get("/api/state")' not in backend
