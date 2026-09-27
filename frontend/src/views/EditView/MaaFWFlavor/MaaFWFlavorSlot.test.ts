import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, reactive, type SetupContext } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import {
  defineMaaFWFlavorSlotComponent,
  type MaaFWFlavor,
  type MaaFWUserFormData,
  type MaaFWUserSlotContext,
} from '@/composables/maafwFlavorTypes'
import MaaFWFlavorSlot from './MaaFWFlavorSlot.vue'
import { mssPlanComboxItems } from './mss/planModeOptions'

// 仓库没有 DOM 测试环境，用 vue 自带的 SSR 渲染器出 HTML（同 LaunchFailure.test.ts）。
// SSR 会等异步组件加载完再出结果，正好验证「按需加载的组件加载后显示」。

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

/** 各 stub 在 setup 里要替用户做的操作（模拟点击 / 选择） */
const actions: { select?: string; switchTo?: boolean } = {}

type StubAttrs = SetupContext['attrs'] & Record<string, unknown>
const call = (attrs: StubAttrs, name: string, ...args: unknown[]) =>
  (attrs[name] as ((...values: unknown[]) => void) | undefined)?.(...args)

const stubs = {
  AFormItem: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      return () =>
        h('div', { class: ['AFormItem', attrs.class] }, [
          h('b', String(attrs.label)),
          h('i', String(attrs.extra)),
          slots.default?.(),
        ])
    },
  }),
  AAlert: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs }) {
      return () => h('div', { class: ['AAlert', attrs.class] }, String(attrs.message))
    },
  }),
  ASelect: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs }) {
      const a = attrs as StubAttrs
      if (actions.select !== undefined) {
        call(a, 'onUpdate:value', actions.select)
        call(a, 'onChange', actions.select)
      }
      return () =>
        h(
          'div',
          { class: 'ASelect' },
          JSON.stringify({ value: a.value, options: a.options, disabled: a.disabled })
        )
    },
  }),
  ASwitch: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs }) {
      const a = attrs as StubAttrs
      if (actions.switchTo !== undefined) call(a, 'onChange', actions.switchTo)
      return () =>
        h('div', { class: 'ASwitch' }, JSON.stringify({ checked: a.checked, disabled: a.disabled }))
    },
  }),
}

const makeContext = (
  overrides: Partial<MaaFWUserSlotContext> = {},
  info: Partial<MaaFWUserFormData['Info']> = {}
): MaaFWUserSlotContext => ({
  formData: reactive({
    userName: '',
    Info: { Name: '', PlanMode: 'Fixed', ...info },
    Task: {},
    Notify: {},
    Data: {},
  }) as unknown as MaaFWUserFormData,
  loading: false,
  queuedTaskCount: 0,
  ...overrides,
})

async function renderSlot(
  flavor: MaaFWFlavor,
  context: MaaFWUserSlotContext,
  onSave: (key: string, value: unknown) => void = () => undefined
): Promise<string> {
  const app = createSSRApp(MaaFWFlavorSlot, {
    name: 'userBeforeTaskQueue',
    flavor,
    context,
    onSave,
  })
  app.use(i18n)
  for (const [name, component] of Object.entries(stubs)) app.component(name, component)
  return (await renderToString(app)).replace(/<!--[\s\S]*?-->/g, '')
}

afterEach(() => {
  delete actions.select
  delete actions.switchTo
  mssPlanComboxItems.value = null
})

