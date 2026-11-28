import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import Antd from 'ant-design-vue'
import dayjs from 'dayjs'
import DeclarativeControl from './DeclarativeControl.vue'

type Props = InstanceType<typeof DeclarativeControl>['$props']

/** Node 中通过 AntD 控件公开的事件操作真实表单，无需浏览器或 DOM。 */
async function render(props: Props, ...controls: string[]) {
  const update = vi.fn()
  const app = createSSRApp(() => h(DeclarativeControl, { ...props, 'onUpdate:modelValue': update }))
  app.use(Antd)
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  const inputs: Record<
    string,
    Array<{
      attrs: Record<string, unknown>
      emit: (name: string, ...args: unknown[]) => void
    }>
  > = {}
  for (const name of controls) {
    inputs[name] = []
    app.component(
      name,
      defineComponent({
        inheritAttrs: false,
        setup(_, { attrs, emit, slots }) {
          inputs[name]!.push({ attrs, emit })
          return () => h('span', slots.overlay?.() ?? String(attrs.value ?? ''))
        },
      })
    )
  }
  const html = await renderToString(app)
  return { inputs, update, html }
}

describe('声明式控件的读写契约', () => {
  it.each([{ widget: 'textarea' }, { component: 'textarea' }])('保留多行文本 %o', async props => {
    const { inputs, update } = await render({ ...props, modelValue: 'a\nb' }, 'a-textarea')
    const input = inputs['a-textarea']![0]!
    expect(input.attrs.value).toBe('a\nb')
    input.emit('update:value', 'b\nc')
    expect(update).toHaveBeenCalledWith('b\nc')
  })

  it('按格式读取时分，日期时间编辑后保留秒与时区', async () => {
    const time = await render({ format: 'time', modelValue: '09:10:00' }, 'a-time-picker')
    const clock = time.inputs['a-time-picker']![0]!
    expect(clock.attrs).toMatchObject({ value: '09:10', 'value-format': 'HH:mm' })
    clock.emit('change', '12:35')
    expect(time.update).toHaveBeenCalledWith('12:35')

    const datetime = await render(
      { component: 'datetime', modelValue: '2026-06-01T09:10:11' },
      'a-date-picker'
    )
    const calendar = datetime.inputs['a-date-picker']![0]!
    expect(calendar.attrs).toHaveProperty('show-time')
    calendar.emit('change', dayjs('2026-06-02T14:15:16'))
    expect(datetime.update).toHaveBeenCalledWith(
      expect.stringMatching(/^2026-06-02T14:15:16[+-]\d\d:\d\d$/)
    )
  })

  it.each([
    { component: 'date', picker: 'a-date-picker', modelValue: '2026-06-01', nullable: false },
    {
      component: 'datetime',
      picker: 'a-date-picker',
      modelValue: '2026-06-01T09:10:11',
      required: true,
    },
    { component: 'time', picker: 'a-time-picker', modelValue: '09:10', nullable: false },
  ])(
    '$component 清空提交 null，必填或非空字段禁用清空',
    async ({ picker, component, modelValue, ...constraint }) => {
      const { inputs, update } = await render({ component, modelValue }, picker)
      inputs[picker]![0]!.emit('change', null)
      expect(update).toHaveBeenCalledWith(null)

      const constrained = await render({ component, modelValue, ...constraint }, picker)
      expect(constrained.inputs[picker]![0]!.attrs['allow-clear']).toBe(false)
    }
  )

  it('表格开关提交布尔值，数字框按所在布局选择尺寸', async () => {
    const toggle = await render(
      { component: 'switch', compact: true, modelValue: true },
      'a-switch'
    )
    const input = toggle.inputs['a-switch']![0]!
    expect(input.attrs.checked).toBe(true)
    input.emit('update:checked', false)
    expect(toggle.update).toHaveBeenCalledWith(false)
    for (const compact of [true, false]) {
      const number = await render({ component: 'number', compact }, 'a-input-number')
      expect(number.inputs['a-input-number']![0]!.attrs.size).toBe(compact ? 'middle' : 'large')
    }
  })

  it.each([true, false])('数字框连续键入只改草稿，失焦或步进才提交 (compact=%s)', async compact => {
    const onBlur = vi.fn()
    const onCommit = vi.fn()
    const { inputs, update } = await render(
      { component: 'number', compact, onBlur, onCommit },
      'a-input-number'
    )
    const input = inputs['a-input-number']![0]!
    input.emit('update:value', 1)
    input.emit('update:value', 12)
    expect(update).toHaveBeenLastCalledWith(12)
    expect(onCommit).not.toHaveBeenCalled()
    expect(onBlur).not.toHaveBeenCalled()
    input.emit('blur')
    expect(onBlur).toHaveBeenCalledOnce()
    input.emit('update:value', 13)
    input.emit('step', 13, { offset: 1, type: 'up' })
    expect(update).toHaveBeenLastCalledWith(13)
    expect(onCommit).toHaveBeenCalledOnce()
  })

  it.each(['bool', 'boolean', 'checkbox', 'toggle-button'])(
    '旧组件名 %s 使用普通输入框',
    async component => {
      const { inputs, html } = await render(
        { component, compact: true, modelValue: 'text' },
        'a-input'
      )
      expect(inputs['a-input']?.[0]?.attrs.value).toBe('text')
      expect(html).not.toContain('role="switch"')
    }
  )

  it('分段选择提交原始布尔值', async () => {
    const { inputs, update } = await render(
      {
        widget: 'segmented',
        options: [
          { value: true, label: 'Yes' },
          { value: false, label: 'No' },
        ],
      },
      'a-segmented'
    )
    const control = inputs['a-segmented']![0]!
    const options = control.attrs.options as Array<{ label: string; value: number }>
    control.emit('update:value', options.find(o => o.label === 'No')!.value)
    expect(update).toHaveBeenCalledWith(false)
  })

  it('下拉动作保留所选项的值和类型，普通动作提交 true', async () => {
    const dropdown = await render(
      { component: 'dropdown-button', options: [{ value: 1 }, { value: '1' }] },
      'a-dropdown',
      'a-menu-item'
    )
    dropdown.inputs['a-menu-item']![1]!.emit('click')
    expect(dropdown.update).toHaveBeenCalledWith('1')

    const button = await render({ component: 'button' }, 'a-button')
    button.inputs['a-button']![0]!.emit('click')
    expect(button.update).toHaveBeenCalledWith(true)
  })

  it('引用字段使用选择框并提交选中引用', async () => {
    const { inputs, update } = await render({ component: 'ref-select' }, 'a-select')
    inputs['a-select']![0]!.emit('update:value', 'ref-id')
    expect(update).toHaveBeenCalledWith('ref-id')
  })

  it('移动、移除和新增均保留选项类型及未改动选项的顺序', async () => {
    const selected = [1, '1']
    const { inputs, update } = await render(
      {
        component: 'select',
        multiple: true,
        ordered: true,
        modelValue: selected,
        options: [{ value: 1 }, { value: '1' }, { value: false, label: 'Off' }],
      },
      'a-button',
      'a-select'
    )
    const buttons = inputs['a-button']!
    const up = buttons.filter(button => button.attrs['aria-label'] === 'core.setting.tray.moveUp')
    expect(up[0]!.attrs.disabled).toBe(true)
    up[1]!.emit('click')
    expect(update).toHaveBeenLastCalledWith(['1', 1])
    buttons
      .find(button => button.attrs['aria-label'] === 'core.setting.tray.moveDown')!
      .emit('click')
    expect(update).toHaveBeenLastCalledWith(['1', 1])
    buttons.find(button => button.attrs['aria-label'] === 'core.comp.delete')!.emit('click')
    expect(update).toHaveBeenLastCalledWith(['1'])
    const add = inputs['a-select']![0]!
    const choices = add.attrs.options as Array<{ label: string; value: number }>
    expect(choices.map(option => option.label)).toEqual(['Off'])
    add.emit('update:value', choices[0]!.value)
    expect(update).toHaveBeenLastCalledWith([1, '1', false])
    expect(selected).toEqual([1, '1'])
  })

  it.each([{ masked: true }, { secret: true }])('密文在失焦时保留，输入才覆盖 %o', async props => {
    const sentinel = '__AUTO_MAS_CONFIG_MASKED__'
    const { inputs, update, html } = await render(
      { ...props, modelValue: sentinel },
      'a-input-password'
    )
    const input = inputs['a-input-password']![0]!
    expect(input.attrs.value).toBe('')
    expect(input.attrs.placeholder).toBeTruthy()
    expect(html).not.toContain(sentinel)
    input.emit('blur')
    expect(update).not.toHaveBeenCalled()
    input.emit('update:value', 'replacement')
    expect(update).toHaveBeenCalledWith('replacement')
  })
})
