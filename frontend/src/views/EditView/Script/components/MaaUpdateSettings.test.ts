import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, reactive } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import MaaUpdateSettings from './MaaUpdateSettings.vue'
import { createMaaScriptDraft } from '../maaScriptDraft'

vi.mock('@/composables/useScriptApi', () => ({
  useScriptApi: () => ({ queryMirrorCdk: vi.fn().mockResolvedValue({ status: 'absent' }) }),
}))
vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/MirrorCdkStatusHint.vue', () => ({ default: { render: () => null } }))

let selectChange: ((value: string) => void) | undefined
const Select = defineComponent({
  props: ['value', 'options', 'disabled'],
  emits: ['change'],
  setup(props, { emit }) {
    selectChange = value => emit('change', value)
    return () =>
      h(
        'select',
        { disabled: props.disabled },
        props.options.map((item: { label: string; value: string }) =>
          h('option', { value: item.value, selected: item.value === props.value }, item.label)
        )
      )
  },
})
const Passthrough = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      h('div', slots.default?.()),
})

const renderPanel = async (ready = true) => {
  const draft = reactive(createMaaScriptDraft())
  const saved: unknown[] = []
  const app = createSSRApp({
    render: () =>
      h(MaaUpdateSettings, {
        update: draft.Update,
        ready,
        'onUpdate:update': value => {
          draft.Update = value
        },
        onChange: (key, value) => {
          saved.push([key, value])
        },
      }),
  })
  app.use(
    createI18n({
      legacy: false,
      locale: 'zh',
      flatJson: true,
      messages: {
        zh: {
          'core.edit.updateTakeover': '更新接管',
          'core.edit.updateChannel': '更新通道',
          'core.setting.channel.stable': '稳定版',
          'core.setting.channel.beta': '公测版',
          'core.edit.updateTakeoverSwitch': '接管更新',
        },
      },
      missingWarn: false,
      fallbackWarn: false,
    })
  )
  for (const name of ['a-row', 'a-col', 'a-form-item', 'a-switch', 'a-input-password'])
    app.component(name, Passthrough)
  app.component('ASelect', Select)
  return { html: await renderToString(app), draft, saved }
}

beforeEach(() => {
  selectChange = undefined
})

describe('MAA script update channel', () => {
  it('renders stable and beta in the script settings with stable as default', async () => {
    const { html, draft } = await renderPanel()
    expect(html).toContain('稳定版')
    expect(html).toContain('公测版')
    expect(draft.Update.Channel).toBe('stable')
  })
  it('saves the selected channel as a script update field', async () => {
    const { draft, saved } = await renderPanel()
    selectChange?.('beta')
    expect(draft.Update.Channel).toBe('beta')
    expect(saved).toEqual([['Channel', 'beta']])
  })
  it('disables channel selection until the script configuration has loaded', async () => {
    const { html } = await renderPanel(false)
    expect(html).toMatch(/<select\b[^>]*\bdisabled(?:\s|>)/)
  })
})
