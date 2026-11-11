import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { expect, it, vi } from 'vite-plus/test'
import messages from '../../../../../../res/i18n/en.json'
import OkwwAccountSwitchField from './OkwwAccountSwitchField.vue'

vi.mock('@/components/FieldLabelWithHint.vue', () => ({ default: { render: () => null } }))

it('offers separate per-account and batch native switching choices', async () => {
  const app = createSSRApp({ render: () => h(OkwwAccountSwitchField, { modelValue: 'OKWW' }) })
  app.use(createI18n({ legacy: false, locale: 'en', flatJson: true, messages: { en: messages } }))
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
    'ASelect',
    defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          h('select', slots.default?.()),
    })
  )
  app.component(
    'ATooltip',
    defineComponent({
      props: ['title'],
      setup:
        (props, { slots }) =>
        () =>
          h('span', { 'data-hint': props.title }, slots.default?.()),
    })
  )
  app.component(
    'ASelectOption',
    defineComponent({
      props: ['value'],
      setup:
        (props, { slots }) =>
        () =>
          h('option', { value: props.value }, slots.default?.()),
    })
  )
  const html = await renderToString(app)
  expect(html).toContain('value="NONE"')
  expect(html).toContain('value="MAS"')
  expect(html).toContain('value="OKWW_SINGLE"')
  expect(html).toContain('value="OKWW"')
  expect(html).toContain('ok-ww: one account per run')
  expect(html).toContain('ok-ww: batch switching')
  expect(html).toContain('No switching')
  expect(html).toContain('data-hint="Run tasks with the account currently signed in to the game."')
  expect(html).toContain('data-hint="MAS switches accounts before each run.')
  expect(html).toContain(
    'data-hint="ok-ww switches accounts. Each account starts a separate script run'
  )
  expect(html).toContain('data-hint="ok-ww switches accounts within one script process')
})
