"""The plugin's backend routes (dashboard/plugin_api.py).

Skipped when ``hermes_cli`` is not importable — the routes are thin wrappers over it, so without the
host there is nothing meaningful to assert.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent.parent

pytest.importorskip("hermes_cli.config", reason="runs inside Hermes")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"ov_api_{name}", _HERE / "dashboard" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"ov_api_{name}"] = module
    spec.loader.exec_module(module)
    return module


api = _load("plugin_api")


def test_exposes_a_router_with_the_expected_routes():
    routes = sorted(f"{sorted(r.methods)[0]} {r.path}" for r in api.router.routes)
    assert routes == ["GET /catalogs", "GET /settings", "POST /preview", "POST /settings"]


def test_writable_keys_are_this_plugin_s_own():
    """The pane may write this plugin's settings and the two provider switches — nothing else."""
    assert "tts.openrouter.volume" in api.WRITABLE
    assert "stt.provider" in api.WRITABLE
    assert all(key.startswith(("stt.", "tts.")) for key in api.WRITABLE)


def test_settings_reads_the_live_config():
    payload = api.get_settings()
    assert "settings" in payload and "writable" in payload
    assert payload["settings"]["resolved"]["volume"] == pytest.approx(1.0) or payload["settings"]["resolved"][
        "volume"
    ] > 0


def test_catalogs_match_the_shipped_lists():
    catalogs = api.get_catalogs()
    assert len(catalogs["stt"]) == 21
    assert len(catalogs["tts"]) == 18
    assert len(catalogs["voices"]) == 18
    assert "deepgram/aura-2" in catalogs["voices"]
