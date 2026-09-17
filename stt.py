"""``TranscriptionProvider`` wrapper — the plugin-facing half of the speech-to-text backend.

Registered name: ``openrouter``. Built-ins still win, and a ``stt.providers.openrouter`` command entry
also wins (config is more local than a plugin install) — the shim in this directory is that entry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.transcription_provider import TranscriptionProvider

from hermes_openrouter_voice_common import DEFAULT_STT_MODEL, STT_CATALOG, api_key
from hermes_openrouter_voice_stt_core import transcribe_file


class OpenRouterTranscriptionProvider(TranscriptionProvider):
    """Speech-to-text through OpenRouter's OpenAI-shaped ``/audio/transcriptions``."""

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def display_name(self) -> str:
        return "OpenRouter"

    def is_available(self) -> bool:
        return bool(api_key())

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"id": slug, "name": slug, "provider": "openrouter"} for slug in STT_CATALOG]

    def default_model(self) -> Optional[str]:
        return DEFAULT_STT_MODEL

    def transcribe(
        self, file_path: str, *, model: Optional[str] = None, language: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        return transcribe_file(file_path, model=model or "", language=language or "")


def build_provider() -> OpenRouterTranscriptionProvider:
    return OpenRouterTranscriptionProvider()
