/**
 * OpenRouter Voice — dashboard tab.
 *
 * Plain IIFE, no build step: it renders with the host's React via
 * `window.__HERMES_PLUGIN_SDK__` and registers itself with `window.__HERMES_PLUGINS__`, the same
 * contract the shipped dashboard plugins use.
 *
 * Why a tab and not a Settings row: Settings → Voice is built from a bundle-compiled list inside the
 * app, so no plugin can add a row to it. A plugin *can* contribute a tab (here), a native pane
 * (`desktop/plugin.js`) and backend routes (`plugin_api.py`) — this file is the supported surface.
 */
(function () {
  'use strict'

  var SDK = window.__HERMES_PLUGIN_SDK__
  var registry = window.__HERMES_PLUGINS__
  if (!SDK || !registry || !SDK.React) return

  var React = SDK.React
  var h = React.createElement
  var hooks = SDK.hooks || {}
  var useState = hooks.useState || React.useState
  var useEffect = hooks.useEffect || React.useEffect

  var API = '/api/plugins/openrouter-voice'
  var DEFAULT_VOICE_TEXT = 'This is a sample of my voice at the configured volume.'

  function post(path, body) {
    return (SDK.fetchJSON || SDK.authedFetch)(API + path, {
      body: JSON.stringify(body || {}),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST'
    })
  }

  function get(path) {
    return (SDK.fetchJSON || SDK.authedFetch)(API + path)
  }

  function row(label, control) {
    return h('div', { className: 'ov-row' }, h('label', null, label), control)
  }

  function VoicePage() {
    var state = useState({ loading: true, error: '', settings: {}, catalogs: { stt: [], tts: [], voices: {} } })
    var view = state[0]
    var setState = state[1]
    var busy = useState(false)
    var setBusy = busy[1]
    var audioRef = React.useRef(null)

    useEffect(function () {
      var live = true

      Promise.all([get('/settings'), get('/catalogs')])
        .then(function (results) {
          if (!live) return
          setState(function (current) {
            return Object.assign({}, current, { loading: false, settings: results[0].settings || {}, catalogs: results[1] })
          })
        })
        .catch(function (error) {
          if (!live) return
          setState(function (current) {
            return Object.assign({}, current, { loading: false, error: String(error && error.message ? error.message : error) })
          })
        })

      return function () { live = false }
    }, [])

    function save(patch) {
      post('/settings', patch)
        .then(function (result) {
          if (!result) return
          setState(function (current) {
            var next = Object.assign({}, current)
            if (result.settings) next.settings = result.settings
            next.error = result.rejected && result.rejected.length ? 'not writable: ' + result.rejected.join(', ') : ''
            return next
          })
        })
        .catch(function (error) {
          setState(function (current) {
            return Object.assign({}, current, { error: String(error && error.message ? error.message : error) })
          })
        })
    }

    function preview() {
      setBusy(true)
      post('/preview', {})
        .then(function (result) {
          if (audioRef.current) audioRef.current.pause()
          var audio = new Audio(result.data_url)
          // The provider already applied the volume server-side; playing at unity avoids squaring it.
          audio.volume = 1
          audioRef.current = audio
          return audio.play()
        })
        .catch(function (error) {
          setState(function (current) {
            return Object.assign({}, current, { error: String(error && error.message ? error.message : error) })
          })
        })
        .then(function () { setBusy(false) })
    }

    var settings = view.settings || {}
    var resolved = settings.resolved || {}
    var catalogs = view.catalogs || { tts: [], voices: {} }
    var model = String(settings['tts.openrouter.model'] || resolved.model || '')
    var voices = (catalogs.voices && catalogs.voices[model]) || []
    var volume = Number(settings['tts.openrouter.volume'] !== undefined && settings['tts.openrouter.volume'] !== null
      ? settings['tts.openrouter.volume']
      : (resolved.volume !== undefined ? resolved.volume : 1)) || 1

    function select(value, options, onPick) {
      return h('select', { onChange: function (event) { onPick(event.target.value) }, value: value },
        options.map(function (option) { return h('option', { key: option, value: option }, option) }))
    }

    return h('div', { className: 'ov-page' },
      h('h2', null, 'OpenRouter Voice'),
      view.loading ? h('p', { className: 'ov-note' }, 'Loading…') : null,
      view.error ? h('p', { className: 'ov-error' }, view.error) : null,

      h('div', { className: 'ov-card' },
        row('Speech-to-text', h('button', {
          onClick: function () { save({ 'stt.provider': settings['stt.provider'] === 'openrouter' ? '' : 'openrouter' }) },
          type: 'button'
        }, settings['stt.provider'] === 'openrouter' ? 'Using OpenRouter — switch off' : 'Use OpenRouter')),

        row('Text-to-speech', h('button', {
          onClick: function () { save({ 'tts.provider': settings['tts.provider'] === 'openrouter' ? 'edge' : 'openrouter' }) },
          type: 'button'
        }, settings['tts.provider'] === 'openrouter' ? 'Using OpenRouter — switch to Edge' : 'Use OpenRouter')),

        row('Voice model', select(model, catalogs.tts || [], function (value) { save({ 'tts.openrouter.model': value }) })),

        row('Voice', select(
          String(settings['tts.openrouter.voice'] || resolved.voice || ''),
          voices.length ? voices : [String(settings['tts.openrouter.voice'] || resolved.voice || '')],
          function (value) { save({ 'tts.openrouter.voice': value }) }
        )),

        row('Playback volume', h('span', { className: 'ov-inline' },
          h('input', {
            max: 2, min: 0, onChange: function (event) { save({ 'tts.openrouter.volume': event.target.value }) },
            step: 0.05, type: 'range', value: volume
          }),
          h('span', { className: 'ov-value' }, Math.round(volume * 100) + '%')
        )),

        row('Preview', h('button', { disabled: busy[0], onClick: preview, type: 'button' },
          busy[0] ? 'Preparing…' : 'Play a sample'))
      ),

      h('p', { className: 'ov-note' },
        'The volume is applied by the provider itself before the audio is returned, so it holds for every ',
        'playback path — client-direct, the gateway relay and the data-URL fallback — and it survives app ',
        'updates, which a client-side patch cannot.'),
      h('p', { className: 'ov-note' },
        'Microphone and speaker pickers are app-side: a plugin cannot pin the recorder the app uses. ',
        'That is tracked upstream in NousResearch/hermes-agent#117088.')
    )
  }

  registry.register('openrouter-voice', VoicePage)
})()