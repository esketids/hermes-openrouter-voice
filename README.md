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

### The model + voice rows (optional patch)

The provider **names** above appear in the dropdowns from config alone. The **model row** — the field
with the 20-slug dropdown — is a different story, and it is worth knowing why before you file a bug
against this plugin:

```ts
// apps/desktop/src/app/settings/constants.ts
// The curated voice keys (Settings → Voice) are the single source of which
// per-provider fields exist; both the Voice settings page and the
// Capabilities TTS panel derive from it so the two surfaces never drift.
const VOICE_KEYS = SECTIONS.find(s => s.id === 'voice')?.keys ?? []
```

That list is compiled into the desktop bundle, so neither a plugin nor a config entry can add a row to
it — there is no dynamic, server-driven path for these fields. `gui/` ships the edit plus an idempotent
applier. Besides the rows themselves it adds **Preview buttons** on the voice and speed rows, and makes
the voice dropdown **follow the selected model**, mirroring how the desktop already narrows OpenAI's
voices.

### Microphone and speaker pickers

Two more rows come with the patch, under the voice-capture keys:

| Row | Config key | What it does |
|---|---|---|
| Microphone | `voice.mic_device_id` | pins `getUserMedia` to that device, in both the recorder and the barge-in analyser |
| Speaker | `voice.speaker_device_id` | routes playback through `setSinkId`, for the client-direct, relay and data-URL paths alike |

"System default" (the empty value) is the shipped behaviour, so leaving them alone changes nothing.
Two notes worth knowing:

* These are **browser device ids** from `navigator.mediaDevices.enumerateDevices()`, which is a
  different namespace from `wake_word.input_device` — that one is a **PortAudio** index/name used by
  the Python side for wake-word capture. Setting one does not set the other.
* A configured device that is no longer connected raises `OverconstrainedError`; recording then falls
  back to the system default **and the row says so**, rather than silently switching. The device list
  re-enumerates on `devicechange`, so plugging in a headset refreshes it without a reload.

The Preview button speaks a sample using the settings in force at that moment (model + voice + speed)
through the app's own playback ladder — client-direct synthesis where the profile has client-callable
credentials, otherwise the gateway relay, which is the path that runs this plugin server-side and so
applies the measured speed handling (native parameter inside a model's range, local time-stretch
outside it). It drops the 60-second voice-config cache first, so a model/voice/speed you just typed is
what you hear.

```bash
~/.hermes/plugins/openrouter-voice/gui/apply-gui-rows.sh              # patch + repack
~/.hermes/plugins/openrouter-voice/gui/apply-gui-rows.sh --no-pack    # patch only
```

Two caveats, both real:

* It edits `apps/desktop/src/app/settings/constants.ts` in your Hermes checkout and runs
  `npm run pack` (~5 min), which replaces the bundle under the running app — reload with ⌘R afterwards.
* `hermes update` checks out `main` and rebuilds the desktop, which **removes the row again**. Re-run
  the script after an update. The upstream fix is the schema+desktop change in
  [#112122](https://github.com/NousResearch/hermes-agent/pull/112122) (STT) and
  [#112126](https://github.com/NousResearch/hermes-agent/pull/112126) (TTS).

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

## Models and voices

```bash
python models.py                       # the shipped catalogs (no network)
python models.py --voices              # every model's voice set
python models.py --voices hexgrad/kokoro-82m
python models.py --live                # diff the shipped lists against the API
```

| Direction | Models shipped | Where the list comes from |
|---|---|---|
| `stt.openrouter.model` | **21** transcription models | `GET /api/v1/models?output_modalities=transcription` |
| `tts.openrouter.model` | **18** speech models | `GET /api/v1/models?output_modalities=speech` |
| `tts.openrouter.voice` | **361** voices across 16 models | each model's `supported_voices` |

**Voices are model-specific** — the endpoint rejects a mismatched pair with a 400 that names the
model, so the model field decides the valid voices:

* `deepgram/aura-2` → 90 voices (`aura-2-thalia-en`, …)
* `hexgrad/kokoro-82m` → 54 (`af_heart`, `af_bella`, …) — note this model emits **only the first
  sentence** of longer input
* `minimax/speech-2.8-*` → 45, `mistralai/voxtral-mini-tts-2603` → 30 (`en_paul_neutral`, …)
* `microsoft/mai-voice-2` → 4 (`en-US-Harper:MAI-Voice-2`, …)
* `fish-audio/*` → **none published**; those models speak with the provider's default voice, so leave
  the field empty (the API accepts the request without `voice`)

There is no voices endpoint — the sets above come from `supported_voices` on the models API. With the
GUI patch applied, the voice dropdown follows the selected model instead of offering every voice.

### Playback speed

`tts.openrouter.speed` (or the global `tts.speed`) takes 0.25-4.0 and is honoured on **every** model:

| Model | How the rate is applied |
|---|---|
| `deepgram/aura-2`, `minimax/*`, `microsoft/mai-voice-2`, `hexgrad/kokoro-82m` | natively, within the range the provider accepts (**aura-2: 0.7-1.5 only** — 1.6 is a 400) |
| `qwen/*` | never sent — it rejects the parameter with HTTP 400 |
| `voxtral`, `orpheus`, `grok`, `fish-audio`, anything unmeasured | local pitch-preserving time-stretch (`ffmpeg atempo`) |
| any rate outside a model's native range | nearest in-range value to the API + the remainder stretched locally |

Measured 2026-09-17: with `speed=1.5` the audio landed at 0.60-0.68 of the baseline wherever the API
honours the parameter. Expect **±10-20 %**: providers pace themselves differently between runs (two
identical `aura-2` calls differed by 12 %), and a slow rate at a range edge can overshoot. The local
path needs ffmpeg (`brew install ffmpeg`); without it the rate is sent to the API only.

### Voice samples

The API publishes no preview URLs, so samples are generated (and cached) locally:

```bash
python models.py --sample microsoft/mai-voice-2              # one clip per voice
python models.py --sample deepgram/aura-2 --montage          # + a single concatenated file
python models.py --sample hexgrad/kokoro-82m af_heart --force
```

Each clip speaks its own voice id first (`"<voice>. This is a sample of my voice."`, override with
`--phrase`), which makes a montage self-labelling. Output lands in
`~/.hermes/cache/openrouter-voice-samples/<model>/`, and existing clips are reused unless `--force`.

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
models.py        catalog/voice listing (`--voices`, `--live`)
gui/             optional patch for the Voice-tab model + voice rows (+ applier)
tests/           stdlib unit tests for the audio normaliser
```

## Tests

```bash
python -m pytest tests/ -q      # audio normaliser: downmix, resample, idempotence
```

The `*_core.py` modules deliberately import nothing from Hermes: the shims run outside the repo's
`sys.path`, so the ABC subclasses live in `stt.py` / `tts.py` and the logic is shared.

## Related upstream work

* [#24415](https://github.com/NousResearch/hermes-agent/issues/24415) — "Add OpenRouter as an STT provider" (closed, not-planned; this is the sanctioned alternative)
* [#15726](https://github.com/NousResearch/hermes-agent/issues/15726) — "Add OpenRouter as a TTS provider" (open)
* PRs [#112122](https://github.com/NousResearch/hermes-agent/pull/112122) (STT built-in) and [#112126](https://github.com/NousResearch/hermes-agent/pull/112126) (TTS built-in) — the in-tree variants, if upstream ever prefers built-ins; the schema/desktop rows they add are what would put the OpenRouter **model** row inside the Voice tab

## Licence

MIT
