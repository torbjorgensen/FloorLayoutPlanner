from __future__ import annotations

import importlib
import subprocess
import sys

import pytest


def test_legacy_package_import_warns_and_resolves_public_api() -> None:
    sys.modules.pop("pergo_planner", None)

    with pytest.warns(DeprecationWarning, match="deprecated"):
        legacy = importlib.import_module("pergo_planner")

    canonical = importlib.import_module("floor_layout_planner")
    assert legacy.Candidate is canonical.Candidate


def test_canonical_module_and_legacy_script_expose_cli_help() -> None:
    canonical = subprocess.run(
        [sys.executable, "-m", "floor_layout_planner.cli", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    legacy = subprocess.run(
        [sys.executable, "laminate_planner.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Floor Layout Planner" in canonical.stdout
    assert "deprecated" in legacy.stderr
