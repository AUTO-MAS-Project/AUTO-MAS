const hash = new URLSearchParams(location.hash.slice(1))
const mountToken = hash.get('mountToken')
const pluginName = hash.get('pluginName')
const encodedTarget = hash.get('target')
const form = document.querySelector('form')
const fields = form.querySelector('fieldset')
const status = document.querySelector('[role="status"]')
const groups = Array.from(form.querySelectorAll('[data-group]'), group => ({
  name: group.dataset.group,
  enabled: group.querySelector('[name="Enabled"]'),
  count: group.querySelector('[name="Count"]'),
}))

if (hash.get('v') === '1' && mountToken && pluginName && encodedTarget && window.parent !== window) {
  const target = JSON.parse(encodedTarget)
  const envelope = { source: 'auto-mas-wheel', v: 1, mountToken, pluginName, target }
  const { port1, port2 } = new MessageChannel()
  const pending = new Map()
  let nextId = 0

  // ready transfers the private port. RPC replies echo requestId with result or error.
  port1.onmessage = ({ data: { requestId, result, error } }) => {
    const request = pending.get(requestId)
    if (!request) return
    pending.delete(requestId)
    if (error) request.reject(error)
    else request.resolve(result)
  }
  window.parent.postMessage({ ...envelope, type: 'ready' }, '*', [port2])

  function call(action, params) {
    return new Promise((resolve, reject) => {
      const requestId = ++nextId
      pending.set(requestId, { resolve, reject })
      port1.postMessage({ ...envelope, requestId, action, params })
    })
  }

  function save(phase) {
    const changes = groups.flatMap(({ name: group, enabled, count }) => [
      { group, field: 'Enabled', value: enabled.checked },
      { group, field: 'Count', value: count.valueAsNumber },
    ])
    return call('saveConfig', { phase, changes })
  }

  call('readConfig').then(({ config, locked }) => {
    for (const { name, enabled, count } of groups) {
      enabled.checked = config[name].Enabled
      count.value = config[name].Count
    }
    fields.disabled = locked
    status.textContent = locked ? 'Read-only' : ''
  }).catch(() => { status.textContent = 'Could not load the plan.' })

  form.addEventListener('input', () => {
    if (!form.checkValidity()) return
    status.textContent = 'Unsaved changes'
    save('draft').catch(() => { status.textContent = 'Could not update the draft.' })
  })
  form.addEventListener('submit', async event => {
    event.preventDefault()
    fields.disabled = true
    try {
      await save('commit')
      status.textContent = 'Saved'
    } catch {
      status.textContent = 'Could not save the plan.'
    } finally {
      fields.disabled = false
    }
  })
} else {
  status.textContent = 'Open this editor from AUTO-MAS.'
}
