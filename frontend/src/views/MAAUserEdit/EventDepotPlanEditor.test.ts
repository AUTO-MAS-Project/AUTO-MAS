import { describe, expect, it } from 'vite-plus/test'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import EventDepotPlanEditor from './EventDepotPlanEditor.vue'
import { useDepotMaintainPlanEditor } from './useDepotMaintainPlanEditor'
import type { EventDepotMaintainPlan } from './eventDepotMaintainPresets'
import type { ActivityItem } from '@/types/home'

const legacy: EventDepotMaintainPlan = {
  StageType: 'activity',
  StageIndex: 1,
  DropCount: 999,
  OrundumDropCount: 9999,
  LegacyActivityFirst: true,
  UseMedicine: true,
  MedicineCount: 2,
}
const stages: ActivityItem[] = ['31113', '31083', '31043', '搓玉'].map((drop, index) => ({
  Display: ['TL-9', 'TL-8', 'TL-7', 'TL-4'][index],
  Value: ['TL-9', 'TL-8', 'TL-7', 'TL-4'][index],
  Drop: index === 3 ? '30012' : drop,
  DropName: drop,
  Activity: {
    Tip: '',
    StageName: '',
    UtcStartTime: '',
    UtcExpireTime: '',
    TimeZone: 8,
  },
}))
const Passthrough = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      h('div', slots.default?.()),
})

async function renderEditor(rows: EventDepotMaintainPlan[], activity = stages) {
  const saved: EventDepotMaintainPlan[][] = []
  const checked: boolean[] = []
  const toggles: ((value: boolean) => void)[] = []
  const targets: ((value: number) => void)[] = []
  const values: number[] = []
  let editor!: ReturnType<typeof useDepotMaintainPlanEditor>
  const app = createSSRApp({
    setup() {
      editor = useDepotMaintainPlanEditor({
        getSavedPlans: () => JSON.stringify(rows),
        savePlans: value => saved.push(JSON.parse(value)),
        loadStageCandidates: async () => {},
        getBestStage: () => undefined,
        isLoading: () => false,
        eventMode: true,
      })
      return () =>
        h(EventDepotPlanEditor, {
          editor,
          loading: false,
          stages: activity,
          template: ['material', 'material', 'material', 'orundum'],
          activityLoading: false,
          activityError: '',
          itemOptions: [],
          itemOptionsError: '',
          inventory: {},
          depotInventoryTime: '',
        })
    },
  })
  app.use(
    createI18n({
      legacy: false,
      locale: 'zh',
      messages: { zh: {} },
      missingWarn: false,
      fallbackWarn: false,
    })
  )
  for (const name of ['AAlert', 'ASpin', 'ATooltip', 'AButton', 'NoData'])
    app.component(name, Passthrough)
  app.component(
    'ACheckbox',
    defineComponent({
      props: ['checked', 'disabled'],
      emits: ['change'],
      setup(props, { emit }) {
        checked.push(props.checked)
        toggles.push(value => emit('change', { target: { checked: value } }))
        return () => h('input', { type: 'checkbox', checked: props.checked })
      },
    })
  )
  app.component(
    'AInputNumber',
    defineComponent({
      props: ['value', 'disabled'],
      emits: ['change'],
      setup(props, { emit }) {
        values.push(props.value)
        targets.push(value => emit('change', value))
        return () => h('input', { type: 'number', value: props.value })
      },
    })
  )
  await renderToString(app)
  return { editor, saved, checked, toggles, targets, values }
}

