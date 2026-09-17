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
    resolve_tts_settings,
    synthesize_request,
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
    """
    settings = resolve_tts_settings(config)

    chosen_model = (model or settings["model"] or DEFAULT_TTS_MODEL).strip()
    if "/" not in chosen_model:
        # Catalog entries are vendor-prefixed: a native OpenAI name (`gpt-4o-mini-tts`) is not a
        # valid OpenRouter slug and would 400, so fall back to the default pair.
        chosen_model = DEFAULT_TTS_MODEL
    chosen_voice = (voice or settings["voice"] or DEFAULT_TTS_VOICE).strip()
    if not voice and chosen_model == DEFAULT_TTS_MODEL and not settings["voice"]:
        chosen_voice = chosen_voice or DEFAULT_TTS_VOICE

    speed_value: Any = speed if isinstance(speed, (int, float)) else settings["speed"]

    key = settings["api_key"]
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (env or ~/.hermes/.env)")

    audio = synthesize_request(
        text, model=chosen_model, voice=chosen_voice, speed=speed_value,
        base_url=settings["base_url"], key=key, instructions=instructions,
    )
    if not audio:
        raise RuntimeError("OpenRouter speech returned no audio")

    target = pathlib.Path(output_path).expanduser()
    if target.suffix.lower() != ".mp3":
        target = target.with_suffix(".mp3")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(audio)
    return str(target)
