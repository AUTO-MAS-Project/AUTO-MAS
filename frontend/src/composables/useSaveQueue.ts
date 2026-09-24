import { ref } from 'vue'

interface QueuedSave {
  key: string | undefined
  run: () => Promise<unknown>
  settlers: Array<{
    resolve: (value: unknown) => void
    reject: (reason: unknown) => void
  }>
}

/**
 * 编辑页即时保存串行队列。
 *
 * 以「按序执行的队列」取代布尔 isSaving 互斥：布尔守卫会在「上一次保存尚未返回」时
 * 直接丢弃紧随其后的改动，造成前后端状态失步；队列则逐条按序写回，不再丢保存。
 *
 * - `enqueue(run)`：把一次保存排到队尾，返回该次保存自身的结果；
 * - `enqueue(run, key)`：同一 key 的连续改动在尚未开始执行时只保留最后一次，
 *   早先排队的调用方与最后一次共享同一结果；
 * - 任一保存抛错只让它自己的 promise 拒绝，不阻塞后面的保存；
 * - `isSaving` 在队列非空期间为 true，供模板里 `:loading` / `:disabled` 复用。
 */
export const useSaveQueue = () => {
  const isSaving = ref(false)
  const queue: QueuedSave[] = []
  let draining = false

  const drain = async () => {
    if (draining) return
    draining = true
    isSaving.value = true
    try {
      while (queue.length > 0) {
        const entry = queue.shift() as QueuedSave
        try {
          const result = await entry.run()
          entry.settlers.forEach(settler => settler.resolve(result))
        } catch (error) {
          entry.settlers.forEach(settler => settler.reject(error))
        }
      }
    } finally {
      draining = false
      isSaving.value = false
    }
  }

  const enqueue = <T>(run: () => Promise<T>, key?: string): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      const settler = { resolve: resolve as (value: unknown) => void, reject }
      const pending = key === undefined ? undefined : queue.find(entry => entry.key === key)
      if (pending) {
        pending.run = run
        pending.settlers.push(settler)
      } else {
        queue.push({ key, run, settlers: [settler] })
      }
      void drain()
    })

  return { isSaving, enqueue }
}
