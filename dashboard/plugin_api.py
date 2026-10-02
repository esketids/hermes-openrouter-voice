"""OpenRouter Voice plugin — backend API routes, mounted at /api/plugins/openrouter-voice/.

Exists so the desktop half can offer a *supported* surface for this plugin's settings: a plugin may
contribute a pane, a status-bar item or a route, but it may not add rows to Settings → Voice — those
rows live in a bundle-compiled list in the app, which is why they need an app patch and why the
supported route is this pane instead.

Everything here is a thin wrapper over the plugin's own modules (``common``/``tts_core``/``models``) and
over ``hermes_cli.config``, so the pane, the CLI and the providers cannot drift apart.

Routes
    GET  /settings   — the voice settings this plugin owns, as they stand right now
    POST /settings   — write any subset of them (whitelisted keys only)
    GET  /catalogs   — the shipped model / voice lists
    POST /preview    — synthesize a sample with the current settings, returned as a data URL
"""

from __future__ import annotations

import base64
import importlib.util
import json
import logging
import pathlib
import sys
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

router = APIRouter()

_PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent

# The keys the pane may write. Deliberately narrow: this plugin owns its own provider settings and the
# two provider selectors, and nothing else in the config.
WRITABLE = (
    "stt.provider",
    "tts.provider",
    "stt.openrouter.model",
    "stt.openrouter.language",
    "tts.openrouter.model",
    "tts.openrouter.voice",
    "tts.openrouter.speed",
    "tts.openrouter.volume",
)

READABLE = WRITABLE + ("voice.playback_volume", "voice.mic_device_id", "voice.speaker_device_id")

SAMPLE = "This is a sample of my voice at the configured volume."


def _module(name: str) -> Any:
    """Load one of the plugin's own modules by path — the plugin dir is not on sys.path."""
    module_name = f"hermes_openrouter_voice_{name}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, _PLUGIN_DIR / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - paths are fixed
        raise ImportError(f"cannot load {_PLUGIN_DIR / f'{name}.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _nested(config: Dict[str, Any], path: str) -> Any:
    node: Any = config
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _read_settings() -> Dict[str, Any]:
    from hermes_cli.config import load_config

    config = load_config() or {}
    values = {key: _nested(config, key) for key in READABLE}
    # Resolved through the plugin's own reader as well, so the pane shows what the provider will
    # actually use — including the defaults it applies when a key is unset.
    common = _module("common")
    try:
        values["resolved"] = {
            k: v for k, v in common.resolve_tts_settings().items() if k in ("model", "voice", "speed", "volume")
        }
    except Exception as exc:  # noqa: BLE001 - the pane still shows the raw values
        log.warning("openrouter-voice: could not resolve settings: %s", exc)
    return values


@router.get("/settings")
def get_settings() -> Dict[str, Any]:
    return {"settings": _read_settings(), "writable": list(WRITABLE)}


@router.post("/settings")
async def set_settings(request: Request) -> JSONResponse:
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)

    from hermes_cli.config import set_config_value

    written: Dict[str, Any] = {}
    rejected: List[str] = []

    for key, value in payload.items():
        if key not in WRITABLE:
            rejected.append(key)
            continue
        try:
            # force: these are dotted registry keys, and without it the writer silently skips them.
            set_config_value(key, "" if value is None else str(value), force=True)
            written[key] = value
        except Exception as exc:  # noqa: BLE001 - reported per key rather than failing the batch
            log.warning("openrouter-voice: could not write %s: %s", key, exc)
            rejected.append(key)

    return JSONResponse({"written": written, "rejected": rejected, "settings": _read_settings()})


@router.get("/catalogs")
def get_catalogs() -> Dict[str, Any]:
    common = _module("common")
    return {
        "stt": list(getattr(common, "STT_CATALOG", []) or []),
        "tts": list(getattr(common, "TTS_CATALOG", []) or []),
        # model -> its `supported_voices`; the pane narrows the voice list to the selected model.
        "voices": dict(getattr(common, "TTS_VOICES_BY_MODEL", {}) or {}),
    }


@router.post("/preview")
async def post_preview(request: Request) -> JSONResponse:
    """Synthesize a short sample with the settings in force, volume included.

    The volume is applied server-side by ``tts_core`` (the provider amplifies the audio before handing it
    back), so the pane must play the result at unity — applying it again in the client would square it.
    """
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}

    text = str(payload.get("text") or SAMPLE)[:400]
    common = _module("common")
    tts_core = _module("tts_core")

    try:
        settings = common.resolve_tts_settings()
        out = pathlib.Path(tempfile.mkdtemp()) / "preview.mp3"
        tts_core.synthesize_to_file(
            text,
            str(out),
            model=str(payload.get("model") or settings["model"]),
            voice=str(payload.get("voice") or settings["voice"]),
            speed=payload.get("speed"),
        )
        audio = out.read_bytes()
    except Exception as exc:  # noqa: BLE001 - surfaced to the pane as a message
        log.warning("openrouter-voice: preview failed: %s", exc)
        return JSONResponse({"error": str(exc)[:300]}, status_code=502)

    return JSONResponse({
        "data_url": "data:audio/mpeg;base64," + base64.b64encode(audio).decode("ascii"),
        "bytes": len(audio),
        "volume": settings.get("volume", 1.0),
    })