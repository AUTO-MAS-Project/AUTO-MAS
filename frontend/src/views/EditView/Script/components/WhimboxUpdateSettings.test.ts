import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import WhimboxUpdateSettings from './WhimboxUpdateSettings.vue'

vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))

const renderPanel = async (ready: boolean) => {
  const update = reactive({ TakeoverEnabled: false })
  const saved: boolean[] = []
  let toggle: (value: boolean) => void = () => {}
  const app = createSSRApp({
    render: () =>
      h(WhimboxUpdateSettings, {
        update,
        ready,
        'onUpdate:update': value => Object.assign(update, value),
        onChange: value => saved.push(value),
      }),
  })
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  app.component(
    'AFormItem',
    defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          h('div', slots.default?.()),
    })
  )
  app.component(
    'ASwitch',
    defineComponent({
      props: ['checked', 'disabled'],
      emits: ['change'],
      setup(props, { emit }) {
        toggle = value => {
          if (!props.disabled) emit('change', value)
        }
        return () =>
          h('input', { type: 'checkbox', checked: props.checked, disabled: props.disabled })
      },
    })
  )
  const html = await renderToString(app)
  return { html, update, saved, toggle }
}

describe('Whimbox pre-run update settings', () => {
  it('starts disabled and saves enabling and disabling', async () => {
    const { update, saved, toggle } = await renderPanel(true)
    expect(update.TakeoverEnabled).toBe(false)
    toggle(true)
    expect(update.TakeoverEnabled).toBe(true)
    toggle(false)
    expect(update.TakeoverEnabled).toBe(false)
    expect(saved).toEqual([true, false])
  })

  it('prevents saving while the script is loading', async () => {
    const { html, saved, toggle } = await renderPanel(false)
    expect(html).toContain('disabled')
    toggle(true)
    expect(saved).toEqual([])
  })
})
