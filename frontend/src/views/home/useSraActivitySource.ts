import { onScopeDispose, ref } from 'vue'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'

const logger = window.electronAPI.getLogger('活动数据')

/** 与后端现有活动服务一致的请求超时与失败重试节奏 */
const FETCH_TIMEOUT_MS = 20_000
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8

/** SRA 公开接口直连返回的数据（缺后端 SWR 包装的三个元数据） */
interface SraSourceData {
  version: string
  versionName: string
  startTime: string
  endTime: string
  cover?: string
  activities: SraActivityItem[]
}

const SOURCE_BASE = 'https://starrailassistant.top/api/v1/activity'

const createEmptyOverview = (message: string): SraActivityOverview => ({
  Available: false,
  Stale: false,
  Message: message,
  version: '',
  versionName: '',
  startTime: '',
  endTime: '',
  activities: [],
})

const snapshotKey = (game: string) => 'auto-mas.home.sra-snapshot.' + game

/**
 * 单游戏活动数据的直连数据源（首页全前端化第一步）。
 *
 * 职责与后端 SraActivityService 对齐：直接请求 SRA 公开接口，
 * 带超时、失败退避重试、本地快照（stale-while-revalidate）与
 * 独立失败态——任一源异常只影响本卡片，不阻塞其它卡片。
 */
export const useSraActivitySource = (game: string, displayName: string) => {
  const overview = ref<SraActivityOverview>(createEmptyOverview(''))
  const loading = ref(false)
  const hasData = ref(false)
  let retryTimer: number | null = null
  let retryCount = 0
  let disposed = false

  // 启动先用上次快照填卡片，不等网络
  try {
    const raw = localStorage.getItem(snapshotKey(game))
    if (raw) {
      const cached = JSON.parse(raw) as SraSourceData
      overview.value = { Available: true, Stale: false, Message: '', ...cached }
      hasData.value = true
    }
  } catch {
    // 快照损坏按无缓存处理
  }
  if (!hasData.value) {
    loading.value = true
  }

  const load = async () => {
    if (disposed) return
    try {
      const controller = new AbortController()
      const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
      let response: Response
      try {
        response = await fetch(SOURCE_BASE + '/' + game + '.json', {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        })
      } finally {
        window.clearTimeout(timer)
      }
      if (!response.ok) {
        throw new Error('HTTP ' + response.status)
      }
      const data = (await response.json()) as SraSourceData
      overview.value = { Available: true, Stale: false, Message: '', ...data }
      hasData.value = true
      retryCount = 0
      try {
        localStorage.setItem(snapshotKey(game), JSON.stringify(data))
      } catch {
        // 本地存储不可用时仅跳过快照缓存
      }
    } catch (requestError) {
      if (disposed) return
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.warn('获取' + displayName + '活动数据失败: ' + errorMessage)
      if (hasData.value) {
        overview.value = {
          ...overview.value,
          Stale: true,
          Message: '正在使用上次成功获取的活动数据',
        }
      } else {
        overview.value = createEmptyOverview(displayName + '活动数据暂不可用')
      }
      if (retryCount < MAX_RETRIES) {
        retryCount += 1
        retryTimer = window.setTimeout(() => {
          retryTimer = null
          void load()
        }, RETRY_DELAY_MS)
      }
    } finally {
      if (!disposed) {
        loading.value = false
      }
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  })

  void load()

  return {
    overview,
    loading,
    refresh: () => {
      retryCount = 0
      void load()
    },
  }
}