describe('MAA activity selection migration', () => {
  it('shows the old selection without adding or saving other stages on open', async () => {
    const panel = await renderEditor([legacy])
    expect(panel.checked).toEqual([true, false, false, false])
    expect(panel.saved).toEqual([])
    expect(panel.editor.plans.value).toHaveLength(1)
  })

  it.each([
    [4, [false, false, false, true]],
    [99, [true, false, false, false]],
  ])(
    'projects old full-list index %i into the visible stage categories',
    async (index, checked) => {
      const panel = await renderEditor([{ ...legacy, StageIndex: index }])
      expect(panel.checked).toEqual(checked)
      expect(panel.saved).toEqual([])
    }
  )

  it('replaces the hidden old selection when the user saves new checkboxes', async () => {
    const rows: EventDepotMaintainPlan[] = [
      legacy,
      ...[1, 2, 3].map(index => ({
        StageType: 'material' as const,
        StageIndex: index,
        DropCount: index === 2 ? 123 : 999,
        Skip: true,
      })),
      { StageType: 'orundum', StageIndex: 1, DropCount: 9999 },
    ]
    const panel = await renderEditor(rows)
    panel.toggles[3](false)
    expect(panel.saved).toHaveLength(1)
    expect(panel.saved[0]).toHaveLength(4)
    expect(panel.saved[0].every(plan => plan.Skip && !plan.LegacyActivityFirst)).toBe(true)
    expect(panel.saved[0][1].DropCount).toBe(123)

    const reopened = await renderEditor(panel.saved[0])
    expect(reopened.checked).toEqual([false, false, false, false])
    expect(reopened.saved).toEqual([])
    reopened.toggles[0](true)
    expect(reopened.saved[0].filter(plan => !plan.Skip)).toEqual([
      expect.objectContaining({ StageType: 'material', StageIndex: 1 }),
    ])
    expect(reopened.saved[0].some(plan => plan.LegacyActivityFirst)).toBe(false)
  })

  it('keeps the other visible choices and old per-stage parameters on first target edit', async () => {
    const panel = await renderEditor([legacy])
    panel.targets[0](321)
    await panel.editor.flushPendingEdits()
    expect(panel.saved).toHaveLength(1)
    expect(panel.saved[0]).toHaveLength(4)
    expect(panel.saved[0][0]).toMatchObject({
      StageType: 'material',
      StageIndex: 1,
      DropCount: 321,
      UseMedicine: true,
      MedicineCount: 2,
    })
    expect(panel.saved[0][0].LegacyActivityFirst).toBeUndefined()
    expect(panel.saved[0].slice(1).every(plan => plan.Skip)).toBe(true)
  })

  it('uses the expired template for editing without saving merely on open', async () => {
    const panel = await renderEditor([legacy], [])
    expect(panel.saved).toEqual([])
    panel.toggles[3](true)
    expect(panel.saved).toHaveLength(1)
    expect(panel.saved[0].some(plan => plan.LegacyActivityFirst)).toBe(false)
    expect(panel.saved[0].filter(plan => !plan.Skip).map(plan => plan.StageType)).toEqual([
      'material',
      'orundum',
    ])
  })

  it('keeps the all-stage preset editable without creating a legacy selection', async () => {
    const panel = await renderEditor([{ StageType: 'all', DropCount: 999, OrundumDropCount: 9999 }])
    expect(panel.checked).toEqual([true, true, true, true])
    expect(panel.saved).toEqual([])
    panel.toggles[0](false)
    expect(panel.saved[0]).toEqual([
      { StageType: 'all', DropCount: 999, OrundumDropCount: 9999 },
      { StageType: 'material', StageIndex: 1, DropCount: 999, Skip: true },
    ])
  })

  it.each([false, true])(
    'takes over old material fallback with activity-first=%s',
    async activityFirst => {
      const old: EventDepotMaintainPlan = {
        StageType: 'material',
        StageIndex: 3,
        DropCount: 123,
        LegacyIndex: true,
        UseMedicine: true,
        MedicineCount: 2,
      }
      const panel = await renderEditor(activityFirst ? [old, legacy] : [old], [
        stages[0],
        stages[3],
      ])
      expect(panel.saved).toEqual([])
      expect(panel.checked).toEqual([true, false])
      expect(panel.values).toEqual([123, 9999])
      panel.toggles[0](false)
      expect(panel.saved).toHaveLength(1)
      expect(panel.saved[0]).toHaveLength(2)
      expect(
        panel.saved[0].every(plan => plan.Skip && !plan.LegacyIndex && !plan.LegacyActivityFirst)
      ).toBe(true)
      expect(panel.saved[0][0]).toMatchObject({
        StageType: 'material',
        StageIndex: 1,
        DropCount: 123,
        UseMedicine: true,
        MedicineCount: 2,
      })
    }
  )

  it('keeps the highest custom target when several old indices fall back to one stage', async () => {
    const rows: EventDepotMaintainPlan[] = [
      { StageType: 'material', StageIndex: 2, DropCount: 250, LegacyIndex: true },
      { StageType: 'material', StageIndex: 3, DropCount: 123, LegacyIndex: true },
      legacy,
    ]
    const panel = await renderEditor(rows, [stages[0], stages[3]])
    expect(panel.values[0]).toBe(250)
    panel.toggles[1](true)
    expect(panel.saved[0]).toHaveLength(2)
    expect(panel.saved[0][0].DropCount).toBe(250)
    expect(panel.saved[0].some(plan => plan.LegacyIndex || plan.LegacyActivityFirst)).toBe(false)
  })

  it('shows an old explicit cancellation ahead of other legacy fallback targets', async () => {
    const panel = await renderEditor(
      [
        { StageType: 'material', StageIndex: 1, DropCount: 123, LegacyIndex: true, Skip: true },
        { StageType: 'material', StageIndex: 3, DropCount: 250, LegacyIndex: true },
        legacy,
      ],
      [stages[0], stages[3]]
    )
    expect(panel.checked).toEqual([false, false])
    panel.toggles[1](true)
    expect(panel.saved[0][0]).toMatchObject({ DropCount: 123, Skip: true })
  })

  it('does not project an out-of-range cancellation onto the first current stage', async () => {
    const panel = await renderEditor(
      [
        { StageType: 'material', StageIndex: 99, DropCount: 123, LegacyIndex: true, Skip: true },
        legacy,
      ],
      [stages[0], stages[3]]
    )
    expect(panel.checked).toEqual([true, false])
  })
})
