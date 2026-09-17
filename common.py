"""Shared helpers for the OpenRouter voice plugin (speech-to-text + text-to-speech).

Nothing here imports Hermes at module import time beyond a best-effort config read, so the same
module serves the plugin entry point and the two command-provider shims.

Endpoint facts established by probing the live API (2026-09-14), baked in below:

* Transcription accepts only ``response_format: json|verbose_json`` — ``"text"`` is a 400.
* 19 of 20 transcription models accept MP3/WebM; ``meta/muse-voice-transcribe-1.0`` requires
  16 kHz or 24 kHz mono RIFF/WAVE (a 22.05 kHz ``say`` recording is a live 400) — so PCM WAV input is
  normalised in pure Python and other containers go through ffmpeg when it is available.
* Speech models are vendor-prefixed catalog slugs, and voices are **model-specific**.
"""

from __future__ import annotations

import array
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import wave
from typing import Any, Dict, List, Optional

ENV_FILE = pathlib.Path.home() / ".hermes" / ".env"
WAV_TARGET_RATE = 16000  # Meta's transcription endpoint accepts 16000 or 24000 Hz only

DEFAULT_STT_MODEL = os.environ.get("OPENROUTER_STT_MODEL", "openai/whisper-large-v3")
DEFAULT_STT_BASE_URL = os.environ.get("OPENROUTER_STT_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_TTS_MODEL = os.environ.get("TTS_OPENROUTER_MODEL", "deepgram/aura-2")
DEFAULT_TTS_VOICE = os.environ.get("TTS_OPENROUTER_VOICE", "aura-2-thalia-en")
DEFAULT_TTS_BASE_URL = os.environ.get("TTS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Every transcription model on OpenRouter when this was written; feeds ``list_models()`` and the CLI
# pickers, which take slugs verbatim.
STT_CATALOG = (
    "openai/whisper-large-v3", "openai/whisper-large-v3-turbo", "openai/whisper-1",
    "openai/gpt-4o-transcribe", "openai/gpt-4o-mini-transcribe", "openai/gpt-transcribe",
    "mistralai/voxtral-mini-transcribe", "google/chirp-3", "deepgram/nova-3",
    "x-ai/grok-stt-1.0", "qwen/qwen3-asr-flash-2026-02-10", "microsoft/mai-transcribe-2",
    "nvidia/parakeet-tdt-0.6b-v3", "fish-audio/transcribe-1", "meta/muse-voice-transcribe-1.0",
    "mistralai/voxtral-small-24b-2507-stt", "qwen/qwen3-asr-1.7b", "qwen/qwen3-asr-0.6b",
    "microsoft/mai-transcribe-1.5", "nvidia/nemotron-3.5-asr-streaming-multilingual-0.6b",
)

# Aura-2 voices (the default model). Voices are model-specific: Kokoro wants af_heart/af_bella and
# Flux wants flux-*-en, so this list is a starting point, not a constraint — the config field is
# free-input and the endpoint rejects a mismatched pair with a 400 that names the model.
TTS_VOICES = (
    "aura-2-thalia-en", "aura-2-andromeda-en", "aura-2-asteria-en", "aura-2-hermes-en",
    "aura-2-luna-en", "aura-2-orion-en", "aura-2-aurora-en", "aura-2-jupiter-en",
)

FFMPEG_CANDIDATES = (
    "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg", "/snap/bin/ffmpeg",
)


# --------------------------------------------------------------------------- credentials + config

def api_key() -> str:
    """``OPENROUTER_API_KEY`` from the environment, else ``~/.hermes/.env`` (the chat key)."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def config_candidates(explicit: str = "") -> List[pathlib.Path]:
    """Config files to try, most specific first.

    Profiles do not always differ by ``HERMES_HOME`` (the desktop passes ``--profile <name>``), so an
    implicit lookup can read the wrong profile's config — the shims therefore accept ``--config``.
    """
    if explicit:
        return [pathlib.Path(explicit).expanduser()]
    candidates: List[pathlib.Path] = []
    env_config = os.environ.get("HERMES_CONFIG", "").strip()
    if env_config:
        candidates.append(pathlib.Path(env_config).expanduser())
    profile = os.environ.get("HERMES_PROFILE", "").strip()
    if profile:
        candidates.append(pathlib.Path.home() / ".hermes" / "profiles" / profile / "config.yaml")
    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    if hermes_home:
        candidates.append(pathlib.Path(hermes_home).expanduser() / "config.yaml")
    candidates.append(pathlib.Path.home() / ".hermes" / "config.yaml")
    return candidates


def load_config(explicit: str = "") -> Dict[str, Any]:
    """The active (or explicitly named) config, via Hermes' loader when importable."""
    if not explicit:
        try:
            from hermes_cli.config import load_config as _load

            data = _load()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    try:
        import yaml
    except ImportError:
        return {}
    for path in config_candidates(explicit):
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


def _section(kind: str, explicit: str = "") -> Dict[str, Any]:
    section = load_config(explicit).get(kind)
    return section if isinstance(section, dict) else {}


def _per_provider(section: Dict[str, Any], key: str = "openrouter") -> Dict[str, Any]:
    block = section.get(key)
    return block if isinstance(block, dict) else {}


def _command_block(section: Dict[str, Any], key: str = "openrouter") -> Dict[str, Any]:
    providers = section.get("providers")
    if isinstance(providers, dict):
        block = providers.get(key)
        if isinstance(block, dict):
            return block
    return {}


def _first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def resolve_stt_settings(explicit_config: str = "") -> Dict[str, str]:
    section = _section("stt", explicit_config)
    per_provider = _per_provider(section)
    return {
        "model": _first_string(per_provider.get("model"), _command_block(section).get("model"))
                 or DEFAULT_STT_MODEL,
        "language": _first_string(per_provider.get("language"), section.get("language")),
        "base_url": _first_string(per_provider.get("base_url")).rstrip("/") or DEFAULT_STT_BASE_URL,
        "api_key": api_key(),
    }


def resolve_tts_settings(explicit_config: str = "") -> Dict[str, Any]:
    section = _section("tts", explicit_config)
    per_provider = _per_provider(section)
    speed: Any = per_provider.get("speed")
    if not isinstance(speed, (int, float)):
        speed = section.get("speed", 1.0)
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 1.0
    return {
        "model": _first_string(per_provider.get("model"), _command_block(section).get("model"))
                 or DEFAULT_TTS_MODEL,
        "voice": _first_string(per_provider.get("voice"), _command_block(section).get("voice"))
                 or DEFAULT_TTS_VOICE,
        "base_url": _first_string(per_provider.get("base_url")).rstrip("/") or DEFAULT_TTS_BASE_URL,
        "speed": speed,
        "api_key": api_key(),
    }


# --------------------------------------------------------------------------- audio preparation

def ffmpeg_path() -> Optional[str]:
    """PATH first, then the usual install prefixes — the app-spawned backend can have a short PATH.

    ffmpeg is not installed by default on macOS, and the desktop records ``audio/webm;codecs=opus``,
    so a WAV-only model needs it (``brew install ffmpeg``) for that container.
    """
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in FFMPEG_CANDIDATES:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def _pcm16_mono_downmix(frames: bytes, channels: int) -> bytes:
    if channels <= 1:
        return frames
    samples = array.array("h")
    samples.frombytes(frames if len(frames) % 2 == 0 else frames[:-1])
    if sys.byteorder == "big":
        samples.byteswap()
    mono = array.array("h", bytes(2 * (len(samples) // channels)))
    for frame in range(len(mono)):
        base = frame * channels
        total = 0
        for channel in range(channels):
            total += samples[base + channel]
        mono[frame] = int(total / channels)
    if sys.byteorder == "big":
        mono.byteswap()
    return mono.tobytes()


def _pcm16_resample(frames: bytes, in_rate: int, out_rate: int) -> bytes:
    """Linear interpolation — speech-grade, and free of any audioop/ffmpeg dependency."""
    if in_rate == out_rate or not frames:
        return frames
    samples = array.array("h")
    samples.frombytes(frames if len(frames) % 2 == 0 else frames[:-1])
    if sys.byteorder == "big":
        samples.byteswap()
    ratio = in_rate / out_rate
    out_count = max(1, int(len(samples) / ratio))
    out = array.array("h", bytes(2 * out_count))
    for index in range(out_count):
        position = index * ratio
        low = int(position)
        frac = position - low
        first = samples[low]
        second = samples[low + 1] if low + 1 < len(samples) else first
        out[index] = int(first + (second - first) * frac)
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()


def normalize_wav(src: str) -> str:
    """Rewrite a PCM WAV as 16 kHz mono, in pure Python (no ffmpeg needed)."""
    try:
        with wave.open(src, "rb") as handle:
            channels, width, rate = handle.getnchannels(), handle.getsampwidth(), handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError, OSError):
        return src
    if width != 2:  # only 16-bit PCM here; ffmpeg covers the rest
        return src
    if channels == 1 and rate == WAV_TARGET_RATE:
        return src
    frames = _pcm16_resample(_pcm16_mono_downmix(frames, channels), rate, WAV_TARGET_RATE)
    out = pathlib.Path(tempfile.mkdtemp()) / "audio.wav"
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(WAV_TARGET_RATE)
        handle.writeframes(frames)
    return str(out)


def prepare_audio(src: str) -> str:
    """Best-effort 16 kHz mono PCM; the input untouched when nothing can convert it."""
    if src.lower().endswith(".wav"):
        return normalize_wav(src)
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return src
    out = pathlib.Path(tempfile.mkdtemp()) / "audio.wav"
    proc = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(WAV_TARGET_RATE),
         "-f", "wav", str(out)],
        capture_output=True,
    )
    if proc.returncode == 0 and out.exists() and out.stat().st_size > 44:
        return str(out)
    return src


# --------------------------------------------------------------------------- HTTP

def _multipart(fields: Dict[str, str], file_field: str, file_path: str) -> tuple:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    body += (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{os.path.basename(file_path)}"\r\nContent-Type: application/octet-stream\r\n\r\n'
    ).encode()
    body += pathlib.Path(file_path).read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), boundary


def _headers(key: str, content_type: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": content_type,
        "HTTP-Referer": "https://github.com/NousResearch/hermes-agent",
        "X-Title": "Hermes Agent",
    }


def _request(url: str, data: bytes, headers: Dict[str, str], timeout: int = 180) -> bytes:
    """POST and return the raw body; raise ``RuntimeError`` naming the endpoint error."""
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenRouter request failed: {exc.reason}") from exc


def transcribe_request(audio_path: str, *, model: str, language: str, base_url: str, key: str) -> str:
    """POST audio to ``/audio/transcriptions`` and return the transcript text."""
    payload, boundary = _multipart(
        {"model": model, "response_format": "json", **({"language": language} if language else {})},
        "file",
        prepare_audio(audio_path),
    )
    raw = _request(
        f"{base_url}/audio/transcriptions", payload,
        _headers(key, f"multipart/form-data; boundary={boundary}"),
    )
    body = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
    except ValueError:
        return body.strip()
    if isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
        return parsed["text"].strip()
    return body.strip()


def synthesize_request(text: str, *, model: str, voice: str, speed: Any, base_url: str, key: str,
                       instructions: str = "", response_format: str = "mp3") -> bytes:
    """POST to ``/audio/speech`` and return the audio bytes (mp3 unless told otherwise).

    ``response_format`` is left at mp3 deliberately: it is what the shipped default model was
    verified with, and some catalog models reject anything else (gemini wants ``pcm``).
    """
    body: Dict[str, Any] = {"model": model, "input": text, "voice": voice,
                            "response_format": response_format}
    if isinstance(speed, (int, float)) and float(speed) != 1.0:
        body["speed"] = float(speed)
    if instructions:
        body["instructions"] = instructions
    data = json.dumps(body).encode("utf-8")
    return _request(f"{base_url}/audio/speech", data, _headers(key, "application/json"))
