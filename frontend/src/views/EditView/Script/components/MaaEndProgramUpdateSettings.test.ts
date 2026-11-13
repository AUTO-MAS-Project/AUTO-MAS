import { renderToString } from '@vue/server-renderer'
import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, reactive } from 'vue'
import { createI18n } from 'vue-i18n'
import MaaEndProgramUpdateSettings from './MaaEndProgramUpdateSettings.vue'

vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))
const control = (kind: string) =>
  defineComponent({
    props: ['checked', 'value', 'disabled', 'options'],
    emits: ['update:checked', 'update:value', 'change', 'blur'],
    setup(props) {
      return () =>
        kind === 'select'
          ? h(
              'select',
              { 'data-kind': kind, disabled: props.disabled },
              props.options.map((item: { value: string; label: string }) =>
                h('option', { value: item.value, selected: item.value === props.value }, item.label)
              )
            )
          : h('input', { 'data-kind': kind, disabled: props.disabled })
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
    PackageMode: 'full' as 'full' | 'incremental',
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
  app.use(
    createI18n({
      legacy: false,
      locale: 'zh',
      flatJson: true,
      messages: {
        zh: {
          'core.setting.channel.stable': '稳定版',
          'core.setting.channel.beta': '公测版',
        },
      },
      missingWarn: false,
      fallbackWarn: false,
    })
  )
  for (const name of ['ARow', 'ACol', 'AFormItem']) app.component(name, passthrough)
  app.component('ASwitch', control('switch'))
  app.component('ASelect', control('select'))
  app.component('AInputPassword', control('password'))
  return { update, saved, html: await renderToString(app) }
}

describe('MaaEnd program update settings', () => {
  it('disables all controls before initial configuration is loaded', async () => {
    const { html } = await renderPanel(false)
    expect(html).toMatch(/<select\b[^>]*\bdisabled(?:\s|>)/)
    expect(html).toMatch(/<input\b[^>]*data-kind="switch"[^>]*\bdisabled(?:\s|>)/)
    expect(html).toMatch(/<input\b[^>]*data-kind="password"[^>]*\bdisabled(?:\s|>)/)
  })
})
