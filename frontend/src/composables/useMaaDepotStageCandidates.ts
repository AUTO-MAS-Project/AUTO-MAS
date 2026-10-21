import { onBeforeUnmount, ref } from 'vue'
import { Service, type CancelablePromise, type MaaDepotStageCandidatesBatchOut } from '@/api'

type StageOption = { label: string; value: string }
type PendingLoad = { promise: Promise<void>; resolve: () => void }

/** 页面内共用批量候选查询，后台预取只占用一个 HTTP 连接。 */
export function useMaaDepotStageCandidates(scriptId: string) {
  const logger = window.electronAPI.getLogger('MAA库存关卡候选')
  const candidates = ref<Record<string, StageOption[]>>({})
  const loading = ref<string[]>([])
  const pending = new Map<string, PendingLoad>()
  const queued = new Set<string>()
  let request: CancelablePromise<MaaDepotStageCandidatesBatchOut> | undefined
  let running = false
  let disposed = false

  const drain = async () => {
    if (running || disposed) return
    running = true
    try {
      while (queued.size > 0 && !disposed) {
        const itemIds = [...queued]
        queued.clear()
        try {
          request =
            Service.getMaaDepotStageCandidatesBatchApiScriptsMaaDepotStageCandidatesBatchPost({
              script: { scriptId },
              itemIds,
            })
          const response = await request
          if (disposed) return
          const data = response.data
          if (response.code !== 200 || !data) throw new Error(response.message || '候选查询失败')
          for (const itemId of itemIds) {
            candidates.value[itemId] = data[itemId]
              .filter(option => option.value)
              .map(option => ({ label: option.label, value: option.value as string }))
          }
        } catch (error) {
          // 失败不缓存为空结果；下次展开或编辑时仍可重试。
          if (!disposed) {
            logger.error(
              `加载库存保持关卡候选失败: ${error instanceof Error ? error.message : String(error)}`
            )
          }
        } finally {
          request = undefined
          for (const itemId of itemIds) {
            pending.get(itemId)?.resolve()
            pending.delete(itemId)
          }
          loading.value = loading.value.filter(itemId => !itemIds.includes(itemId))
        }
      }
    } finally {
      running = false
    }
  }

  const load = async (itemIds: string[]): Promise<void> => {
    if (disposed) return
    const waits: Promise<void>[] = []
    for (const itemId of new Set(itemIds.filter(Boolean))) {
      if (candidates.value[itemId] !== undefined) continue
      let entry = pending.get(itemId)
      if (!entry) {
        let resolve!: () => void
        const promise = new Promise<void>(settle => {
          resolve = settle
        })
        entry = { promise, resolve }
        pending.set(itemId, entry)
        queued.add(itemId)
        loading.value.push(itemId)
      }
      waits.push(entry.promise)
    }
    // 同一轮的预取、展开与编辑合并后再发请求；在途期间的新材料留给下一批。
    if (queued.size > 0) queueMicrotask(() => void drain())
    await Promise.all(waits)
  }

  onBeforeUnmount(() => {
    disposed = true
    request?.cancel()
    queued.clear()
    for (const entry of pending.values()) entry.resolve()
    pending.clear()
    loading.value = []
  })

  return { candidates, loading, load }
}
