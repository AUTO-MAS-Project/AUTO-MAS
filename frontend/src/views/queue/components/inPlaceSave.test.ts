// @vitest-environment vue-client
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { defineComponent, h, nextTick, ref, type Component } from 'vue'
import { Service } from '@/api'
import { deferred, fire, testView } from '../../../../tests/vueRenderer'
import { useQueueScopedList } from '../useQueueScopedList'
import QueueItemManager from './QueueItemManager.vue'
import TimeSetManager from './TimeSetManager.vue'

const api = vi.hoisted(() => ({ updateSchedule: vi.fn(), updateTimeSet: vi.fn() }))
vi.mock('@/composables/useQueueApi', () => ({ queueApi: { updateSchedule: api.updateSchedule } }))
vi.mock('@/composables/useTimeSetApi', () => ({
  Service: { updateTimeSetApiQueueTimeUpdatePost: api.updateTimeSet },
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))
vi.mock('@ant-design/icons-vue', () => ({ PlusOutlined: { render: () => null } }))
vi.mock('@/components/ui', () => ({
  SectionCard: defineComponent({
    inheritAttrs: false,
    setup:
      (_, { slots }) =>
      () =>
        h('section', slots.default?.()),
  }),
}))
vi.mock('@/components/DragHandle.vue', () => ({
  default: defineComponent({ inheritAttrs: false, setup: () => () => h('handle') }),
}))
vi.mock('./QueueDeleteButton.vue', () => ({
  default: defineComponent({ inheritAttrs: false, setup: () => () => h('delete') }),
}))
vi.mock('./DraggableTableShell.vue', () => ({
  default: defineComponent({
    inheritAttrs: false,
    props: ['modelValue'],
    setup:
      (props, { slots }) =>
      () =>
        h(
          'rows',
          props.modelValue.map((element: unknown, index: number) => slots.row?.({ element, index }))
        ),
  }),
}))
// 定时行：只留「启用」开关，节点上带出当前显示的值
vi.mock('./TimeSetRow.vue', () => ({
  default: defineComponent({
    inheritAttrs: false,
    props: ['record'],
    emits: ['enabled'],
    setup:
      (props, { emit }) =>
      () =>
        h('time-row', {
          enabled: props.record.enabled,
          onToggle: (value: boolean) => emit('enabled', value),
        }),
  }),
}))
// 队列项的执行星期：节点上带出当前显示的值
vi.mock('./QueueWeekdaysSelect.vue', () => ({
  default: defineComponent({
    inheritAttrs: false,
    props: ['modelValue'],
    emits: ['update:modelValue', 'change'],
    setup:
      (props, { emit }) =>
      () =>
        h('days', {
          value: props.modelValue.join(','),
          onPick: (value: string[]) => {
            emit('update:modelValue', value)
            emit('change', value)
          },
        }),
  }),
}))

const ok = { code: 200 }
const flush = async () => {
  for (let i = 0; i < 8; i++) await nextTick()
}

/** 父层与页面一致：列表来自 useQueueScopedList，子表 saved 后用 patch 回写 */
function mountList<T extends { id: string }>(
  component: Component,
  listProp: string,
  rows: T[],
  apply: (item: T, change: Record<string, unknown>) => void
) {
  const active = ref('q')
  let list!: ReturnType<typeof useQueueScopedList<T>>
  const view = testView(
    defineComponent({
      setup() {
        list = useQueueScopedList<T>(active)
        list.commit('q', rows)
        return () =>
          h(component, {
            queueId: 'q',
            [listProp]: list.items.value,
            onSaved: (queueId: string, id: string, change: Record<string, unknown>) =>
              list.patch(queueId, id, item => apply(item, JSON.parse(JSON.stringify(change)))),
          })
      },
    })
  )
  view.stub({ AButton: 'button', ASelect: 'select', ASpace: 'span' })
  view.mount()
  const shown = (tag: string, key: string) =>
    view
      .all()
      .filter(el => el.tag === tag)
      .map(el => el.props[key])
  const node = (tag: string, index: number) => view.all().filter(el => el.tag === tag)[index]
  /** 切到别的队列再切回来：这时显示的是切队列用的缓存 */
  const cached = () => {
    active.value = 'other'
    list.select('other')
    active.value = 'q'
    list.select('q')
    return list.items.value
  }
  return { list: () => list, shown, node, cached }
}

beforeEach(() => {
  api.updateSchedule.mockReset()
  api.updateTimeSet.mockReset()
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
    },
  })
  vi.spyOn(Service, 'getScriptComboxApiInfoComboxScriptPost').mockResolvedValue({
    code: 200,
    data: [],
  } as never)
})

