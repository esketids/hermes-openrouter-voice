"""``TTSProvider`` wrapper — the plugin-facing half of the speech backend.

Registered name: ``openrouter``. ``voice_compatible`` is True because OpenRouter never returns Ogg:
voice-bubble delivery needs the gateway's ffmpeg conversion, exactly as the built-in did.

Catalog caveats worth keeping (found by measuring the audio, not by trusting a 200):

* ``deepgram/aura-2`` + ``aura-2-thalia-en`` (the defaults) speak multi-sentence input in full.
* ``hexgrad/kokoro-82m`` returns **the first sentence only** — the same ~1.6 s clip for very
  different inputs.
* ``google/gemini-3.1-flash-tts-preview`` rejects mp3 and requires ``pcm``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.tts_provider import DEFAULT_OUTPUT_FORMAT, TTSProvider

from hermes_openrouter_voice_common import (
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    TTS_VOICES,
    api_key,
)
from hermes_openrouter_voice_tts_core import synthesize_to_file


class OpenRouterTTSProvider(TTSProvider):
    """Speech synthesis through OpenRouter's OpenAI-shaped ``/audio/speech``."""

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def display_name(self) -> str:
        return "OpenRouter"

    def is_available(self) -> bool:
        return bool(api_key())

    def list_voices(self) -> List[Dict[str, Any]]:
        return [{"id": voice, "display": voice, "language": "en"} for voice in TTS_VOICES]

    def default_voice(self) -> Optional[str]:
        return DEFAULT_TTS_VOICE

    def default_model(self) -> Optional[str]:
        return DEFAULT_TTS_MODEL

    @property
    def voice_compatible(self) -> bool:
        return True

    def synthesize(
        self, text: str, output_path: str, *, voice: Optional[str] = None, model: Optional[str] = None,
        speed: Optional[float] = None, format: str = DEFAULT_OUTPUT_FORMAT, **extra: Any,
    ) -> str:
        """Raises on failure (the dispatcher owns the envelope); returns the written path."""
        return synthesize_to_file(
            text,
            output_path,
            model=model or "",
            voice=voice or "",
            speed=speed,
            instructions=str(extra.get("instructions") or ""),
        )


def build_provider() -> OpenRouterTTSProvider:
    return OpenRouterTTSProvider()
