import { computed, ref, type ComputedRef, type Ref } from 'vue'

interface QueuedSave {
  owner: symbol
  key: string | undefined
  run: () => Promise<unknown>
  pendingCount: Ref<number>
  settlers: Array<{
    resolve: (value: unknown) => void
    reject: (reason: unknown) => void
  }>
}

const globalQueue: QueuedSave[] = []
const idleWaiters: Array<() => void> = []
let draining = false

const findCoalesceTargetIndex = (owner: symbol, key: string): number => {
  // 从队尾往前找，遇到无 key 顺序屏障立刻停止，防止跨屏障合并破坏因果顺序。
  for (let i = globalQueue.length - 1; i >= 0; i -= 1) {
    const entry = globalQueue[i]!
    if (entry.key === undefined) return -1
    if (entry.owner === owner && entry.key === key) return i
  }
  return -1
}

const drain = async () => {
  if (draining) return
  draining = true
  try {
    while (globalQueue.length > 0) {
      const entry = globalQueue.shift()!
      try {
        const result = await entry.run()
        entry.settlers.forEach(settler => settler.resolve(result))
      } catch (error) {
        entry.settlers.forEach(settler => settler.reject(error))
      } finally {
        entry.pendingCount.value = Math.max(0, entry.pendingCount.value - 1)
      }
    }
  } finally {
    draining = false
    idleWaiters.splice(0).forEach(resolve => resolve())
  }
}

/**
 * 全前端共享的配置写入 FIFO 串行队列。
 *
 * 所有配置写操作（页面与嵌套子组件）共享同一条 FIFO 队列，按序落盘不丢修改、不并发乱序；
 * `isSaving` 按调用方独立统计，不会跨组件互相串 loading：
 * - `enqueue(run, key)`：同一调用方尚未开始的同 key 改动合并为最后一次（不跨无 key 屏障）；
 * - `enqueue(run)`：无 key 作为顺序屏障；
 * - 单次失败仅拒绝自身 Promise，不阻塞后续写入；
 * - `waitForIdle()`：等待当前队列全部落盘完成。
 */
export const useSaveQueue = (): {
  isSaving: ComputedRef<boolean>
  enqueue: <T>(run: () => Promise<T>, key?: string) => Promise<T>
  waitForIdle: () => Promise<void>
} => {
  const owner = Symbol('save-queue-owner')
  const pendingCount = ref(0)
  const isSaving = computed(() => pendingCount.value > 0)

  const enqueue = <T>(run: () => Promise<T>, key?: string): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      const settler = { resolve: resolve as (value: unknown) => void, reject }
      const targetIndex = key === undefined ? -1 : findCoalesceTargetIndex(owner, key)
      if (targetIndex !== -1) {
        const [pending] = globalQueue.splice(targetIndex, 1)
        pending!.run = run
        pending!.settlers.push(settler)
        globalQueue.push(pending!)
      } else {
        pendingCount.value += 1
        globalQueue.push({ owner, key, run, pendingCount, settlers: [settler] })
      }
      void drain()
    })

  const waitForIdle = (): Promise<void> =>
    !draining && globalQueue.length === 0
      ? Promise.resolve()
      : new Promise<void>(resolve => {
          idleWaiters.push(resolve)
        })

  return { isSaving, enqueue, waitForIdle }
}
