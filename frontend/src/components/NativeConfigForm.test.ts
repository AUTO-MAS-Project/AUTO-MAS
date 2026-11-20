import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import Antd from 'ant-design-vue'
import NativeConfigForm from './NativeConfigForm.vue'
import { OkwwConfigField } from '@/api'
async function render(
  fields: OkwwConfigField[],
  values: Record<string, unknown>,
  disabled = false,
  labels: Record<string, string> = {}
) {
  const app = createSSRApp({
    render: () =>
      h(NativeConfigForm, {
        fields,
        labels,
        values,
        disabled,
        labelPrefix: 'label.',
        optionPrefix: 'option.',
      }),
  })
  app.use(Antd)
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  return renderToString(app)
}
describe('native configuration form', () => {
  it('renders newly supplied fields without a task-specific template', async () => {
    const html = await render(
      [
        { name: 'New limit', type: OkwwConfigField.type.NUMBER },
        { name: 'New object', type: OkwwConfigField.type.JSON },
        { name: 'New flag', type: OkwwConfigField.type.BOOL },
      ],
      { 'New limit': 2.5, 'New object': { nested: true }, 'New flag': true }
    )
    expect(html).toContain('New limit')
    expect(html).toContain('value="2.5"')
    expect(html).toContain('nested')
    expect(html).toContain('New flag')
  })
  it('uses descriptor conditions and inherits the edit lock', async () => {
    const fields: OkwwConfigField[] = [
      {
        name: 'Target index',
        type: OkwwConfigField.type.NUMBER,
        parent: 'Destination',
        choices: ['Weekly'],
      },
    ]
    expect(await render(fields, { Destination: 'No', 'Target index': 3 })).not.toContain(
      'Target index'
    )
    const html = await render(fields, { Destination: 'Weekly', 'Target index': 3 }, true)
    expect(html).toContain('Target index')
    expect(html).toMatch(/<input[^>]*disabled/)
  })
})

describe('native labels and multiple choices', () => {
  it('prefers upstream labels over display fallbacks while retaining raw values', async () => {
    const html = await render(
      [{ name: 'Echo Pickup Method', type: OkwwConfigField.type.SELECT, options: ['Walk'] }],
      { 'Echo Pickup Method': 'Walk' },
      false,
      { 'Echo Pickup Method': '搜索声骸方法', Walk: '后退再前进' }
    )
    expect(html).toContain('搜索声骸方法')
    expect(html).toContain('后退再前进')
  })
  it('renders multiple choices as checkboxes with the selected values checked', async () => {
    const html = await render(
      [
        {
          name: 'Additional',
          type: OkwwConfigField.type.MULTI_SELECTION,
          options: ['first', 'second'],
        },
      ],
      { Additional: ['first'] },
      false,
      { first: '任务一', second: '任务二' }
    )
    expect(html.match(/type="checkbox"/g)).toHaveLength(2)
    expect(html.match(/ant-checkbox-checked/g)).toHaveLength(1)
    expect(html).toContain('任务一')
    expect(html).toContain('任务二')
    expect(html).not.toContain('role="combobox"')
  })
})

it('locks only descriptor-managed fields, leaving other settings editable', async () => {
  const html = await render(
    [
      { name: 'Planned number', type: OkwwConfigField.type.NUMBER, disabled: true },
      { name: 'Account switch', type: OkwwConfigField.type.BOOL },
    ],
    { 'Planned number': 2, 'Account switch': false }
  )
  expect(html).toMatch(/<input[^>]*disabled/)
  expect(html).not.toMatch(/<button[^>]*disabled/)
})
