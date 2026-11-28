// Load with a classic script or a side-effect ES module import, then call connectPanel().
globalThis.connectPanel = function connectPanel() {
  const hash = new URLSearchParams(location.hash.slice(1))
  const mountToken = hash.get('mountToken')
  const pluginName = hash.get('pluginName')
  const encodedTarget = hash.get('target')
  if (
    window.parent === window ||
    hash.get('v') !== '1' ||
    !mountToken ||
    !pluginName ||
    !encodedTarget
  ) {
    throw new Error('Open this panel from AUTO-MAS.')
  }

  const envelope = {
    source: 'auto-mas-wheel',
    v: 1,
    mountToken,
    pluginName,
    target: JSON.parse(encodedTarget),
  }
  const { port1, port2 } = new MessageChannel()
  const pending = new Map()
  const stateListeners = new Set()
  const configListeners = new Set()
  let nextId = 0
  let observer
  let disposed = false
  let lastHeight

  function applyTheme(theme) {
    const root = document.documentElement
    root.dataset.theme = theme.mode
    for (const [name, value] of Object.entries(theme.tokens)) {
      if (name.startsWith('--mas-')) root.style.setProperty(name, value)
    }
  }

  function call(action, params) {
    if (disposed) return Promise.reject(new Error('Panel connection closed.'))
    return new Promise((resolve, reject) => {
      const requestId = ++nextId
      port1.postMessage({ ...envelope, requestId, action, params })
      pending.set(requestId, { resolve, reject })
    })
  }

  function subscribe(listeners, listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  }

  port1.onmessage = ({ data }) => {
    const { event, payload, requestId, result, error } = data
    if (event === 'stateChanged') {
      applyTheme(payload.theme)
      for (const listener of stateListeners) listener(payload)
      return
    }
    if (event === 'configReloaded') {
      for (const listener of configListeners) listener(payload)
      return
    }
    const request = pending.get(requestId)
    if (!request) return
    pending.delete(requestId)
    if (error) request.reject(new Error(error))
    else request.resolve(result)
  }

  function observeHeight() {
    const body = document.body
    observer = new ResizeObserver(() => {
      const { bottom } = body.getBoundingClientRect()
      const height = Math.ceil(bottom + parseFloat(getComputedStyle(body).marginBottom))
      if (height === lastHeight) return
      lastHeight = height
      void call('resize', { height }).catch(() => {
        // The host can close the port while a resize is in flight.
        lastHeight = undefined
      })
    })
    observer.observe(body)
  }

  function dispose() {
    if (disposed) return
    disposed = true
    observer?.disconnect()
    document.removeEventListener('DOMContentLoaded', observeHeight)
    window.removeEventListener('pagehide', dispose)
    port1.close()
    for (const { reject } of pending.values()) {
      reject(new Error('Panel connection closed.'))
    }
    pending.clear()
    stateListeners.clear()
    configListeners.clear()
  }

  port1.onmessageerror = dispose
  window.parent.postMessage({ ...envelope, type: 'ready' }, '*', [port2])
  window.addEventListener('pagehide', dispose, { once: true })
  if (document.body) observeHeight()
  else document.addEventListener('DOMContentLoaded', observeHeight, { once: true })

  async function getContext() {
    const context = await call('getContext')
    applyTheme(context.theme)
    return context
  }

  /**
   * Save replies contain {ok: true} or {ok: false, code, message, fieldErrors?}.
   * Event subscriptions return an unsubscribe function.
   */
  return {
    getContext,
    translate: keys => call('translate', { keys }),
    request: (method, path, body) => call('request', { method, path, body }),
    saveConfig: (changes, phase = 'commit') => call('saveConfig', { changes, phase }),
    runAction: (group, field, value = true) => call('runAction', { group, field, value }),
    pickPath: options => call('pickPath', options),
    confirm: options => call('confirm', options),
    notify: (severity, message) => call('notify', { severity, message }),
    onStateChange: listener => subscribe(stateListeners, listener),
    onConfigReloaded: listener => subscribe(configListeners, listener),
    dispose,
  }
}
