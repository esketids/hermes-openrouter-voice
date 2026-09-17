# hermes-openrouter-voice

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that adds **OpenRouter** to both
voice directions:

| Direction | Config | What it does |
|---|---|---|
| Speech-to-text | `stt.provider: openrouter` | `POST /api/v1/audio/transcriptions` — 20-model catalog, `json`/`verbose_json` |
| Text-to-speech | `tts.provider: openrouter` | `POST /api/v1/audio/speech` — vendor-prefixed speech slugs, model-specific voices |

Both reuse **`OPENROUTER_API_KEY`** — the same key your chat provider already uses — so there's no second
account, key or billing setup. Stdlib only: no pip dependencies.

It exists because upstream closed the "built-in OpenRouter STT provider" request as not-planned
([#24415](https://github.com/NousResearch/hermes-agent/issues/24415)) in favour of the provider
surfaces — plugins and `stt.providers.<name>` command providers. This is that path, packaged.

## Install

### A. Via Hermes (git under the hood)

```bash
hermes plugins install esketids/hermes-openrouter-voice
hermes plugins enable openrouter-voice
```

A full git URL works too: `hermes plugins install https://github.com/esketids/hermes-openrouter-voice.git`.
Later: `hermes plugins update openrouter-voice`.

**Per profile** — each profile has its own `config.yaml` and `plugins/`, so repeat with the profile flag:

```bash
hermes --profile <name> plugins install esketids/hermes-openrouter-voice
hermes --profile <name> plugins enable openrouter-voice
```

A profile may already have a standalone directory plugin elsewhere; symlinking keeps one source of truth:

```bash
ln -s ~/.hermes/plugins/openrouter-voice ~/.hermes/profiles/<name>/plugins/openrouter-voice
```

### B. Manual clone

```bash
git clone https://github.com/esketids/hermes-openrouter-voice.git \
  ~/.hermes/plugins/openrouter-voice
```

Then enable it in `~/.hermes/config.yaml` (or `hermes plugins enable openrouter-voice`):

```yaml
plugins:
  enabled:
    - openrouter-voice
```

## Configure

Minimum — pick the provider:

```bash
hermes config set stt.provider openrouter
hermes config set tts.provider openrouter      # only if you want OpenRouter speech output
```

Model / voice / language (all optional; defaults shown):

```yaml
stt:
  provider: openrouter
  language: en
  openrouter:
    model: openai/whisper-large-v3     # or meta/muse-voice-transcribe-1.0, google/chirp-3, …
    language: ""                       # "" = auto-detect
tts:
  provider: openrouter
  openrouter:
    model: deepgram/aura-2
    voice: aura-2-thalia-en            # voices are MODEL-SPECIFIC
```

### Make both names selectable in the desktop GUI

Hermes' desktop Voice tab builds its provider dropdown from a bundle-compiled list plus any
**command provider declared in config**, and the served config schema never carries `stt.provider` /
`tts.provider` — so a plugin-only install serves at runtime but is not offered in that dropdown.
Declaring these two entries fixes that (they run the same code, via the shims in this repo):

```bash
# use the python that runs your Hermes (e.g. <repo>/venv/bin/python)
PY=~/.hermes/hermes-agent/venv/bin/python
PLUG=~/.hermes/plugins/openrouter-voice

hermes config set --force stt.providers.openrouter.type command
hermes config set --force stt.providers.openrouter.command \
  "$PY $PLUG/transcribe.py --config ~/.hermes/config.yaml {input_path} {output_path} {language} {model}"

hermes config set --force tts.providers.openrouter.type command
hermes config set --force tts.providers.openrouter.command \
  "$PY $PLUG/speak.py --config ~/.hermes/config.yaml {input_path} {output_path} {voice} {model}"
hermes config set --force tts.providers.openrouter.voice_compatible true
```

Two things worth knowing about those commands:

* `--force` is required. Without it Hermes prints *"use --force to write this path anyway"* and writes
  **nothing** for these dotted registry keys.
* `--config` is not optional in practice: profiles do not always differ by `HERMES_HOME` (the desktop
  passes `--profile <name>`), so the shim must be told which config to read or it may read another
  profile's model.

Resolution order at dispatch is **built-in → command provider → plugin**, so the shims win when
declared and the plugin is the fallback when they are not.

## Verify

```bash
# any audio file; the shim prints the transcript
$PY ~/.hermes/plugins/openrouter-voice/transcribe.py --config ~/.hermes/config.yaml /path/to/clip.wav

# speech out
echo "round trip test" > /tmp/t.txt
$PY ~/.hermes/plugins/openrouter-voice/speak.py --config ~/.hermes/config.yaml /tmp/t.txt /tmp/out.mp3
```

## What the endpoint actually accepts (measured, not assumed)

These cost real debugging time, so they are baked in:

| Finding | Detail |
|---|---|
| `response_format` | transcription accepts only `json` / `verbose_json`; `"text"` is a **400** |
| Sample rate | `meta/muse-voice-transcribe-1.0` requires **16 kHz or 24 kHz mono WAV**; a 22.05 kHz file is a live 400 (`received 22050 Hz`). PCM WAV is normalised in pure Python — no ffmpeg needed |
| Containers | 19 of 20 transcription models accept MP3/WebM; the desktop records `audio/webm;codecs=opus`, which needs **ffmpeg** (`brew install ffmpeg`) to reach a WAV-only model |
| Truncation | `hexgrad/kokoro-82m` returns **only the first sentence** (identical ~1.5 s clip for very different inputs) — not the default |
| Format | `google/gemini-3.1-flash-tts-preview` rejects mp3 and demands `pcm`, so this plugin always requests mp3 |
| Voices | model-specific: `aura-2-*` for `deepgram/aura-2`, `af_heart` for Kokoro, `flux-*-en` for Flux |
| Verified default | `deepgram/aura-2` + `aura-2-thalia-en` — speaks multi-sentence input in full (verified 1.47 s vs 8.91 s for short/long input) |

## Layout

```
plugin.yaml      manifest (name, requires_env, tags)
__init__.py      register(ctx) → registers BOTH providers
common.py        credentials, profile-aware config, WAV normalise/resample, HTTP
stt_core.py      transcription logic (no Hermes imports)
stt.py           TranscriptionProvider wrapper
tts_core.py      synthesis logic (no Hermes imports)
tts.py           TTSProvider wrapper (raises on failure, voice_compatible)
transcribe.py    STT command-provider shim (GUI selectability)
speak.py         TTS command-provider shim (GUI selectability)
```

The `*_core.py` modules deliberately import nothing from Hermes: the shims run outside the repo's
`sys.path`, so the ABC subclasses live in `stt.py` / `tts.py` and the logic is shared.

## Related upstream work

* [#24415](https://github.com/NousResearch/hermes-agent/issues/24415) — "Add OpenRouter as an STT provider" (closed, not-planned; this is the sanctioned alternative)
* [#15726](https://github.com/NousResearch/hermes-agent/issues/15726) — "Add OpenRouter as a TTS provider" (open)
* PRs [#112122](https://github.com/NousResearch/hermes-agent/pull/112122) (STT built-in) and [#112126](https://github.com/NousResearch/hermes-agent/pull/112126) (TTS built-in) — the in-tree variants, if upstream ever prefers built-ins; the schema/desktop rows they add are what would put the OpenRouter **model** row inside the Voice tab

## Licence

MIT
