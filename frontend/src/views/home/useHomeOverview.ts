import { onScopeDispose, ref } from 'vue'
import { Service } from '@/api/services/Service'
import {
  createEmptyEndfieldActivityOverview,
  createEmptySraActivityOverview,
  type ActivityItem,
  type EndfieldActivityOverview,
  type HomeOverviewResponse,
  type ProxyInfo,
  type ResourceItem,
  type SraActivityOverview,
} from '@/types/home'

const logger = window.electronAPI.getLogger('首页')

/** 冷缓存时第三方活动接口在后台刷新，首页不阻塞；此间隔后静默重试直到数据就绪 */
const PENDING_RETRY_DELAY_MS = 3000
/** 活动源刷新请求超时上限为 20 秒，8 次重试（约 24 秒）可覆盖该窗口 */
const MAX_PENDING_RETRIES = 8

type ActivityOverviewLike = Pick<SraActivityOverview, 'Available' | 'Message'>

const isProviderFetching = (overview: ActivityOverviewLike): boolean =>
  !overview.Available && overview.Message.includes('正在获取')

export const useHomeOverview = () => {
  const loading = ref(false)
  const error = ref('')
  const activityData = ref<ActivityItem[]>([])
  const resourceData = ref<ResourceItem[]>([])
  const proxyData = ref<Record<string, ProxyInfo>>({})
  const endfieldData = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  const starRailData = ref<SraActivityOverview>(createEmptySraActivityOverview())
  const genshinData = ref<SraActivityOverview>(createEmptySraActivityOverview())
  const zenlessZoneZeroData = ref<SraActivityOverview>(createEmptySraActivityOverview())
  const wutheringWavesData = ref<SraActivityOverview>(createEmptySraActivityOverview())
  const nevernessToEvernessData = ref<SraActivityOverview>(createEmptySraActivityOverview())
  const reverse1999Data = ref<SraActivityOverview>(createEmptySraActivityOverview())

  // 请求代次：仅最新一次请求可写回状态，避免旧响应覆盖新数据
  let fetchVersion = 0
  let pendingRetryTimer: ReturnType<typeof setTimeout> | null = null
  let pendingRetryCount = 0

  onScopeDispose(() => {
    if (pendingRetryTimer !== null) {
      clearTimeout(pendingRetryTimer)
      pendingRetryTimer = null
    }
  })

  const clearOverviewError = () => {
    error.value = ''
  }

  const fetchOverviewData = async (quiet = false) => {
    const version = ++fetchVersion

    if (!quiet) {
      loading.value = true
    }
    error.value = ''

    try {
      const response = await Service.getOverviewApiInfoGetOverviewPost()

      if (version !== fetchVersion) {
        return
      }

      if (response.code === 200) {
        const data = response.data as HomeOverviewResponse
        if (data.Stage) {
          activityData.value = data.Stage.Activity || []
          resourceData.value = data.Stage.Resource || []
        }
        if (data.Proxy) {
          proxyData.value = data.Proxy
        }
        starRailData.value = data.StarRail ?? createEmptySraActivityOverview()
        genshinData.value = data.Genshin ?? createEmptySraActivityOverview()
        zenlessZoneZeroData.value = data.ZenlessZoneZero ?? createEmptySraActivityOverview()
        wutheringWavesData.value = data.WutheringWaves ?? createEmptySraActivityOverview()
        nevernessToEvernessData.value = data.NevernessToEverness ?? createEmptySraActivityOverview()
        reverse1999Data.value = data.Reverse1999 ?? createEmptySraActivityOverview()
        endfieldData.value = data.Endfield ?? createEmptyEndfieldActivityOverview()

        // 仍有活动源处于"正在获取"：后台静默重试，数据就绪后自动展示
        const pendingProviders = [
          starRailData.value,
          genshinData.value,
          zenlessZoneZeroData.value,
          wutheringWavesData.value,
          nevernessToEvernessData.value,
          reverse1999Data.value,
          endfieldData.value,
        ]
        if (pendingProviders.some(isProviderFetching)) {
          if (pendingRetryTimer === null && pendingRetryCount < MAX_PENDING_RETRIES) {
            pendingRetryTimer = setTimeout(() => {
              pendingRetryTimer = null
              pendingRetryCount += 1
              void fetchOverviewData(true)
            }, PENDING_RETRY_DELAY_MS)
          }
        } else {
          pendingRetryCount = 0
        }
      } else {
        error.value = response.message || '获取数据失败'
        logger.warn(`获取首页概览失败: ${error.value}`)
      }
    } catch (requestError) {
      if (version !== fetchVersion) {
        return
      }
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.error(`获取首页概览失败: ${errorMessage}`)
      error.value = '网络请求失败，请检查连接'
    } finally {
      if (version === fetchVersion && !quiet) {
        loading.value = false
      }
    }
  }

  return {
    loading,
    error,
    activityData,
    resourceData,
    proxyData,
    endfieldData,
    starRailData,
    genshinData,
    zenlessZoneZeroData,
    wutheringWavesData,
    nevernessToEvernessData,
    reverse1999Data,
    clearOverviewError,
    fetchOverviewData,
  }
}
