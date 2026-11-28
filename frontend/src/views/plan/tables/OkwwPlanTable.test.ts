// @vitest-environment vue-client
import type { OkwwPlanConfig, OkwwPlanKey } from '@/api'
import { expect, it, vi } from 'vite-plus/test'
import { defineComponent, h, nextTick, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { fire, testView } from '../../../../tests/vueRenderer'
import OkwwPlanTable from './OkwwPlanTable.vue'

vi.mock('@/router', () => ({ navigateTo: vi.fn() }))

it('只提交合法序号，保存后显示远端值，失败时可离开并丢弃草稿', async () => {
  const config = (index: number): OkwwPlanConfig => ({
    ALL: { Key: { WhichToFarm: 'Tacet Suppression', WhichTacetSuppressionToFarm: index } },
  })
  const tableData = ref(config(2))
  const save = vi.fn(async (_path: string, fields: unknown) => {
    tableData.value = { ALL: { Key: fields as OkwwPlanKey } }
    return true
  })
  const table = ref<InstanceType<typeof OkwwPlanTable>>()
  const view = testView(() =>
    h(OkwwPlanTable, {
      ref: table,
      planId: 'plan',
      currentMode: 'ALL',
      tableData: tableData.value,
      handlePlanChange: save,
    })
  )
  view.app.use(createI18n({ legacy: false, locale: 'zh-CN', missingWarn: false }))
  view.stub({
    'a-alert': 'alert',
    'a-button': 'button',
    'a-input-number': 'stage-index',
    'a-popover': 'popover',
    'a-select': 'select',
  })
  view.app.component(
    'ATable',
    defineComponent({
      props: ['columns', 'dataSource'],
      setup:
        (props, { slots }) =>
        () =>
          h(
            'table',
            props.columns.map((column: { key: string }) =>
              slots.bodyCell?.({ column, record: props.dataSource[0] })
            )
          ),
    })
  )
  view.mount()
  const stage = () => view.find('stage-index')!
  try {
    for (const invalid of [0, 1.5, 100]) await fire(stage(), 'onChange', invalid)
    expect(save).not.toHaveBeenCalled()

    await fire(stage(), 'onChange', 99)
    expect(save).toHaveBeenCalledWith(
      'ALL.Key',
      expect.objectContaining({ WhichTacetSuppressionToFarm: 99 })
    )
    await vi.waitFor(() => expect(stage().props.disabled).toBe(false))
    tableData.value = config(3)
    await nextTick()
    expect(stage().props.value).toBe(3)

    save.mockResolvedValueOnce(false)
    await fire(stage(), 'onChange', 4)
    await vi.waitFor(() => expect(view.find('alert')).toBeDefined())
    expect(stage().props.value).toBe(4)
    expect(table.value?.beforeLeave()).toBe(true)
    await nextTick()
    expect(stage().props.value).toBe(3)
    expect(view.find('alert')).toBeUndefined()
  } finally {
    view.app.unmount()
  }
})
