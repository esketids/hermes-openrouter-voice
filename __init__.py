"""Hermes plugin: OpenRouter voice — speech-to-text **and** text-to-speech in one plugin.

Registers two providers under the name ``openrouter``:

* ``TranscriptionProvider`` → ``stt.provider: openrouter``
* ``TTSProvider``           → ``tts.provider: openrouter``

Both reuse ``OPENROUTER_API_KEY`` — the key chat already uses — and both entry points of each
direction share one implementation (``stt_core`` / ``tts_core``), so the plugin path and the
``stt.providers`` / ``tts.providers`` command shims in this directory cannot drift apart.

Enable it per profile (each profile has its own ``config.yaml``):

    plugins:
      enabled:
        - openrouter-voice

Why the shims exist at all: the desktop Voice tab builds its rows from a bundle-compiled ``SECTIONS``
list and offers only provider names that appear under ``stt.providers.<name>`` / ``tts.providers.<name>``
or in its own enum — the served config schema never carries ``stt.provider``/``tts.provider``, so a
plugin-registered name is not offered in that dropdown. Declaring the command providers keeps both
names selectable in the GUI; resolution prefers them over the plugin, and both run this same code.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

_HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str) -> Any:
    """Load a sibling module under a stable import name.

    The directory cannot be imported as a package (its name contains a hyphen) and the modules import
    each other by name, so the module is registered in ``sys.modules`` before execution.
    """
    module_name = f"hermes_openrouter_voice_{name}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - paths are fixed
        raise ImportError(f"cannot load {_HERE / f'{name}.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def register(ctx: Any) -> None:
    """Plugin entry point: one plugin, both directions.

    Order matters: the wrappers import the core modules by name, so every module is loaded and
    registered in ``sys.modules`` before anything that imports it.
    """
    _load("common")
    _load("stt_core")
    _load("tts_core")
    stt = _load("stt")
    tts = _load("tts")
    ctx.register_transcription_provider(stt.build_provider())
    ctx.register_tts_provider(tts.build_provider())
