import { ref } from 'vue'

import { useShareApi, type MyAppearanceItem } from '@/composables/useShareApi'
import { createCoverLoader, type CoverTask } from './coverLoader'

export const MY_APPEARANCE_COVER_CACHE_LIMIT = 60
export const MY_APPEARANCE_COVER_CONCURRENCY = 3

const UNAUTHORIZED = 401

/**
 * 当前账号在分享站上的外观（「我的主题」页、上传对话框和详情页共用一份）。
 * 封面取的是最新版本的，待审核、被驳回的版本也能看到。
 */
export function useMyAppearances(options: { onUnauthorized?: () => void } = {}) {
  const logger = window.electronAPI.getLogger('主题商店')
  const { listMyAppearances, getMyAppearanceCover, updateMyAppearanceDescription } = useShareApi()

  const items = ref<MyAppearanceItem[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<string | null>(null)
  let revision = 0
  let pending: Promise<void> | null = null

  const coverLoader = createCoverLoader({
    limit: MY_APPEARANCE_COVER_CACHE_LIMIT,
    concurrency: MY_APPEARANCE_COVER_CONCURRENCY,
  })
  const coverKey = (item: MyAppearanceItem): string => `${item.fileId}@${item.latestVersionNo}`

  const coverTask = (item: MyAppearanceItem): CoverTask => {
    const key = coverKey(item)
    return {
      key,
      run: async () => {
        const result = await getMyAppearanceCover(item.fileId)
        if (result.ok) return result.data
        if (result.code !== 404) logger.warn(`加载我的外观封面失败: ${key}，${result.message}`)
        return null
      },
    }
  }

  const coverFor = (item: MyAppearanceItem): string | undefined =>
    item.latestHasCover ? coverLoader.get(coverKey(item)) : undefined

  const ensureCover = (item: MyAppearanceItem): void => {
    if (item.latestHasCover) coverLoader.request(coverTask(item))
  }

  const run = async (): Promise<void> => {
    const current = ++revision
    loading.value = true
    error.value = null
    try {
      const result = await listMyAppearances()
      if (current !== revision) return
      if (!result.ok) {
        items.value = []
        loaded.value = false
        error.value = result.message
        logger.warn(`加载我的外观失败: ${result.code} ${result.message}`)
        if (result.code === UNAUTHORIZED) options.onUnauthorized?.()
        return
      }
      items.value = result.data
      loaded.value = true
      coverLoader.load(items.value.filter(item => item.latestHasCover).map(coverTask))
    } finally {
      if (current === revision) loading.value = false
    }
  }

  /** 重新拉一次；并发调用共用同一次请求。 */
  const load = (): Promise<void> => {
    pending ??= run().finally(() => {
      pending = null
    })
    return pending
  }

  /** 还没拉过（或上次失败）才拉。 */
  const ensureLoaded = async (): Promise<void> => {
    if (!loaded.value) await load()
  }

  const findById = (fileId: number | null): MyAppearanceItem | null =>
    fileId === null ? null : (items.value.find(item => item.fileId === fileId) ?? null)

  const findByFileKey = (fileKey: string): MyAppearanceItem | null =>
    items.value.find(item => item.fileKey === fileKey) ?? null

  /** 改简介，成功后就地替换列表里的条目；失败返回原因。 */
  const updateDescription = async (
    fileId: number,
    description: string
  ): Promise<{ ok: true } | { ok: false; message: string }> => {
    const result = await updateMyAppearanceDescription(fileId, description)
    if (!result.ok) {
      logger.warn(`修改外观简介失败: ${fileId}，${result.code} ${result.message}`)
      if (result.code === UNAUTHORIZED) options.onUnauthorized?.()
      return { ok: false, message: result.message }
    }
    items.value = items.value.map(item => (item.fileId === fileId ? result.data : item))
    return { ok: true }
  }

  const reset = (): void => {
    revision += 1
    pending = null
    items.value = []
    loading.value = false
    loaded.value = false
    error.value = null
    coverLoader.reset()
  }

  return {
    items,
    loading,
    loaded,
    error,
    coverFor,
    ensureCover,
    load,
    ensureLoaded,
    findById,
    findByFileKey,
    updateDescription,
    reset,
  }
}

export type MyAppearanceStore = ReturnType<typeof useMyAppearances>
