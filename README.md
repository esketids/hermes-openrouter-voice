# hermes-openrouter-voice

OpenRouter for **both** voice directions in [Hermes Agent](https://github.com/NousResearch/hermes-agent) —
speech-to-text and text-to-speech — reusing the `OPENROUTER_API_KEY` your chat provider already uses. No
second account, no second bill, no pip dependencies.

| Direction | Config | Endpoint |
|---|---|---|
| Speech-to-text | `stt.provider: openrouter` | `POST /api/v1/audio/transcriptions` |
| Text-to-speech | `tts.provider: openrouter` | `POST /api/v1/audio/speech` |

Upstream closed the "built-in OpenRouter STT provider" request as not-planned
([#24415](https://github.com/NousResearch/hermes-agent/issues/24415)) in favour of the provider surfaces —
plugins and `stt.providers.<name>` command providers. This plugin is that path, packaged.

## Install and configure

```bash
hermes plugins install esketids/hermes-openrouter-voice
hermes plugins enable openrouter-voice              # per profile: add --profile <name>
hermes config set stt.provider openrouter
hermes config set tts.provider openrouter           # only if you want OpenRouter speech output
```

```yaml
stt:
  openrouter:
    model: openai/whisper-large-v3     # or meta/muse-voice-transcribe-1.0, google/chirp-3, …
    language: ""                       # "" = auto-detect
tts:
  openrouter:
    model: deepgram/aura-2
    voice: aura-2-thalia-en            # voices are MODEL-SPECIFIC
    speed: 1.0                         # 0.25-4.0
```

The verified defaults are `openai/whisper-large-v3`, and `deepgram/aura-2` + `aura-2-thalia-en`, which
speaks multi-sentence input in full.

## Models, voices and limits

| Key | Shipped | Source |
|---|---|---|
| `stt.openrouter.model` | **21** transcription models | `GET /api/v1/models?output_modalities=transcription` |
| `tts.openrouter.model` | **18** speech models | `GET /api/v1/models?output_modalities=speech` |
| `tts.openrouter.voice` | **361** voices across 16 models | each model's `supported_voices` (there is no voices endpoint) |

```bash
python models.py                     # the shipped catalogs, no network
python models.py --voices [model]    # one model's voice set
python models.py --live              # diff the shipped lists against the API
python models.py --sample deepgram/aura-2 --montage   # cached voice clips + a montage
```

Voice counts: `deepgram/aura-2` 90, `hexgrad/kokoro-82m` 54, `minimax/speech-2.8-*` 45,
`mistralai/voxtral-mini-tts-2603` 30, `microsoft/mai-voice-2` 4, `fish-audio/*` none published (leave the
voice empty and the provider uses its default). Samples land in
`~/.hermes/cache/openrouter-voice-samples/<model>/`, one clip per voice, each naming its own voice first so
a montage is self-labelling — the API publishes no preview URLs.

`tts.openrouter.speed` is honoured two ways: sent natively where the model supports it (`aura-2` accepts
only 0.7-1.5; `qwen/*` rejects it entirely), otherwise applied as a local pitch-preserving time-stretch via
`ffmpeg atempo`. Without ffmpeg the rate is sent to the API only.

Measured against the live API rather than assumed — the things most likely to surprise you:

| Constraint | Detail |
|---|---|
| `response_format` | transcription accepts only `json` / `verbose_json`; `"text"` is a 400 |
| `meta/muse-voice-transcribe-1.0` | requires **16 or 24 kHz mono WAV**; 22.05 kHz is a live 400 |
| Containers | every other model accepts MP3/WebM; the desktop records WebM/Opus, which needs ffmpeg to reach a WAV-only model |
| `hexgrad/kokoro-82m` | returns **only the first sentence** |
| `google/gemini-3.1-flash-tts-preview` | rejects mp3 and demands `pcm` |

## In the desktop GUI

The provider **names** become selectable in Settings → Voice once the command providers are declared —
Hermes builds that dropdown from a bundle-compiled list plus any command provider in config:

<details>
<summary>Command-provider config for GUI selectability</summary>

```bash
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

`--force` is required — without it Hermes writes nothing for these dotted registry keys. `--config` is not
optional either: profiles are not always distinguished by `HERMES_HOME`, so the shim must be told which
config to read.

</details>

**Model / voice / speed dropdowns, Preview buttons, microphone and speaker pickers, and a
playback-volume slider** come from a patch that edits the desktop app itself. It is deliberately **not in
this repo's tree** — a plugin-catalog entry may not ship a patch for the app — and lives on branch
**`gui-rows`**, with a copy on each machine that uses it:

```bash
~/.hermes/patches/openrouter-voice-gui/apply-gui-rows.sh               # patch + repack
~/.hermes/patches/openrouter-voice-gui/apply-gui-rows.sh --no-pack     # patch only
```

### What a plugin may do — the surfaces this plugin now uses

The rows above need an app patch, but the same controls are reachable through supported plugin surface,
and this plugin ships all three:

| Surface | File | What it gives |
|---|---|---|
| Backend routes | `dashboard/plugin_api.py` | `GET`/`POST /settings`, `GET /catalogs`, `POST /preview` under `/api/plugins/openrouter-voice/` |
| Dashboard tab | `dashboard/dist/index.js` | provider switches, model, voice, playback volume and a Preview button |
| Native pane | `desktop/plugin.js` | the same controls as an Electron pane (`area: PANES_AREA`) |

**Playback volume lives in the provider**, not the renderer: `tts.openrouter.volume` (0.0-2.0) is applied by
`speak.py` / `tts_core.py` before the audio is handed back, so it covers every playback path Hermes uses —
client-direct, the gateway relay and the data-URL fallback — and it survives `hermes update`. Measured with
`ffmpeg volumedetect`: 1.5 → +3.10 dB, 2.0 → +5.50 dB, 0.5 → −6.50 dB (theory +3.52 / +6.02 / −6.02, the
gap being mp3 re-encode loss). Needs ffmpeg; without it the level is left alone rather than failing.

Microphone and speaker pickers cannot be done this way — a plugin cannot pin the recorder the app uses —
which is why that part is upstream, in [#117088](https://github.com/NousResearch/hermes-agent/pull/117088).

The rows live in a bundle-compiled list, so no plugin or config key can add one. Two things make it feel
fragile, both handled in `gui/`: `hermes update` replaces the checkout (re-run the script — a watchdog
notices and reports, staying silent while healthy), and the patch is cut against **one commit**, so a moved
base makes it fail loudly rather than half-apply.

The microphone and speaker rows use **browser device ids** (`navigator.mediaDevices.enumerateDevices()`), a
different namespace from `wake_word.input_device` — that one is a **PortAudio** index for wake-word capture
on the Python side. An unplugged device falls back to the system default, and the row says so rather than
switching silently.

## Verify and layout

```bash
$PY ~/.hermes/plugins/openrouter-voice/transcribe.py --config ~/.hermes/config.yaml clip.wav
python -m pytest tests/ -q          # audio normaliser: downmix, resample, idempotence
```

```
__init__.py      register(ctx) -> registers BOTH providers
common.py        credentials, profile-aware config, WAV normalise/resample, HTTP
stt_core.py      transcription logic (no Hermes imports)     stt.py   provider wrapper
tts_core.py      synthesis logic (no Hermes imports)         tts.py   provider wrapper
transcribe.py / speak.py   command-provider shims (GUI selectability)
models.py        catalogs, voices, samples     tests/   stdlib unit tests
```

The `*_core.py` modules import nothing from Hermes — the shims run outside the repo's `sys.path`, so the
ABC subclasses live in `stt.py` / `tts.py` and the logic is shared.

## Related upstream work

- **Listed in the Hermes plugin catalog** (catalog entry merged 2026-09-20)
- [#117088](https://github.com/NousResearch/hermes-agent/pull/117088) — microphone/speaker pickers for everyone (open)
- [#24415](https://github.com/NousResearch/hermes-agent/issues/24415) — STT provider (closed, not-planned; this plugin is the sanctioned alternative)
- [#15726](https://github.com/NousResearch/hermes-agent/issues/15726) — TTS provider (open)
- [#112122](https://github.com/NousResearch/hermes-agent/pull/112122) / [#112126](https://github.com/NousResearch/hermes-agent/pull/112126) — built-in provider variants (open; upstream prefers extending the existing transports instead)

## Licence

MIT