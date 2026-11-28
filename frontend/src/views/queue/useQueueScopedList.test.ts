import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { effectScope, ref } from 'vue'
import {
  QUEUE_LIST_DIM_DELAY,
  nextQueuePageInstance,
  useQueueScopedList,
} from './useQueueScopedList'

type Row = { id: string; v: string }
const rows = (...vs: string[]): Row[] => vs.map((v, i) => ({ id: `r${i}`, v }))

function setup() {
  const active = ref('')
  const scope = effectScope()
  const list = scope.run(() => useQueueScopedList<Row>(active))!
  // 与页面的 selectQueue 一致：先改 activeQueueId，再通知列表
  const select = (queueId: string) => {
    active.value = queueId
    list.select(queueId)
  }
  return { list, select, scope }
}

/** 先读回 A 与 B，停在 A 上 */
function withAandB() {
  const ctx = setup()
  ctx.select('A')
  ctx.list.commit('A', rows('a1'))
  ctx.select('B')
  ctx.list.commit('B', rows('b1'))
  ctx.select('A')
  ctx.list.commit('A', rows('a1'))
  return ctx
}

describe('useQueueScopedList', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('首屏：没有数据时锁住、列表为空，读回后显示并解锁', () => {
    const { list, select } = setup()
    expect(list.locked.value).toBe(true)
    select('A')
    expect(list.locked.value).toBe(true)
    expect(list.items.value).toEqual([])
    expect(list.ownerQueueId.value).toBe('')

    list.commit('A', rows('a1'))
    expect(list.locked.value).toBe(false)
    expect(list.items.value).toEqual(rows('a1'))
    expect(list.ownerQueueId.value).toBe('A')
  })

  it('切到没有缓存的队列：保留上一个队列的内容并锁住，写入目标仍是上一个队列', () => {
    const { list, select } = setup()
    select('A')
    list.commit('A', rows('a1'))
    select('B')
    expect(list.items.value).toEqual(rows('a1'))
    expect(list.ownerQueueId.value).toBe('A')
    expect(list.locked.value).toBe(true)

    list.commit('B', rows('b1'))
    expect(list.items.value).toEqual(rows('b1'))
    expect(list.ownerQueueId.value).toBe('B')
    expect(list.locked.value).toBe(false)
  })

  it('切到有缓存的队列：先显示它的缓存，但仍锁住直到这次回读返回', () => {
    const { list, select } = withAandB()
    select('B')
    expect(list.items.value).toEqual(rows('b1'))
    expect(list.ownerQueueId.value).toBe('B')
    expect(list.locked.value).toBe(true)

    list.commit('B', rows('b2'))
    expect(list.items.value).toEqual(rows('b2'))
    expect(list.locked.value).toBe(false)
  })

  it('迟到的旧队列结果只进它自己的缓存，不替换当前显示也不解锁', () => {
    const { list, select } = withAandB()
    select('B')
    list.commit('A', rows('a-late'))
    expect(list.items.value).toEqual(rows('b1'))
    expect(list.ownerQueueId.value).toBe('B')
    expect(list.locked.value).toBe(true)

    list.commit('B', rows('b1'))
    select('A')
    expect(list.items.value).toEqual(rows('a-late'))
  })

  it('读失败：还显示着别的队列内容时清空，按新队列显示空表并解锁', () => {
    const { list, select } = setup()
    select('A')
    list.commit('A', rows('a1'))
    select('B')
    list.fail('B')
    expect(list.items.value).toEqual([])
    expect(list.ownerQueueId.value).toBe('B')
    expect(list.locked.value).toBe(false)
  })

  it('读失败：已显示本队列占位内容时保留并解锁', () => {
    const { list, select } = withAandB()
    select('B')
    list.fail('B')
    expect(list.items.value).toEqual(rows('b1'))
    expect(list.ownerQueueId.value).toBe('B')
    expect(list.locked.value).toBe(false)
  })

  it('别的队列读失败不影响当前显示和锁定', () => {
    const { list, select } = withAandB()
    select('B')
    list.fail('A')
    expect(list.items.value).toEqual(rows('b1'))
    expect(list.locked.value).toBe(true)
  })

  it('真正没有任务的队列：读回空列表后解锁（显示空状态而不是加载态）', () => {
    const { list, select } = setup()
    select('A')
    list.commit('A', rows('a1'))
    select('E')
    list.commit('E', [])
    expect(list.items.value).toEqual([])
    expect(list.ownerQueueId.value).toBe('E')
    expect(list.locked.value).toBe(false)
  })

  it('就地保存成功：同步进缓存和当前显示', () => {
    const { list, select } = withAandB()
    list.patch('A', 'r0', item => (item.v = 'a1-saved'))
    expect(list.items.value).toEqual(rows('a1-saved'))

    select('B')
    list.commit('B', rows('b1'))
    select('A')
    expect(list.items.value).toEqual(rows('a1-saved'))
  })

  it('就地保存结果属于已切走的队列：只改它的缓存，不动当前显示', () => {
    const { list, select } = withAandB()
    select('B')
    list.commit('B', rows('b1'))
    list.patch('A', 'r0', item => (item.v = 'a1-saved'))
    expect(list.items.value).toEqual(rows('b1'))
    select('A')
    expect(list.items.value).toEqual(rows('a1-saved'))
  })

  it('删掉的队列不再有缓存', () => {
    const { list, select } = withAandB()
    list.forget('B')
    select('B')
    expect(list.items.value).toEqual(rows('a1'))
    expect(list.ownerQueueId.value).toBe('A')
  })

  it('禁用样式：锁定满 300ms 才出现，解锁立即消失，快速切换不出现', () => {
    const { list, select } = withAandB()
    vi.advanceTimersByTime(QUEUE_LIST_DIM_DELAY * 2)
    expect(list.dimmed.value).toBe(false)

    // 300ms 内回读返回：全程不置灰，之后也不会被残留的定时器置灰
    select('B')
    vi.advanceTimersByTime(QUEUE_LIST_DIM_DELAY - 1)
    expect(list.dimmed.value).toBe(false)
    list.commit('B', rows('b1'))
    vi.advanceTimersByTime(QUEUE_LIST_DIM_DELAY * 2)
    expect(list.dimmed.value).toBe(false)
    expect(list.locked.value).toBe(false)

    // 超过 300ms：置灰；解锁立即恢复
    select('A')
    vi.advanceTimersByTime(QUEUE_LIST_DIM_DELAY - 1)
    expect(list.dimmed.value).toBe(false)
    vi.advanceTimersByTime(1)
    expect(list.dimmed.value).toBe(true)
    list.fail('A')
    expect(list.dimmed.value).toBe(false)
  })

  it('禁用样式：连续切换后在 300ms 内解锁，之后不置灰、不残留定时器', () => {
    const { list, select } = withAandB()
    select('B')
    vi.advanceTimersByTime(100)
    select('C')
    vi.advanceTimersByTime(50)
    list.commit('C', rows('c1'))
    vi.advanceTimersByTime(QUEUE_LIST_DIM_DELAY * 2)
    expect(list.locked.value).toBe(false)
    expect(list.dimmed.value).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('页面卸载（scope 销毁）时清掉置灰定时器', () => {
    const { select, scope } = withAandB()
    select('B')
    expect(vi.getTimerCount()).toBe(1)
    scope.stop()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('页面实例编号每次都不同', () => {
    expect(nextQueuePageInstance()).not.toBe(nextQueuePageInstance())
  })
})
