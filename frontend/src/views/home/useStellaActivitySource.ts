import { onScopeDispose, ref } from 'vue'
import { GetService } from '@/api'
import { createEmptyStellaActivityOverview } from '@/types/home'
import type {
  StellaActivityItem,
  StellaActivityOverview,
  StellaOfficialBanner,
} from '@/types/home'

const logger = window.electronAPI.getLogger('活动数据')

/** 与其它活动源一致的失败重试节奏 */
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8

/**
 * 星塔旅人活动数据的后端中转数据源。
 *
 * StellaBase 不放开跨域（实测从前端的源直连报 `Failed to fetch`），所以取数走
 * 后端 `POST /api/info/stella/activity`。后端只转发站点原始响应，挑选与格式化
 * 仍在这里完成——与碧蓝档案那条链路同一形状。
 *
 * 站点已经把活动按状态分好组（current / upcoming / ended），卡片只关心
 * `current`，因此这里不再做时间窗筛选。
 */
export const useStellaActivitySource = () => {
  const overview = ref<StellaActivityOverview>(createEmptyStellaActivityOverview())
  const loading = ref(false)
  const hasData = ref(false)
  let retryTimer: number | null = null
  let retryCount = 0
  let disposed = false
  let active = false
  let started = false
  let retryPending = false

  const load = async () => {
    if (disposed) return
    try {
      const response = await GetService.getStellaActivityApiInfoStellaActivityPost()
      const payload = (response?.data ?? {}) as Partial<StellaActivityOverview>
      overview.value = {
        current: (payload.current ?? []) as StellaActivityItem[],
        upcoming: (payload.upcoming ?? []) as StellaActivityItem[],
        ended: (payload.ended ?? []) as StellaActivityItem[],
        official: (payload.official ?? []) as StellaOfficialBanner[],
        // 请求成功就算取到排期：站点返回空组只说明眼下没有活动，不是「拿不到数据」
        Available: true,
      }
      hasData.value = true
      retryCount = 0
    } catch (requestError) {
      if (disposed) return
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.warn('获取星塔旅人活动数据失败: ' + errorMessage)

      if (hasData.value) {
        // 保留上一次的内容，交给卡片按 stale 处理
      } else {
        overview.value = createEmptyStellaActivityOverview()
      }

      if (retryCount < MAX_RETRIES) {
        retryCount += 1
        if (active) {
          scheduleRetry()
        } else {
          // 模块隐藏期间不重试，重新可见时补一次
          retryPending = true
        }
      }
    } finally {
      if (!disposed) {
        loading.value = false
      }
    }
  }

  const scheduleRetry = () => {
    retryTimer = window.setTimeout(() => {
      retryTimer = null
      void load()
    }, RETRY_DELAY_MS)
  }

  const start = () => {
    if (disposed) return
    active = true
    if (!started) {
      started = true
      loading.value = !hasData.value
      void load()
    } else if (retryPending) {
      retryPending = false
      void load()
    }
  }

  const stop = () => {
    active = false
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
      retryPending = true
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  })

  return {
    overview,
    loading,
    start,
    stop,
    refresh: () => {
      retryCount = 0
      void load()
    },
  }
}
