import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, type Component } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import Antd from 'ant-design-vue'
import NativeConfigForm from './NativeConfigForm.vue'
import { OkwwConfigField } from '@/api'
async function render(
  fields: OkwwConfigField[],
  values: Record<string, unknown>,
  disabled = false,
  labels: Record<string, string> = {},
  onChange?: (name: string, value: unknown) => void,
  stubs: Record<string, Component> = {}
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
        onChange,
      }),
  })
  app.use(Antd)
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  for (const [name, component] of Object.entries(stubs)) app.component(name, component)
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
    expect(html).toMatch(/<button[^>]*role="switch"[^>]*aria-checked="true"/)
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

  it('submits integers as numbers and keeps text local until blur', async () => {
    const change = vi.fn()
    const controls: Record<
      string,
      { attrs: Record<string, unknown>; emit: (event: string, ...args: unknown[]) => void }
    > = {}
    const stub = (name: string) =>
      defineComponent({
        inheritAttrs: false,
        setup(_, { attrs, emit }) {
          controls[name] = { attrs, emit }
          return () => h('input', { value: attrs.value })
        },
      })
    await render(
      [
        { name: 'Count', type: OkwwConfigField.type.NUMBER, integer: true, minimum: 1 },
        { name: 'Name', type: OkwwConfigField.type.STRING },
      ],
      { Count: 2, Name: 'initial' },
      false,
      {},
      change,
      { 'a-input-number': stub('number'), 'a-input': stub('text') }
    )

    const number = controls.number!
    const input = controls.text!
    expect(number.attrs).toMatchObject({ value: 2, precision: 0, min: 1 })
    expect(input.attrs.value).toBe('initial')
    number.emit('update:value', '3')
    expect(change.mock.calls).toEqual([['Count', 3]])

    number.emit('update:value', null)
    input.emit('update:value', 'first edit')
    input.emit('update:value', 'final edit')
    expect(change.mock.calls).toEqual([['Count', 3]])
    input.emit('blur')
    expect(change.mock.calls).toEqual([
      ['Count', 3],
      ['Name', 'final edit'],
    ])
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
