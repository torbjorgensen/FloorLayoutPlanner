from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, _tag: str, attrs) -> None:
        for key, value in attrs:
            if key == "id" and value:
                self.ids.add(value)


def project_file(relative_path: str) -> Path:
    return Path(__file__).resolve().parent.parent / relative_path


def test_ui_template_exposes_required_frontend_ids() -> None:
    parser = IdCollector()
    parser.feed(project_file("templates/index.html").read_text(encoding="utf-8"))

    required_ids = {
        "floorCanvas",
        "roomTabs",
        "roomSelect",
        "settingsForm",
        "selectedRoomName",
        "statusText",
        "statusBadge",
        "progressBar",
        "bestStats",
        "profileStats",
        "outputFiles",
        "summaryRoomName",
        "summaryStatusText",
        "summaryDirection",
        "summaryStartCorner",
        "summaryProgress",
        "summaryOutput",
        "simulateDelayInput",
        "simulateButton",
        "stopSimulationButton",
        "simulationStatus",
        "restartAllButton",
        "pauseButton",
        "resumeButton",
        "restartButton",
        "saveConfigButton",
        "resetConfigButton",
        "validationMessage",
    }

    assert required_ids.issubset(parser.ids)


def test_ui_styles_define_redesign_shell_tokens() -> None:
    css = project_file("static/style.css").read_text(encoding="utf-8")

    assert "--accent-warm" in css
    assert ".topbar" in css
    assert ".hero-panel" in css
    assert ".canvas-card" in css
    assert ".room-tab-grid" in css
    assert ".canvas-overlay" in css
    assert "@media (max-width: 860px)" in css


def test_ui_script_references_new_shell_elements() -> None:
    script = project_file("static/app.js").read_text(encoding="utf-8")

    assert 'document.getElementById("roomTabs")' in script
    assert 'document.getElementById("statusBadge")' in script
    assert 'document.getElementById("summaryRoomName")' in script
    assert 'document.getElementById("simulateButton")' in script
    assert 'document.getElementById("simulationStatus")' in script
    assert "populateRoomTabs" in script
    assert "syncRoomTabs" in script
    assert "startSimulation" in script
    assert "stopSimulation" in script
