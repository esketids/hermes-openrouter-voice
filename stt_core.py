"""OpenRouter transcription — pure logic, deliberately free of Hermes imports.

The plugin entry point wraps this in ``TranscriptionProvider``; the command-provider shim calls it
directly (that process runs outside the repo's ``sys.path``, so importing the ABC would break it).
"""

from __future__ import annotations

from typing import Any, Dict

from hermes_openrouter_voice_common import (
    DEFAULT_STT_MODEL,
    api_key,
    resolve_stt_settings,
    transcribe_request,
)


def transcribe_file(
    file_path: str, *, model: str = "", language: str = "", config: str = "",
) -> Dict[str, Any]:
    """Transcribe ``file_path`` into the module envelope; never raise (ABC contract)."""
    settings = resolve_stt_settings(config)

    chosen_model = (model or settings["model"] or DEFAULT_STT_MODEL).strip()
    if "/" not in chosen_model:
        # Every catalog entry is vendor-prefixed, so a bare name (`whisper-1`) is a guaranteed 400 —
        # swap it for the default rather than sending a request that cannot succeed.
        chosen_model = DEFAULT_STT_MODEL

    chosen_language = (language or settings["language"] or "").strip()
    key = settings["api_key"]
    if not key:
        return {"success": False, "transcript": "", "provider": "openrouter",
                "error": "OPENROUTER_API_KEY is not set (env or ~/.hermes/.env)"}

    try:
        transcript = transcribe_request(
            file_path, model=chosen_model, language=chosen_language,
            base_url=settings["base_url"], key=key,
        )
    except Exception as exc:  # noqa: BLE001 - the contract requires an envelope, not a raise
        return {"success": False, "transcript": "", "provider": "openrouter", "error": str(exc)}

    if not transcript:
        return {"success": False, "transcript": "", "provider": "openrouter",
                "error": "the endpoint returned an empty transcript"}
    return {"success": True, "transcript": transcript, "provider": "openrouter"}
