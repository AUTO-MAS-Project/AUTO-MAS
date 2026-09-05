import { ref } from 'vue'
import { translate as t } from '@/i18n'
import { Service } from '@/api/services/Service'
import type {
  ActivityItem,
  HomeOverviewResponse,
  ProxyInfo,
  ResourceItem,
} from '@/types/home'

const logger = window.electronAPI.getLogger('首页')

/** 最近一次成功的首页概览快照：启动时先渲染上次数据，后台刷新完成后再覆盖 */
const OVERVIEW_CACHE_KEY = 'auto-mas.home.overview-cache'

export const useHomeOverview = () => {
  const loading = ref(false)
  const error = ref('')
  /** 是否已有可用数据（本地快照或后端返回）；有数据时刷新不再用骨架屏遮挡内容 */
  const hasSnapshot = ref(false)
  const activityData = ref<ActivityItem[]>([])
  const resourceData = ref<ResourceItem[]>([])
  const proxyData = ref<Record<string, ProxyInfo>>({})

  // 请求代次：仅最新一次请求可写回状态，避免旧响应覆盖新数据
  let fetchVersion = 0

  const clearOverviewError = () => {
    error.value = ''
  }

  const applyOverview = (data: HomeOverviewResponse) => {
    if (data.Stage) {
      activityData.value = data.Stage.Activity || []
      resourceData.value = data.Stage.Resource || []
    }
    if (data.Proxy) {
      proxyData.value = data.Proxy
    }
  }

  const saveOverviewCache = (data: HomeOverviewResponse) => {
    try {
      localStorage.setItem(OVERVIEW_CACHE_KEY, JSON.stringify(data))
    } catch {
      // 本地存储不可用时仅跳过快照缓存，不影响本次展示
    }
  }

  // 启动即用上次的快照填充各卡片，数据区不等后端返回值再渲染
  try {
    const cached = localStorage.getItem(OVERVIEW_CACHE_KEY)
    if (cached) {
      applyOverview(JSON.parse(cached) as HomeOverviewResponse)
      hasSnapshot.value = true
    }
  } catch {
    // 快照损坏时按无缓存处理
  }

  const fetchOverviewData = async (quiet = false) => {
    const version = ++fetchVersion

    if (!quiet && !hasSnapshot.value) {
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
        applyOverview(data)
        hasSnapshot.value = true
        saveOverviewCache(data)
      } else {
        error.value = response.message || t('home.overview.fetchFailed')
        logger.warn('获取首页概览失败: ' + error.value)
      }
    } catch (requestError) {
      if (version !== fetchVersion) {
        return
      }
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.error('获取首页概览失败: ' + errorMessage)
      error.value = t('home.overview.networkFailed')
    } finally {
      if (version === fetchVersion && !quiet) {
        loading.value = false
      }
    }
  }

  return {
    loading,
    error,
    hasSnapshot,
    activityData,
    resourceData,
    proxyData,
    clearOverviewError,
    fetchOverviewData,
  }
}