describe('MaaFWFlavorSlot 插入点渲染器', () => {
  it('MaaFW / M9A 在用户页插入点什么都不渲染，也不加载 MSS 的组件', async () => {
    for (const type of ['MaaFW', 'M9A']) {
      expect(await renderSlot(resolveMaaFWFlavor(type), makeContext())).toBe('')
    }
  })

  it('当前 flavor 声明了组件才渲染，异步组件加载后按声明顺序显示', async () => {
    // 加载函数直接给组件（import() 给的模块对象由 defineAsyncComponent 自己取 default）
    const load = vi.fn(async () =>
      defineComponent({
        props: { context: { type: Object, required: true } },
        setup: props => () =>
          h('p', `队列 ${(props.context as MaaFWUserSlotContext).queuedTaskCount}`),
      })
    )
    const flavor: MaaFWFlavor = {
      ...resolveMaaFWFlavor('MaaFW'),
      slots: {
        userBeforeTaskQueue: [
          defineMaaFWFlavorSlotComponent(load),
          defineMaaFWFlavorSlotComponent(async () =>
            defineComponent({ setup: () => () => h('p', '第二个') })
          ),
        ],
      },
    }
    const html = await renderSlot(flavor, makeContext({ queuedTaskCount: 3 }))
    expect(html).toBe('<p>队列 3</p><p>第二个</p>')
    expect(load).toHaveBeenCalledOnce()
  })

  it('MSS：计划表下拉 → 空队列提示 → 活动优先开关，文案与默认值和改前一致', async () => {
    const html = await renderSlot(resolveMaaFWFlavor('MSS'), makeContext())
    const planIndex = html.indexOf('<b>计划表</b>')
    const emptyIndex = html.indexOf('任务队列是空的')
    const activityIndex = html.indexOf('<b>活动优先</b>')
    expect(planIndex).toBeGreaterThanOrEqual(0)
    expect(emptyIndex).toBeGreaterThan(planIndex)
    expect(activityIndex).toBeGreaterThan(emptyIndex)
    expect(html).toContain('flavor-plan-mode')
    expect(html).toContain('flavor-queue-empty')
    expect(html).toContain('flavor-activity-first')
    // 下拉：计划表还没取到时只有「固定」一项；说明取 MSS 的计划表提示
    expect(html).toContain(
      JSON.stringify({
        value: 'Fixed',
        options: [{ label: '固定（按任务队列里的选项）', value: 'Fixed' }],
        disabled: false,
      }).replace(/"/g, '&quot;')
    )
    expect(html).toContain(`<i>${zhCN.edit.mssFlavorPlanHint}</i>`)
    // 活动优先：后端缺省是开，字段缺失按开显示
    expect(html).toContain(
      JSON.stringify({ checked: true, disabled: false }).replace(/"/g, '&quot;')
    )
  })

  it('MSS：队列里有任务或选了计划表时不提示空队列；显式关掉的活动优先显示为关', async () => {
    const flavor = resolveMaaFWFlavor('MSS')
    expect(await renderSlot(flavor, makeContext({ queuedTaskCount: 1 }))).not.toContain(
      'flavor-queue-empty'
    )
    const html = await renderSlot(
      flavor,
      makeContext({ loading: true }, { PlanMode: 'plan-1', IfActivityFirst: false })
    )
    expect(html).not.toContain('flavor-queue-empty')
    expect(html).toContain(
      JSON.stringify({ checked: false, disabled: true }).replace(/"/g, '&quot;')
    )
  })

  it('MSS：计划表选项由注册表钩子预取的列表生成，「固定」用本地文案', async () => {
    mssPlanComboxItems.value = [
      { label: 'Fixed', value: 'Fixed' },
      { label: '周常', value: 'plan-1' },
      { label: '空', value: null },
    ]
    const html = await renderSlot(resolveMaaFWFlavor('MSS'), makeContext())
    expect(html).toContain(
      JSON.stringify([
        { label: '固定（按任务队列里的选项）', value: 'Fixed' },
        { label: '周常', value: 'plan-1' },
      ]).replace(/"/g, '&quot;')
    )
  })

  it('MSS 区块改动写进页面草稿，并经插入点把 save 交回页面', async () => {
    const onSave = vi.fn()
    const context = makeContext()
    actions.switchTo = false
    actions.select = 'plan-1'
    await renderSlot(resolveMaaFWFlavor('MSS'), context, onSave)
    expect(context.formData.Info.PlanMode).toBe('plan-1')
    expect(context.formData.Info.IfActivityFirst).toBe(false)
    expect(onSave.mock.calls).toEqual([
      ['Info.PlanMode', 'plan-1'],
      ['Info.IfActivityFirst', false],
    ])
  })
})
