import { shallowRef } from 'vue'

/** 一张封面的加载任务：key 用于缓存与去重，run 取回 data URL，取不到时返回 null。 */
export interface CoverTask {
  key: string
  run: () => Promise<string | null>
}

/**
 * 封面加载器：渲染进程里有上限的封面缓存，加上全局并发上限的加载队列。
 *
 * - `load` 用新列表整体替换等待中的队列，旧列表里还没开始的封面不再加载；
 *   已经在途的请求照常结束，并发计数也一直算着它们，所以实际并发不会超过上限。
 * - `request` 把单张封面插到队首（详情页切版本时用），同样受并发上限约束。
 * - `reset` 清空缓存与队列，之后才返回的旧结果直接丢弃。
 */
export function createCoverLoader(options: { limit: number; concurrency: number }) {
  const covers = shallowRef<Record<string, string>>({})
  const loading = new Set<string>()
  let queue: CoverTask[] = []
  let active = 0
  let generation = 0

  const get = (key: string): string | undefined => covers.value[key]

  // 按写入先后淘汰最旧的；重新写入的 key 挪到最后。
  const store = (key: string, value: string): void => {
    const next = { ...covers.value }
    delete next[key]
    next[key] = value
    const keys = Object.keys(next)
    for (const stale of keys.slice(0, Math.max(0, keys.length - options.limit))) {
      delete next[stale]
    }
    covers.value = next
  }

  const settled = (task: CoverTask): boolean =>
    covers.value[task.key] !== undefined || loading.has(task.key)

  const start = (task: CoverTask): void => {
    const current = generation
    active += 1
    loading.add(task.key)
    void task
      .run()
      .catch(() => null)
      .then(value => {
        if (current !== generation) return
        loading.delete(task.key)
        if (value) store(task.key, value)
      })
      .finally(() => {
        active -= 1
        pump()
      })
  }

  const pump = (): void => {
    while (active < options.concurrency && queue.length > 0) {
      const task = queue.shift() as CoverTask
      if (!settled(task)) start(task)
    }
  }

  const load = (tasks: CoverTask[]): void => {
    queue = tasks.filter(task => !settled(task))
    pump()
  }

  const request = (task: CoverTask): void => {
    if (settled(task)) return
    queue = [task, ...queue.filter(item => item.key !== task.key)]
    pump()
  }

  const reset = (): void => {
    generation += 1
    queue = []
    loading.clear()
    covers.value = {}
  }

  return { covers, get, load, request, reset }
}

export type CoverLoader = ReturnType<typeof createCoverLoader>
