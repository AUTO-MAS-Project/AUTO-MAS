import { expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import OkNteConfigFieldControl from './OkNteConfigFieldControl.vue'

it.each([
  ['bool', 'a-switch', 'update:checked', { checked: true }, false],
  [
    'select',
    'a-select',
    'update:value',
    {
      value: '1',
      options: [
        { value: '1', label: 'First' },
        { value: '2', label: 'Second' },
      ],
    },
    '2',
  ],
  ['int', 'a-input-number', 'update:value', { value: 2, precision: 0, min: 1, max: 8 }, 4],
  ['float', 'a-input-number', 'update:value', { value: 2.5, precision: undefined, step: 0.5 }, 3.5],
  ['string', 'a-input', 'update:value', { value: 'initial' }, 'edited'],
] as const)(
  'renders and updates an OK-NTE %s field',
  async (type, controlName, eventName, expected, nextValue) => {
    const change = vi.fn()
    const modelValue = 'checked' in expected ? expected.checked : expected.value
    const app = createSSRApp(() =>
      h(OkNteConfigFieldControl, {
        field: {
          name: 'Field',
          label: 'Display name',
          type,
          options: type === 'select' ? ['1', '2'] : null,
          min: 1,
          max: 8,
          step: type === 'float' ? 0.5 : null,
        },
        optionLabels: { '1': 'First', '2': 'Second' },
        modelValue,
        disabled: false,
        onChange: change,
      })
    )
    app.use(createI18n({ legacy: false, locale: 'en' }))
    let emitControl!: (event: string, value?: unknown) => void
    app.component(
      controlName,
      defineComponent({
        inheritAttrs: false,
        setup(_, { attrs, emit }) {
          expect(attrs).toMatchObject(expected)
          emitControl = emit
          return () => h('span', { 'data-control': controlName })
        },
      })
    )
    expect(await renderToString(app)).toContain(`data-control="${controlName}"`)
    if (controlName === 'a-input-number') {
      emitControl(eventName, null)
      expect(change).not.toHaveBeenCalled()
    }
    emitControl(eventName, nextValue)
    expect(change.mock.calls).toEqual([[nextValue]])
  }
)
