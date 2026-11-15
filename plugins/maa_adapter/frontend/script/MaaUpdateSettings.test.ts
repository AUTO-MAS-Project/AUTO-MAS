import { renderToString } from '@vue/server-renderer'
import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, reactive } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMaaScriptDraft } from './maaScriptDraft'
import MaaUpdateSettings from './MaaUpdateSettings.vue'

vi.mock('@/composables/useScriptApi', () => ({
  useScriptApi: () => ({ queryMirrorCdk: vi.fn().mockResolvedValue({ status: 'absent' }) }),
}))
vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/MirrorCdkStatusHint.vue', () => ({ default: { render: () => null } }))

const Select = defineComponent({
  props: ['value', 'options', 'disabled'],
  emits: ['change'],
  setup(props) {
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

describe('MAA script update channel', () => {
  it('disables channel selection until the script configuration has loaded', async () => {
    const { html } = await renderPanel(false)
    expect(html).toMatch(/<select\b[^>]*\bdisabled(?:\s|>)/)
  })
})
