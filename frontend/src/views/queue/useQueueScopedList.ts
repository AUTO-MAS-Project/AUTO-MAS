import { computed, onScopeDispose, ref, type Ref } from 'vue'

/** 锁定超过这么久才显示禁用样式：快速切换不闪灰 */
export const QUEUE_LIST_DIM_DELAY = 300

let pageInstanceSeq = 0
/**
 * 每个调度队列页面实例一个编号，拼进回读的 query key。离开页面再回来时，新实例的回读
 * 不会并进旧实例还在途的请求（旧实例已卸载，那次结果不会写进新实例）。
 */
export const nextQueuePageInstance = () => ++pageInstanceSeq

/**
 * 按队列切换的列表：切换时不先清空，避免先闪一下空状态。
 *
 * - 切到某个队列：有它的缓存就先显示缓存，没有就保留上一个队列的内容；两种情况都锁住，
 *   直到这个队列的回读返回（`commit` / `fail`）才换成新数据并解锁。缓存只做占位，不可编辑。
 * - `ownerQueueId` 是当前显示内容所属的队列，写请求一律发往它而不是当前选中的队列。
 * - `locked` 立即生效；`dimmed` 在锁定超过 `QUEUE_LIST_DIM_DELAY` 后才为真，只管禁用样式。
 */
export function useQueueScopedList<T extends { id: string }>(activeQueueId: Ref<string>) {
  const items = ref([]) as Ref<T[]>
  const ownerQueueId = ref('')
  const confirmed = ref(false)
  const locked = computed(() => !confirmed.value)
  const dimmed = ref(false)
  const cache = new Map<string, T[]>()
  const clone = (list: readonly T[]): T[] => JSON.parse(JSON.stringify(list))

  let dimTimer: ReturnType<typeof setTimeout> | undefined
  const stopDimTimer = () => {
    if (dimTimer !== undefined) clearTimeout(dimTimer)
    dimTimer = undefined
  }
  onScopeDispose(stopDimTimer)

  function lock(): void {
    confirmed.value = false
    if (dimmed.value || dimTimer !== undefined) return
    dimTimer = setTimeout(() => {
      dimTimer = undefined
      dimmed.value = true
    }, QUEUE_LIST_DIM_DELAY)
  }

  function unlock(): void {
    stopDimTimer()
    dimmed.value = false
    confirmed.value = true
  }

  /** 切换到某个队列（调用方已更新 activeQueueId）。 */
  function select(queueId: string): void {
    const cached = cache.get(queueId)
    if (cached) {
      items.value = clone(cached)
      ownerQueueId.value = queueId
    }
    lock()
  }

  /** 读到某个队列的列表：总是写缓存；它仍是当前队列时才替换显示并解锁。 */
  function commit(queueId: string, list: readonly T[]): void {
    cache.set(queueId, clone(list))
    if (queueId !== activeQueueId.value) return
    items.value = clone(list)
    ownerQueueId.value = queueId
    unlock()
  }

  /** 读取失败：还显示着别的队列内容就清空，显示的是本队列占位内容就保留；都解锁。 */
  function fail(queueId: string): void {
    if (!queueId || queueId !== activeQueueId.value) return
    if (ownerQueueId.value !== queueId) {
      items.value = []
      ownerQueueId.value = queueId
    }
    unlock()
  }

  /** 就地保存成功后同步该队列的缓存和（仍属于它的）当前显示。 */
  function patch(queueId: string, id: string, apply: (item: T) => void): void {
    const cached = cache.get(queueId)?.find(entry => entry.id === id)
    if (cached) apply(cached)
    if (ownerQueueId.value !== queueId) return
    const shown = items.value.find(entry => entry.id === id)
    if (shown) apply(shown)
  }

  function forget(queueId: string): void {
    cache.delete(queueId)
  }

  return { items, ownerQueueId, locked, dimmed, select, commit, fail, patch, forget }
}
