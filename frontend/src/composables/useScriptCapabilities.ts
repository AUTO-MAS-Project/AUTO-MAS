import { computed, onScopeDispose, type Ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { GetService } from '@/api'
import { translate as t } from '@/i18n'
import { requestApi, apiErrorMessage } from '@/utils/apiResult'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { onConnected } from '@/services/websocket/connection'
import { WS_ID_PLUGIN, WS_PLUGIN_CAPABILITIES_UPDATED } from '@/services/websocket/types'

export function useScriptCapabilities(open: Ref<boolean>) {
  // 新建窗口读取当前后端能力；插件启停及连接恢复时重新查询，不使用静态列表兜底。
  const client = useQueryClient()
  const key = ['scripts', 'capabilities']
  const query = useQuery({
    queryKey: key,
    enabled: open,
    refetchOnMount: 'always',
    staleTime: 0,
    retry: false,
    queryFn: async () => {
      // 通过生成接口获取可创建类型，并沿用统一业务响应校验。
      const result = await requestApi(
        () => GetService.getScriptTypesApiScriptsTypesGet(),
        t('core.scripts.create.capabilitiesLoadFailed')
      )
      return result.types ?? []
    },
  })
  const refresh = () => {
    // 失效缓存以覆盖窗口打开期间及断线期间发生的插件能力变化。
    return client.invalidateQueries({ queryKey: key })
  }
  const subscription = subscribe(
    { id: WS_ID_PLUGIN, type: WS_PLUGIN_CAPABILITIES_UPDATED },
    refresh
  )
  const stopConnected = onConnected(refresh)
  onScopeDispose(() => {
    // 窗口组件释放时注销订阅，避免重复刷新与页面保活。
    unsubscribe(subscription)
    stopConnected()
  })
  return {
    types: computed(() => query.data.value ?? []),
    loading: query.isFetching,
    error: computed(() =>
      query.error.value
        ? apiErrorMessage(query.error.value, t('core.scripts.create.capabilitiesLoadFailed'))
        : null
    ),
    refresh,
  }
}
