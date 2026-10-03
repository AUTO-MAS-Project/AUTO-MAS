import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, reactive, type SetupContext } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import {
  defineMaaFWLazyComponent,
  type MaaFWFlavor,
  type MaaFWFlavorPart,
  type MaaFWFlavorSlotContextMap,
  type MaaFWFlavorSlotName,
  type MaaFWScriptSlotContext,
  type MaaFWUserFormData,
  type MaaFWUserSlotContext,
} from '@/composables/maafwFlavorTypes'
import type { MaaFWScriptConfig } from '@/types/script'
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
  previewData: null,
  scriptId: 's1',
  ...overrides,
})

const makeScriptContext = (): MaaFWScriptSlotContext => ({
  scriptId: 's1',
  maafwConfig: reactive({
    Info: { Name: 'n' },
    Run: { GameUpdateMode: 'Off' },
  }) as unknown as MaaFWScriptConfig,
  previewData: null,
  interfaceDisabled: false,
  loading: false,
  isWizard: true,
})

async function renderPartSlot<P extends MaaFWFlavorPart>(
  part: P,
  name: MaaFWFlavorSlotName<P>,
  flavor: MaaFWFlavor,
  context: MaaFWFlavorSlotContextMap[P][MaaFWFlavorSlotName<P>],
  listeners: Record<string, (...args: never[]) => void> = {}
): Promise<string> {
  const app = createSSRApp(MaaFWFlavorSlot, { part, name, flavor, context, ...listeners })
  app.use(i18n)
  for (const [stubName, component] of Object.entries(stubs)) app.component(stubName, component)
  return (await renderToString(app)).replace(/<!--[\s\S]*?-->/g, '')
}

/** 用户页「任务队列两栏之上」的插入点（MSS 的两个区块在这里） */
const renderSlot = (
  flavor: MaaFWFlavor,
  context: MaaFWUserSlotContext,
  onSave: (key: string, value: unknown) => void = () => undefined
) => renderPartSlot('userPage', 'beforeTaskQueue', flavor, context, { onSave })

const SCRIPT_SLOTS = [
  'afterBasicInfo',
  'beforeControl',
  'besidePackageName',
  'afterControl',
  'afterUpdate',
  'afterRun',
] as const
const USER_SLOTS = ['afterBasicInfo', 'beforeTaskQueue', 'afterTaskQueue'] as const

/** 记录收到的 context 与全部监听，并在 setup 里替用户发一次事件 */
const recorded: Array<{ name: string; context: unknown; attrs: string[] }> = []
const reportingSlot = (name: string, event: string, args: unknown[]) =>
  defineMaaFWLazyComponent(async () =>
    defineComponent({
      props: { context: { type: Object, required: true } },
      emits: [event],
      setup(props, { attrs, emit }) {
        recorded.push({ name, context: props.context, attrs: Object.keys(attrs) })
        emit(event, ...args)
        return () => h('p', name)
      },
    })
  )

afterEach(() => {
  delete actions.select
  delete actions.switchTo
  mssPlanComboxItems.value = null
  recorded.length = 0
})

