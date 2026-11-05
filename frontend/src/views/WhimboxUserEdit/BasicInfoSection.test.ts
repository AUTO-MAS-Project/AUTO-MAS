import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import messages from '../../../../res/i18n/en.json'
import BasicInfoSection from './BasicInfoSection.vue'

vi.mock('@/views/EditView/User/components/UserNameField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/views/EditView/User/components/UserStatusField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/views/EditView/User/components/UserRemainedDayField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/views/EditView/User/components/UserNotesField.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))

const renderSection = async (base: string, override: boolean) => {
  const app = createSSRApp({
    render: () =>
      h(BasicInfoSection, {
        loading: false,
        formData: {
          userName: 'Demo account',
          Info: {
            Name: 'Demo account',
            Status: true,
            Base: base,
            IfQuickConfig: override,
            RemainedDay: -1,
            Notes: '',
            Tag: '',
          },
        },
      }),
  })
  app.use(createI18n({ legacy: false, locale: 'en', flatJson: true, messages: { en: messages } }))
  const container = defineComponent({
    props: ['message'],
    setup:
      (props, { slots }) =>
      () =>
        h('div', [props.message, slots.default?.()]),
  })
  for (const name of ['ARow', 'ACol', 'AFormItem', 'AAlert', 'ATooltip', 'ATag']) {
    app.component(name, container)
  }
  app.component(
    'ARadioGroup',
    defineComponent({
      setup:
        (_, { attrs, slots }) =>
        () =>
          h('fieldset', attrs, slots.default?.()),
    })
  )
  app.component('ARadio', defineComponent({ render: () => h('input', { type: 'radio' }) }))
  return (await renderToString(app)).replace(/&#39;/g, "'")
}

describe('Whimbox configuration source guidance', () => {
  it.each(['shared', 'independent'])('does not promise a shared base for %s', async base => {
    const html = await renderSection(base, false)
    expect(html).toContain('they do not share one base configuration across this managed script')
    expect(html).not.toContain('the copy shared by every account of this managed script')
    expect(html).not.toContain('aria-label="Enable overriding the standard configuration"')
  })

  it.each([false, true])('shows the native override effect when enabled=%s', async override => {
    const html = await renderSection('native', override)
    expect(html).toContain('aria-label="Enable overriding the standard configuration"')
    expect(html).toContain(
      override
        ? "Overrides the script's own configuration with the fields on this page"
        : "Runs on the external script's native configuration as is"
    )
    expect(html).not.toContain('MAS writes nothing')
  })
})
