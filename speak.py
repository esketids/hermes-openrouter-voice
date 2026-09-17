#!/usr/bin/env python3
"""TTS command-provider shim (``tts.providers.openrouter``) — thin wrapper over ``tts_core``.

Exists so the name is selectable in the desktop Voice tab (see the plugin ``__init__`` for why a
plugin-registered name is not). Imports nothing from Hermes: it runs outside the repo's ``sys.path``.

usage: speak.py [--config PATH] <input_path|text> <output_path> [voice] [model]

Per ``tools/tts_command_provider.py`` the template supplies ``{input_path}``/``{text_path}`` (a file
holding the text), ``{output_path}``, ``{voice}``, ``{model}``, ``{format}`` and ``{speed}``. The
first argument is treated as a file when it exists, otherwise as the literal text.
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

    if len(args) < 2:
        print("usage: speak.py [--config PATH] <input_path|text> <output_path> [voice] [model]",
              file=sys.stderr)
        return 2

    source, output_path = args[0], args[1]
    voice = args[2].strip() if len(args) > 2 and args[2].strip() else ""
    model = args[3].strip() if len(args) > 3 and args[3].strip() else ""

    source_path = pathlib.Path(source).expanduser()
    text = source_path.read_text(encoding="utf-8") if source_path.is_file() else source
    if not text.strip():
        print("speak.py: nothing to synthesize", file=sys.stderr)
        return 2

    _load("common")
    tts_core = _load("tts_core")
    try:
        written = tts_core.synthesize_to_file(
            text, output_path, model=model, voice=voice, config=explicit_config,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a non-zero exit
        print(f"speak.py: {exc}", file=sys.stderr)
        return 1

    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
