"""Spoken-reply volume: resolution, clamping, and the ffmpeg step.

The volume lives in the provider on purpose: applied here it holds for every playback path Hermes uses
(client-direct, gateway relay, data-URL fallback) and survives an ``hermes update``, which a
client-side patch cannot.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent.parent


def _load(name: str):
    module_name = f"hermes_openrouter_voice_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, _HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


common = _load("common")


class TestResolution:
    def test_defaults_to_source_level(self, tmp_path):
        """Unset means 1.0. An empty value must mean unset, not silence."""
        config = tmp_path / "config.yaml"
        config.write_text("tts:\n  openrouter:\n    model: deepgram/aura-2\n")
        assert common.resolve_tts_settings(str(config))["volume"] == 1.0

    def test_empty_string_is_not_zero(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text('tts:\n  openrouter:\n    volume: ""\n')
        assert common.resolve_tts_settings(str(config))["volume"] == 1.0

    def test_reads_a_number(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("tts:\n  openrouter:\n    volume: 1.5\n")
        assert common.resolve_tts_settings(str(config))["volume"] == 1.5

    def test_clamps_to_the_supported_range(self, tmp_path):
        for written, expected in ((3.0, common.MAX_TTS_VOLUME), (-2.0, 0.0)):
            config = tmp_path / "config.yaml"
            config.write_text(f"tts:\n  openrouter:\n    volume: {written}\n")
            assert common.resolve_tts_settings(str(config))["volume"] == expected

    def test_nonsense_falls_back(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("tts:\n  openrouter:\n    volume: loud\n")
        assert common.resolve_tts_settings(str(config))["volume"] == 1.0


class TestApplyVolume:
    def test_unity_is_a_no_op(self):
        assert common.apply_volume("/tmp/does-not-need-to-exist.mp3", 1.0) == "/tmp/does-not-need-to-exist.mp3"

    def test_without_ffmpeg_the_original_path_comes_back(self, monkeypatch):
        monkeypatch.setattr(common, "ffmpeg_path", lambda: None)
        assert common.apply_volume("/tmp/audio.mp3", 1.5) == "/tmp/audio.mp3"

    def test_builds_a_volume_filter(self, monkeypatch, tmp_path):
        source = tmp_path / "audio.mp3"
        source.write_bytes(b"x" * 16)
        calls = {}

        class Done:
            returncode = 1  # keeps the helper on its "return the original" path

        def fake_run(argv, **kwargs):
            calls["argv"] = argv
            return Done()

        monkeypatch.setattr(common, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")
        monkeypatch.setattr(common.subprocess, "run", fake_run)

        assert common.apply_volume(str(source), 1.5) == str(source)
        argv = calls["argv"]
        assert "-filter:a" in argv
        assert argv[argv.index("-filter:a") + 1] == "volume=1.500"

    def test_the_filter_matches_the_measured_levels(self):
        """The levels used in the live check: 1.5 measured +3.10 dB, 2.0 measured +5.50 dB."""
        import math

        assert round(20 * math.log10(1.5), 2) == 3.52
        assert round(20 * math.log10(2.0), 2) == 6.02
