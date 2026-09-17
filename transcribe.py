#!/usr/bin/env python3
"""STT command-provider shim (``stt.providers.openrouter``) — thin wrapper over ``stt_core``.

Exists so the name is selectable in the desktop Voice tab (see the plugin ``__init__`` for why a
plugin-registered name is not). Runs outside the repo's ``sys.path``, so it imports nothing from
Hermes — only the sibling core modules, loaded by path.

usage: transcribe.py [--config PATH] <input_path> [output_path] [language] [model]

``tools/transcription_command.py`` prefers a non-empty ``{output_path}`` file over stdout, so this
writes the transcript there and also prints it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

_HERE = pathlib.Path(__file__).resolve().parent


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
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def main(argv: list) -> int:
    args = list(argv[1:])
    explicit_config = ""
    if args and args[0] == "--config":
        explicit_config = args[1] if len(args) > 1 else ""
        args = args[2:]

    if not args:
        print("usage: transcribe.py [--config PATH] <input_path> [output_path] [language] [model]",
              file=sys.stderr)
        return 2

    audio_path = args[0]
    output_path = args[1] if len(args) > 1 else ""
    language = args[2].strip() if len(args) > 2 and args[2].strip() else ""
    model = args[3].strip() if len(args) > 3 and args[3].strip() else ""

    _load("common")
    stt_core = _load("stt_core")
    envelope = stt_core.transcribe_file(
        audio_path, model=model, language=language, config=explicit_config,
    )
    if not envelope.get("success"):
        print(envelope.get("error") or "transcription failed", file=sys.stderr)
        return 1

    transcript = str(envelope.get("transcript") or "")
    if output_path:
        target = pathlib.Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(transcript, encoding="utf-8")
    print(transcript)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
