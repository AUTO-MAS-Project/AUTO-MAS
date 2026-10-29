import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import MaaEndProgramUpdateSettings from './MaaEndProgramUpdateSettings.vue'

vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))
let switchChange: (value: boolean) => void
let channelChange: (value: string) => void
let cdkBlur: () => void
const control = (kind: string) =>
  defineComponent({
    props: ['checked', 'value', 'disabled'],
    emits: ['update:checked', 'update:value', 'change', 'blur'],
    setup(props, { emit }) {
      if (kind === 'switch')
        switchChange = value => {
          emit('update:checked', value)
          emit('change', value)
        }
      if (kind === 'select')
        channelChange = value => {
          emit('update:value', value)
          emit('change', value)
        }
      if (kind === 'password') cdkBlur = () => emit('blur')
      return () => h('input', { 'data-kind': kind, disabled: props.disabled })
    },
  })
const passthrough = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      h('div', slots.default?.()),
})
const renderPanel = async (ready: boolean) => {
  const update = reactive({
    TakeoverEnabled: false,
    Channel: 'stable' as 'stable' | 'beta',
    MirrorChyanCDK: '',
  })
  const saved: unknown[] = []
  const app = createSSRApp({
    render: () =>
      h(MaaEndProgramUpdateSettings, {
        update,
        ready,
        'onUpdate:update': value => Object.assign(update, value),
        onSave: (key, value) => saved.push([key, value]),
      }),
  })
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  for (const name of ['ARow', 'ACol', 'AFormItem']) app.component(name, passthrough)
  app.component('ASwitch', control('switch'))
  app.component('ASelect', control('select'))
  app.component('AInputPassword', control('password'))
  return { update, saved, html: await renderToString(app) }
}

beforeEach(() => {
  switchChange = () => {}
  channelChange = () => {}
  cdkBlur = () => {}
})

describe('MaaEnd program update settings', () => {
  it('keeps program takeover separate from game updates and emits only changed fields', async () => {
    const { update, saved } = await renderPanel(true)
    switchChange(true)
    channelChange('beta')
    cdkBlur()
    expect(update.TakeoverEnabled).toBe(true)
    expect(update.Channel).toBe('beta')
    expect(saved).toEqual([
      ['TakeoverEnabled', true],
      ['Channel', 'beta'],
      ['MirrorChyanCDK', ''],
    ])
  })
  it('disables all controls before initial configuration is loaded', async () => {
    const { html } = await renderPanel(false)
    expect((html.match(/disabled/g) ?? []).length).toBe(3)
  })
})