describe('定时列表连续就地保存', () => {
  type TimeSet = { id: string; time: string; enabled: boolean; days: string[] }
  const rows = (): TimeSet[] => [
    { id: 'a', time: '08:00', enabled: true, days: [] },
    { id: 'b', time: '09:00', enabled: true, days: [] },
  ]
  const mount = () =>
    mountList<TimeSet>(TimeSetManager, 'timeSets', rows(), (item, change) =>
      Object.assign(item, change)
    )

  it('较早的保存返回时，不把另一条仍在途的编辑顶回旧值', async () => {
    const first = deferred<typeof ok>()
    const second = deferred<typeof ok>()
    api.updateTimeSet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const view = mount()

    await fire(view.node('time-row', 0), 'onToggle', false)
    await fire(view.node('time-row', 1), 'onToggle', false)
    first.resolve(ok)
    await flush()
    expect(view.shown('time-row', 'enabled')).toEqual([false, false])

    second.resolve(ok)
    await flush()
    expect(view.shown('time-row', 'enabled')).toEqual([false, false])
    expect(view.list().items.value.map(item => item.enabled)).toEqual([false, false])
  })

  it('同一行连拨两次开关时依次保存，页面与缓存都停在最后一次操作', async () => {
    const first = deferred<typeof ok>()
    const second = deferred<typeof ok>()
    api.updateTimeSet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const view = mount()
    const sent = () => api.updateTimeSet.mock.calls.map(([input]) => input.data.Info.Enabled)

    await fire(view.node('time-row', 0), 'onToggle', false)
    await fire(view.node('time-row', 0), 'onToggle', true)
    await flush()
    // 前一次没返回，后一次不发出：旧回包不可能晚于新回包
    expect(sent()).toEqual([false])
    expect(view.shown('time-row', 'enabled')).toEqual([true, true])

    first.resolve(ok)
    await flush()
    expect(sent()).toEqual([false, true])
    expect(view.shown('time-row', 'enabled')).toEqual([true, true])

    second.resolve(ok)
    await flush()
    expect(view.shown('time-row', 'enabled')).toEqual([true, true])
    expect(view.cached().map(item => item.enabled)).toEqual([true, true])
  })

  it('后一条保存失败时只回滚它自己', async () => {
    const first = deferred<typeof ok>()
    const second = deferred<{ code: number; message: string }>()
    api.updateTimeSet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const view = mount()

    await fire(view.node('time-row', 0), 'onToggle', false)
    await fire(view.node('time-row', 1), 'onToggle', false)
    first.resolve(ok)
    second.resolve({ code: 500, message: 'boom' })
    await flush()
    expect(view.shown('time-row', 'enabled')).toEqual([false, true])
  })

  it('保存在途期间到达的整表刷新，在保存返回后补上', async () => {
    const pending = deferred<typeof ok>()
    api.updateTimeSet.mockReturnValueOnce(pending.promise)
    const view = mount()

    await fire(view.node('time-row', 0), 'onToggle', false)
    view.list().commit('q', [...rows(), { id: 'c', time: '10:00', enabled: true, days: [] }])
    await flush()
    pending.resolve(ok)
    await flush()
    expect(view.shown('time-row', 'enabled')).toEqual([false, true, true])
  })
})

describe('队列项连续就地保存', () => {
  type Item = { id: string; script: string; schedule: Record<string, unknown> }
  const mount = () =>
    mountList<Item>(
      QueueItemManager,
      'queueItems',
      [
        { id: 'a', script: 's1', schedule: { Days: [] } },
        { id: 'b', script: 's2', schedule: { Days: [] } },
      ],
      (item, change) => {
        item.schedule = { ...item.schedule, ...change }
      }
    )

  it('较早的保存返回时，不把另一条仍在途的编辑顶回旧值', async () => {
    const first = deferred<typeof ok>()
    const second = deferred<typeof ok>()
    api.updateSchedule.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const view = mount()

    await fire(view.node('days', 0), 'onPick', ['Monday'])
    await fire(view.node('days', 1), 'onPick', ['Friday'])
    first.resolve(ok)
    await flush()
    expect(view.shown('days', 'value')).toEqual(['Monday', 'Friday'])

    second.resolve(ok)
    await flush()
    expect(view.shown('days', 'value')).toEqual(['Monday', 'Friday'])
    expect(view.list().items.value.map(item => item.schedule.Days)).toEqual([
      ['Monday'],
      ['Friday'],
    ])
  })
})
