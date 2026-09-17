"""OpenRouter speech synthesis — pure logic, free of Hermes imports (see ``stt_core`` for why).

``synthesize`` must raise on failure: the TTS dispatcher builds the ``{success: False}`` envelope
itself, unlike the STT side where the provider returns one.
"""

from __future__ import annotations

import pathlib
from typing import Any, Optional

from hermes_openrouter_voice_common import (
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    TTS_VOICES_BY_MODEL,
    resolve_tts_settings,
    split_speed,
    synthesize_request,
    time_stretch,
    voices_for_model,
)


def synthesize_to_file(
    text: str,
    output_path: str,
    *,
    model: str = "",
    voice: str = "",
    speed: Optional[float] = None,
    instructions: str = "",
    config: str = "",
) -> str:
    """Write synthesized audio for ``text`` and return the written path.

    Always requests mp3: that is what the shipped default was verified with, and models in the
    catalog disagree about other containers (``google/gemini-3.1-flash-tts-preview`` wants ``pcm``).
    A non-mp3 ``output_path`` therefore becomes ``<name>.mp3`` so the extension matches the bytes.

    ``speed`` (0.25-4.0) is honoured on every model: natively where the provider supports it, and by
    local ffmpeg time-stretch elsewhere — see ``SPEED_NATIVE_MODELS`` for the measured split.
    """
    settings = resolve_tts_settings(config)

    chosen_model = (model or settings["model"] or DEFAULT_TTS_MODEL).strip()
    if "/" not in chosen_model:
        # Catalog entries are vendor-prefixed: a native OpenAI name (`gpt-4o-mini-tts`) is not a
        # valid OpenRouter slug and would 400, so fall back to the default pair.
        chosen_model = DEFAULT_TTS_MODEL
    chosen_voice = (voice or settings["voice"] or DEFAULT_TTS_VOICE).strip()
    # A model that publishes no voices (the fish-audio family) speaks with the provider's default:
    # the parameter has to be OMITTED, not filled in with another model's default voice.
    if chosen_model in TTS_VOICES_BY_MODEL and not voices_for_model(chosen_model):
        chosen_voice = ""

    speed_value: Any = speed if isinstance(speed, (int, float)) else settings["speed"]
    try:
        speed_value = max(0.25, min(4.0, float(speed_value)))
    except (TypeError, ValueError):
        speed_value = 1.0

    # `speed` goes to the API only within the model's measured range; every remainder — a model
    # that ignores the parameter (voxtral/orpheus/grok), one that rejects it (qwen: HTTP 400), or a
    # rate outside its range (aura-2 above 1.5 is a 400) — is time-stretched locally instead.
    native_speed, local_stretch = split_speed(chosen_model, speed_value)

    key = settings["api_key"]
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (env or ~/.hermes/.env)")

    audio = synthesize_request(
        text, model=chosen_model, voice=chosen_voice, speed=native_speed,
        base_url=settings["base_url"], key=key, instructions=instructions,
    )
    if not audio:
        raise RuntimeError("OpenRouter speech returned no audio")

    target = pathlib.Path(output_path).expanduser()
    if target.suffix.lower() != ".mp3":
        target = target.with_suffix(".mp3")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(audio)

    if local_stretch != 1.0:
        stretched = time_stretch(str(target), local_stretch)
        if stretched != str(target):
            target.write_bytes(pathlib.Path(stretched).read_bytes())

    return str(target)
