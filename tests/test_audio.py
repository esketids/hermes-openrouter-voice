"""Stdlib-only tests for the audio normaliser — no network, no Hermes imports.

The resampler is the part that silently breaks live calls if it drifts: the transcription endpoint
rejects a WAV whose sample rate is not 16 kHz or 24 kHz ("Meta transcription requires a 16000 Hz or
24000 Hz WAV sample rate (received 22050 Hz)"), and `say`-style 22.05 kHz input is the common case.

Run with:  python -m pytest tests/ -q
"""

from __future__ import annotations

import array
import importlib.util
import math
import pathlib
import sys
import wave

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_COMMON_PATH = _HERE.parent / "common.py"


def _common():
    """Load the plugin's shared module by path (the plugin dir is not an importable package)."""
    name = "hermes_openrouter_voice_common"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, _COMMON_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_pcm(path: pathlib.Path, *, rate: int, channels: int, seconds: float, width: int = 2,
               left: int = 9000, right: int = 3000) -> pathlib.Path:
    """A tone (or, for mono, a constant-amplitude tone) as an uncompressed WAV."""
    frames = array.array("h")
    for index in range(int(rate * seconds)):
        value = int(left * math.sin(2 * math.pi * 220 * index / rate))
        for channel in range(channels):
            frames.append(value if channel == 0 else right)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.writeframes(frames.tobytes() if width == 2 else b"\x00" * (len(frames) * width))
    return path


def _params(path: str) -> tuple[int, int, int, int]:
    with wave.open(path, "rb") as handle:
        return (handle.getnchannels(), handle.getsampwidth(),
                handle.getframerate(), handle.getnframes())


def test_44k_stereo_becomes_16k_mono_with_duration_preserved(tmp_path):
    common = _common()
    source = _write_pcm(tmp_path / "stereo44.wav", rate=44100, channels=2, seconds=2.0)

    out = common.normalize_wav(str(source))

    channels, width, rate, frames = _params(out)
    assert (channels, width, rate) == (1, 2, common.WAV_TARGET_RATE)
    # duration must survive the resample (allow one frame of rounding)
    assert abs(frames - int(common.WAV_TARGET_RATE * 2.0)) <= 1


def test_16k_mono_is_returned_untouched(tmp_path):
    """Already-canonical input must not be rewritten (temp files are churn)."""
    common = _common()
    source = _write_pcm(tmp_path / "mono16.wav", rate=16000, channels=1, seconds=0.5,
                        right=9000)

    assert common.normalize_wav(str(source)) == str(source)


def test_22050_mono_is_resampled(tmp_path):
    """`say`'s default rate — the exact case that produced a live 400."""
    common = _common()
    source = _write_pcm(tmp_path / "mono22.wav", rate=22050, channels=1, seconds=1.0, right=9000)

    channels, _, rate, frames = _params(common.normalize_wav(str(source)))
    assert (channels, rate) == (1, common.WAV_TARGET_RATE)
    assert abs(frames - common.WAV_TARGET_RATE) <= 1


def test_downmix_averages_the_channels(tmp_path):
    common = _common()
    # channel 0 = +1000, channel 1 = -1000 -> averaged to 0
    frames = array.array("h", [1000, -1000] * 16000)
    source = tmp_path / "opposed.wav"
    with wave.open(str(source), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(frames.tobytes())

    out = common.normalize_wav(str(source))
    with wave.open(out, "rb") as handle:
        assert handle.getnchannels() == 1
        assert set(handle.readframes(handle.getnframes())) == {0}


def test_non_pcm16_is_left_alone(tmp_path):
    """8-bit WAV needs a decoder this plugin does not carry; ffmpeg handles that path."""
    common = _common()
    source = _write_pcm(tmp_path / "eight.wav", rate=16000, channels=1, seconds=0.1, width=1,
                        right=9000)

    assert common.normalize_wav(str(source)) == str(source)


def test_unreadable_input_is_returned_unchanged(tmp_path):
    common = _common()
    broken = tmp_path / "not-really.wav"
    broken.write_bytes(b"nope")

    assert common.normalize_wav(str(broken)) == str(broken)
