import { ref } from 'vue'
import { Service } from '@/api/services/Service'
import {
  createEmptyEndfieldActivityOverview,
  createEmptyStarRailActivityOverview,
  type ActivityItem,
  type EndfieldActivityOverview,
  type HomeOverviewResponse,
  type ProxyInfo,
  type ResourceItem,
  type StarRailActivityOverview,
} from '@/types/home'

const logger = window.electronAPI.getLogger('首页')

export const useHomeOverview = () => {
  const loading = ref(false)
  const error = ref('')
  const activityData = ref<ActivityItem[]>([])
  const resourceData = ref<ResourceItem[]>([])
  const proxyData = ref<Record<string, ProxyInfo>>({})
  const endfieldData = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  const starRailData = ref<StarRailActivityOverview>(createEmptyStarRailActivityOverview())

  const clearOverviewError = () => {
    error.value = ''
  }

  const fetchOverviewData = async () => {
    loading.value = true
    error.value = ''

    try {
      const response = await Service.getOverviewApiInfoGetOverviewPost()

      if (response.code === 200) {
        const data = response.data as HomeOverviewResponse
        if (data.Stage) {
          activityData.value = data.Stage.Activity || []
          resourceData.value = data.Stage.Resource || []
        }
        if (data.Proxy) {
          proxyData.value = data.Proxy
        }
        starRailData.value = data.StarRail ??
        createEmptyStarRailActivityOverview()
        endfieldData.value = data.Endfield ?? createEmptyEndfieldActivityOverview()
      } else {
        error.value = response.message || '获取数据失败'
        logger.warn(`获取首页概览失败: ${error.value}`)
      }
    } catch (requestError) {
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.error(`获取首页概览失败: ${errorMessage}`)
      error.value = '网络请求失败，请检查连接'
    } finally {
      loading.value = false
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
    clearOverviewError,
    fetchOverviewData,
  }
}
