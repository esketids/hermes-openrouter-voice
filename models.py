#!/usr/bin/env python3
"""Print the OpenRouter voice catalogs — what this plugin ships, or what OpenRouter lists live.

    python models.py            # shipped catalogs (no network)
    python models.py --live     # fetch from the API and show anything the shipped lists are missing

Why a static list at all: the model field is free-input (the API takes any slug), so a shipped list
is a convenience, not a gate. `--live` is how you refresh it after OpenRouter adds a model — that is
exactly how `mistralai/voxtral-mini-3b-2507` was found missing from the transcription list.

Voices are a separate story: they are MODEL-SPECIFIC, so `list_voices()` can only describe the
default model's set (Aura-2). Every other model has its own, and a mismatched pair is a 400 naming
the model.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import urllib.request
from typing import Any

_HERE = pathlib.Path(__file__).resolve().parent
API = "https://openrouter.ai/api/v1/models"


def _load(name: str) -> Any:
    module_name = f"hermes_openrouter_voice_{name}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - paths are fixed
        raise ImportError(f"cannot load {_HERE / f'{name}.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _live(modality: str, key: str) -> list[str]:
    request = urllib.request.Request(
        f"{API}?output_modalities={modality}",
        headers={"Authorization": f"Bearer {key}"} if key else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return [item.get("id", "") for item in json.loads(response.read().decode()).get("data", [])]


def _live_voices(key: str) -> dict:
    """`supported_voices` per speech model — the models API carries the sets, there is no endpoint."""
    request = urllib.request.Request(
        f"{API}?output_modalities=speech",
        headers={"Authorization": f"Bearer {key}"} if key else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode()).get("data", [])
    return {item.get("id", ""): item.get("supported_voices") or [] for item in data}


def main(argv: list) -> int:
    common = _load("common")
    live = "--live" in argv

    shipped = {"transcription (stt)": list(common.STT_CATALOG), "speech (tts)": list(common.TTS_CATALOG)}
    for label, slugs in shipped.items():
        print(f"=== {label}: {len(slugs)} shipped ===")
        for slug in slugs:
            print("  ", slug)

    if "--voices" in argv:
        index = argv.index("--voices")
        wanted = argv[index + 1] if len(argv) > index + 1 and not argv[index + 1].startswith("--") else ""
        entries = {wanted: common.TTS_VOICES_BY_MODEL.get(wanted, ())} if wanted \
            else common.TTS_VOICES_BY_MODEL
        for model, voices in entries.items():
            note = "" if voices else "  (none published — the provider default voice works)"
            print(f"=== voices for {model}: {len(voices)}{note}")
            for voice in voices:
                print("  ", voice)
        if not live:
            return 0

    if not live:
        print("\n(--live fetches OpenRouter's current lists and shows what is missing)")
        print("(--voices [model] lists the shipped per-model voice sets)")
        return 0

    key = common.api_key()
    for modality, label in (("transcription", "transcription (stt)"), ("speech", "speech (tts)")):
        try:
            current = _live(modality, key)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"\n=== {label}: live fetch failed: {exc}")
            continue
        missing = [slug for slug in current if slug not in shipped[label]]
        gone = [slug for slug in shipped[label] if slug not in current]
        print(f"\n=== {label}: live {len(current)} | shipped {len(shipped[label])} ===")
        print("   missing from the plugin:", missing or "none")
        print("   shipped but no longer listed:", gone or "none")

    # Voice sets move too: the models API exposes `supported_voices`, so diff those as well.
    try:
        live_voices = _live_voices(key)
        for model, voices in live_voices.items():
            shipped_voices = list(common.TTS_VOICES_BY_MODEL.get(model, ()))
            added = [v for v in voices if v not in shipped_voices]
            dropped = [v for v in shipped_voices if v not in voices]
            if added or dropped:
                print(f"   voices {model}: +{len(added)} -{len(dropped)}"
                      + (f" (e.g. +{', '.join(added[:4])})" if added else ""))
        new_models = [m for m in live_voices if m not in common.TTS_VOICES_BY_MODEL]
        if new_models:
            print("   models with voices but no shipped entry:", new_models)
    except Exception as exc:  # noqa: BLE001 - report and finish
        print(f"   voice diff failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