describe('MaaFWFlavorSlot 插入点渲染器', () => {
  it('只有登记了组件的插入点有东西：M9A 包名旁，MSS 控制方式前与用户页队列上方；MaaFW 一处都没有', async () => {
    const occupied = new Set([
      'M9A:scriptPage:besidePackageName',
      'MSS:scriptPage:beforeControl',
      'MSS:userPage:beforeTaskQueue',
    ])
    for (const type of ['MaaFW', 'M9A', 'MSS']) {
      const flavor = resolveMaaFWFlavor(type)
      for (const name of SCRIPT_SLOTS) {
        const html = await renderPartSlot('scriptPage', name, flavor, makeScriptContext())
        expect([type, name, html !== '']).toEqual([
          type,
          name,
          occupied.has(`${type}:scriptPage:${name}`),
        ])
      }
      for (const name of USER_SLOTS) {
        const html = await renderPartSlot('userPage', name, flavor, makeContext())
        expect([type, name, html !== '']).toEqual([
          type,
          name,
          occupied.has(`${type}:userPage:${name}`),
        ])
      }
    }
  })

  it('MSS 控制方式提示与 M9A 游戏更新下拉的文案与改前相同', async () => {
    const mssHint = await renderPartSlot(
      'scriptPage',
      'beforeControl',
      resolveMaaFWFlavor('MSS'),
      makeScriptContext()
    )
    expect(mssHint).toContain('AAlert flavor-controller-hint')
    expect(mssHint).toContain(zhCN.edit.mssFlavorControllerHint)
    const m9aGameUpdate = await renderPartSlot(
      'scriptPage',
      'besidePackageName',
      resolveMaaFWFlavor('M9A'),
      makeScriptContext()
    )
    // 三档与后端 Run.GameUpdateMode 一致，值取自脚本配置草稿
    expect(m9aGameUpdate).toContain('ASelect')
    for (const label of [
      zhCN.edit.mfwGameUpdateOff,
      zhCN.edit.mfwGameUpdateCheck,
      zhCN.edit.mfwGameUpdateAutoInstall,
    ]) {
      expect(m9aGameUpdate).toContain(label)
    }
  })

  it('脚本页插入点：只渲染这一页这个位置的组件，change 原样交回页面，不挂 save', async () => {
    const base = resolveMaaFWFlavor('MaaFW')
    const flavor: MaaFWFlavor = {
      ...base,
      scriptPage: {
        ...base.scriptPage,
        slots: {
          afterControl: [reportingSlot('script:afterControl', 'change', ['Game', 'Foo', 1])],
        },
      },
      userPage: {
        ...base.userPage,
        slots: { afterBasicInfo: [reportingSlot('user:afterBasicInfo', 'save', ['Info.X', 1])] },
      },
    }
    const onChange = vi.fn()
    const onSave = vi.fn()
    const context = makeScriptContext()
    const html = await renderPartSlot('scriptPage', 'afterControl', flavor, context, {
      onChange,
      onSave,
    })
    expect(html).toBe('<p>script:afterControl</p>')
    expect(onChange.mock.calls).toEqual([['Game', 'Foo', 1]])
    expect(onSave).not.toHaveBeenCalled()
    expect(recorded).toEqual([{ name: 'script:afterControl', context, attrs: [] }])
    // 同名的位置在另一页是另一个插入点
    expect(await renderPartSlot('scriptPage', 'afterBasicInfo', flavor, context)).toBe('')
  })

  it('用户页插入点：save 原样交回页面，不挂 change；上下文带只读的 interface 与脚本 id', async () => {
    const base = resolveMaaFWFlavor('MaaFW')
    const flavor: MaaFWFlavor = {
      ...base,
      userPage: {
        ...base.userPage,
        slots: {
          afterBasicInfo: [reportingSlot('user:afterBasicInfo', 'save', ['Info.X', 1])],
          afterTaskQueue: [reportingSlot('user:afterTaskQueue', 'save', ['Info.Y', 2])],
        },
      },
    }
    const onChange = vi.fn()
    const onSave = vi.fn()
    const context = makeContext({ previewData: { tasks: [] } as never })
    expect(
      await renderPartSlot('userPage', 'afterBasicInfo', flavor, context, { onChange, onSave })
    ).toBe('<p>user:afterBasicInfo</p>')
    expect(
      await renderPartSlot('userPage', 'afterTaskQueue', flavor, context, { onChange, onSave })
    ).toBe('<p>user:afterTaskQueue</p>')
    expect(onSave.mock.calls).toEqual([
      ['Info.X', 1],
      ['Info.Y', 2],
    ])
    expect(onChange).not.toHaveBeenCalled()
    expect(recorded.map(entry => entry.attrs)).toEqual([[], []])
    expect(recorded[0].context).toMatchObject({ scriptId: 's1', previewData: { tasks: [] } })
  })

  it('新建流程插入点：只读，三个类型都什么都不插；声明了就渲染，不挂任何监听', async () => {
    const context = { type: 'MaaFW', selection: 'new' } as const
    for (const type of ['MaaFW', 'M9A', 'MSS']) {
      expect([
        type,
        await renderPartSlot('create', 'afterSourceStep', resolveMaaFWFlavor(type), context),
      ]).toEqual([type, ''])
    }
    const base = resolveMaaFWFlavor('MaaFW')
    const flavor: MaaFWFlavor = {
      ...base,
      create: {
        ...base.create,
        slots: { afterSourceStep: [reportingSlot('create:afterSourceStep', 'change', [1])] },
      },
    }
    const onChange = vi.fn()
    const onSave = vi.fn()
    expect(
      await renderPartSlot('create', 'afterSourceStep', flavor, context, { onChange, onSave })
    ).toBe('<p>create:afterSourceStep</p>')
    expect(onChange).not.toHaveBeenCalled()
    expect(onSave).not.toHaveBeenCalled()
    expect(recorded).toEqual([{ name: 'create:afterSourceStep', context, attrs: [] }])
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
    const base = resolveMaaFWFlavor('MaaFW')
    const flavor: MaaFWFlavor = {
      ...base,
      userPage: {
        ...base.userPage,
        slots: {
          beforeTaskQueue: [
            defineMaaFWLazyComponent(load),
            defineMaaFWLazyComponent(async () =>
              defineComponent({ setup: () => () => h('p', '第二个') })
            ),
          ],
        },
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
