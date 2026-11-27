import { computed, onScopeDispose, type Ref } from 'vue'
import { usePluginRegistry } from './usePluginScriptTypes'
import { indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { GetService } from '@/api'
import { translate as t } from '@/i18n'
import { requestApi, apiErrorMessage } from '@/utils/apiResult'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { onConnected } from '@/services/websocket/connection'
import { WS_ID_PLUGIN, WS_PLUGIN_CAPABILITIES_UPDATED } from '@/services/websocket/types'

export async function fetchScriptCapabilities() {
  // 创建入口和静态插件页面共用实际后端能力，插件未启用时不开放专项入口。
  const result = await requestApi(
    () => GetService.getScriptTypesApiScriptsTypesGet(),
    t('core.scripts.create.capabilitiesLoadFailed')
  )
  return result.types ?? []
}

export function useScriptCapabilities(open: Ref<boolean>) {
  // 新建窗口读取当前后端能力；插件启停及连接恢复时重新查询，不使用静态列表兜底。
  const client = useQueryClient()
  const registry = usePluginRegistry(open)
  const key = ['scripts', 'capabilities']
  const query = useQuery({
    queryKey: key,
    enabled: open,
    refetchOnMount: 'always',
    staleTime: 0,
    retry: false,
    queryFn: fetchScriptCapabilities,
  })
  const refreshTypes = () => client.invalidateQueries({ queryKey: key }, { cancelRefetch: false })
  const refresh = async () => {
    // 失效缓存以覆盖窗口打开期间及断线期间发生的插件能力变化。
    await Promise.all([
      refreshTypes(),
      client.invalidateQueries({ queryKey: ['plugins', 'registry'] }, { cancelRefetch: false }),
    ])
  }
  const subscription = subscribe(
    { id: WS_ID_PLUGIN, type: WS_PLUGIN_CAPABILITIES_UPDATED },
    refresh
  )
  const stopConnected = onConnected(refreshTypes)
  onScopeDispose(() => {
    // 窗口组件释放时注销订阅，避免重复刷新与页面保活。
    unsubscribe(subscription)
    stopConnected()
  })
  return {
    types: computed(() => query.data.value ?? []),
    provided: computed(() => indexPluginScriptTypes(registry.data.value?.data)),
    loading: computed(() => query.isFetching.value || registry.isFetching.value),
    error: computed(() => {
      const error = query.error.value ?? registry.error.value
      return error ? apiErrorMessage(error, t('core.scripts.create.capabilitiesLoadFailed')) : null
    }),
    refresh,
  }
}
