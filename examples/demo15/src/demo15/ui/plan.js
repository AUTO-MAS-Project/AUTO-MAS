const form = document.querySelector('form')
const fieldset = form.querySelector('fieldset')
const status = document.querySelector('[role="status"]')
const inputs = [...form.querySelectorAll('input')]
const fieldKey = input => `${input.closest('[data-group]').dataset.group}.${input.name}`

function changeFor(input) {
  return {
    group: input.closest('[data-group]').dataset.group,
    field: input.name,
    value: input.type === 'checkbox' ? input.checked : input.valueAsNumber,
  }
}

function showError(input, error = '') {
  document.getElementById(input.getAttribute('aria-describedby')).textContent = error
  if (error) input.setAttribute('aria-invalid', 'true')
  else input.removeAttribute('aria-invalid')
}

function applyConfig(config) {
  for (const input of inputs) {
    const { group, field, value } = changeFor(input)
    const next = config[group][field]
    if (value === next) continue
    if (input.type === 'checkbox') input.checked = next
    else input.value = next
    showError(input)
  }
}

async function start() {
  const panel = globalThis.connectPanel()
  let state = { locked: false, busy: false }
  let submitting = false
  let feedback = ''
  function updateControls() {
    fieldset.disabled = state.locked || state.busy || submitting
    status.textContent = state.locked ? 'Read-only' : feedback
  }

  const context = await panel.getContext()
  state = context
  applyConfig(context.config)
  panel.onStateChange(next => {
    state = next
    updateControls()
  })
  panel.onConfigReloaded(({ config }) => applyConfig(config))
  updateControls()

  form.addEventListener('input', async ({ target: input }) => {
    if (!inputs.includes(input)) return
    showError(input)
    feedback = 'Unsaved changes'
    updateControls()
    if (!input.validity.valid) return
    try {
      const result = await panel.saveConfig([changeFor(input)], 'draft')
      if (!result.ok) feedback = result.message
    } catch {
      feedback = 'Could not update the draft.'
    }
    updateControls()
  })

  form.addEventListener('submit', async event => {
    event.preventDefault()
    const changes = inputs.map(changeFor)
    submitting = true
    updateControls()
    try {
      const result = await panel.saveConfig(changes)
      feedback = result.ok ? 'Saved' : result.message
      for (const input of inputs)
        showError(input, result.ok ? '' : result.fieldErrors?.[fieldKey(input)])
    } catch {
      feedback = 'Could not save the plan.'
    } finally {
      submitting = false
      updateControls()
    }
  })
}

start().catch(error => {
  status.textContent = error.message
})
