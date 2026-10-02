/**
 * OpenRouter Voice — desktop half (a pane).
 *
 * This is the *supported* surface for this plugin's settings. A plugin may contribute panes, status-bar
 * items, routes and themes; it may not add rows to Settings → Voice, because those rows live in a
 * bundle-compiled list inside the app. That is why the same controls exist as an app patch on the
 * plugin's `gui-rows` branch — and why this pane is the version that survives an update.
 *
 * Everything it reads and writes goes through `ctx.rest`, which is namespaced to
 * `/api/plugins/openrouter-voice/` and carries the dashboard's auth for us.
 *
 * Deliberately plain DOM + one SDK import: a pane that fails to import takes the whole plugin down with
 * it, so this file keeps its surface small.
 */

import { PANES_AREA } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

const ID = 'openrouter-voice'
const STYLE = `
.ov-pane { display: flex; flex-direction: column; gap: 14px; padding: 16px; font-size: 13px; }
.ov-pane h3 { margin: 0; font-size: 14px; font-weight: 600; }
.ov-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ov-row label { opacity: .75; }
.ov-pane select, .ov-pane input[type="number"] { min-width: 12rem; padding: 4px 6px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--card); color: inherit; font: inherit; }
.ov-pane input[type="range"] { width: 13rem; }
.ov-pane button { padding: 5px 10px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--card); color: inherit; font: inherit; cursor: pointer; }
.ov-pane button:disabled { opacity: .5; cursor: default; }
.ov-note { opacity: .65; font-size: 12px; line-height: 1.45; }
.ov-error { color: #d9534f; font-size: 12px; }
.ov-value { font-variant-numeric: tabular-nums; min-width: 3.5rem; text-align: right; opacity: .8; }
`

function el(tag, props, ...children) {
  return jsx(tag, { ...props, children: children.length > 1 ? children : children[0] })
}

function Pane({ ctx }) {
  const [state, setState] = React.useState({ loading: true, error: '', settings: {}, catalogs: { tts: [], stt: [], voices: {} } })
  const [busy, setBusy] = React.useState(false)
  const audioRef = React.useRef(null)

  const load = React.useCallback(async () => {
    try {
      const [settings, catalogs] = await Promise.all([ctx.rest('/settings'), ctx.rest('/catalogs')])
      setState({ loading: false, error: '', settings: settings.settings || {}, catalogs })
    } catch (error) {
      setState(current => ({ ...current, loading: false, error: String(error && error.message ? error.message : error) }))
    }
  }, [ctx])

  React.useEffect(() => { void load() }, [load])

  const save = React.useCallback(async (patch) => {
    try {
      const result = await ctx.rest('/settings', { method: 'POST', body: JSON.stringify(patch) })
      if (result && result.rejected && result.rejected.length) {
        setState(current => ({ ...current, error: `not writable: ${result.rejected.join(', ')}` }))
      }
      if (result && result.settings) {
        setState(current => ({ ...current, settings: result.settings }))
      }
    } catch (error) {
      setState(current => ({ ...current, error: String(error && error.message ? error.message : error) }))
    }
  }, [ctx])

  const preview = React.useCallback(async () => {
    setBusy(true)
    setState(current => ({ ...current, error: '' }))
    try {
      const result = await ctx.rest('/preview', { method: 'POST', body: JSON.stringify({}) })
      if (audioRef.current) { audioRef.current.pause() }
      const audio = new Audio(result.data_url)
      // The provider already applied the volume server-side, so this plays at unity on purpose:
      // scaling it again here would square the boost.
      audio.volume = 1
      audioRef.current = audio
      await audio.play()
    } catch (error) {
      setState(current => ({ ...current, error: String(error && error.message ? error.message : error) }))
    } finally {
      setBusy(false)
    }
  }, [ctx])

  const settings = state.settings || {}
  const resolved = settings.resolved || {}
  const catalogs = state.catalogs || { tts: [], voices: {} }
  const model = String(settings['tts.openrouter.model'] || resolved.model || '')
  const voices = (catalogs.voices && catalogs.voices[model]) || []
  const volume = Number(settings['tts.openrouter.volume'] ?? resolved.volume ?? 1) || 1

  const select = (key, value, options, onChange) =>
    el('select', { onChange: event => onChange(event.target.value), value },
      ...options.map(option => el('option', { key: option, value: option }, option)))

  return el('div', { className: 'ov-pane' },
    el('h3', null, 'OpenRouter Voice'),
    state.loading ? el('div', { className: 'ov-note' }, 'Loading…') : null,
    state.error ? el('div', { className: 'ov-error' }, state.error) : null,

    el('div', { className: 'ov-row' },
      el('label', null, 'Speech-to-text'),
      el('button', {
        onClick: () => void save({ 'stt.provider': settings['stt.provider'] === 'openrouter' ? '' : 'openrouter' })
      }, settings['stt.provider'] === 'openrouter' ? 'Using OpenRouter — switch off' : 'Use OpenRouter')
    ),

    el('div', { className: 'ov-row' },
      el('label', null, 'Text-to-speech'),
      el('button', {
        onClick: () => void save({ 'tts.provider': settings['tts.provider'] === 'openrouter' ? 'edge' : 'openrouter' })
      }, settings['tts.provider'] === 'openrouter' ? 'Using OpenRouter — switch to Edge' : 'Use OpenRouter')
    ),

    el('div', { className: 'ov-row' },
      el('label', null, 'Voice model'),
      select('tts.openrouter.model', model, catalogs.tts || [], value => void save({ 'tts.openrouter.model': value }))
    ),

    el('div', { className: 'ov-row' },
      el('label', null, 'Voice'),
      select('tts.openrouter.voice', String(settings['tts.openrouter.voice'] || resolved.voice || ''),
        voices.length ? voices : [String(settings['tts.openrouter.voice'] || resolved.voice || '')],
        value => void save({ 'tts.openrouter.voice': value }))
    ),

    el('div', { className: 'ov-row' },
      el('label', null, 'Playback volume'),
      el('input', {
        max: 2, min: 0, onChange: event => void save({ 'tts.openrouter.volume': event.target.value }),
        step: 0.05, type: 'range', value: volume
      }),
      el('span', { className: 'ov-value' }, `${Math.round(volume * 100)}%`)
    ),

    el('div', { className: 'ov-row' },
      el('button', { disabled: busy, onClick: () => void preview() }, busy ? 'Preparing…' : 'Preview'),
      el('span', { className: 'ov-note' }, 'Plays a sample at the volume above')
    ),

    el('div', { className: 'ov-note' },
      'The volume is applied by the provider itself, so it holds for every playback path — including the ',
      'gateway relay — and survives app updates. Microphone and speaker pickers are app-side: a plugin ',
      'cannot pin the recorder, which is tracked upstream in NousResearch/hermes-agent#117088.'
    )
  )
}

export default {
  id: ID,
  name: 'OpenRouter Voice',
  description: 'Settings for the OpenRouter voice plugin: providers, model, voice, playback volume and a preview.',
  defaultEnabled: true,
  register(ctx) {
    const style = document.createElement('style')
    style.textContent = STYLE
    document.head.append(style)
    ctx.onDispose(() => style.remove())

    ctx.register({
      area: PANES_AREA,
      data: { dock: { pane: 'workspace', pos: 'center' }, minWidth: '20rem', placement: 'main' },
      id: `${ID}:pane`,
      render: () => jsx(Pane, { ctx }),
      title: 'OpenRouter Voice'
    })
  }
}