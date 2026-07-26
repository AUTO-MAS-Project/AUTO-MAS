/**
 * 插件数据管理 composable。
 * 负责 WebSocket 通信、HTTP 回退、快照管理和插件操作编排。
 * 从 Plugin.vue 提取，保持向后兼容。
 */

import { ref } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import {
  PluginWebSocketCommandError,
  requestPluginActionWithFallback,
} from '@/views/pluginActionTransport'

import type {
  PluginInstance,
  PluginSchemaField,
  PluginRuntimeState,
  PluginActionInfo,
  PluginPackageInfo,
  PluginServiceInfo,
  PluginRouteInfo,
  PluginsGetResponse,
  WsCommandResponse,
  PluginSystemRuntimeMessage,
  PluginSystemSnapshotMessage,
  PluginSystemHmrMessage,
} from '../types'

const logger = window.electronAPI.getLogger('插件数据')

export function usePluginData() {
  const { subscribe, unsubscribe, sendRaw } = useWebSocket()

  // ---- 响应式状态 ----
  const loading = ref(false)
  const submitting = ref(false)
  const reloadingAll = ref(false)
  const togglingInstanceId = ref('')
  const pluginActionLoadingId = ref('')
  const uninstallingPlugin = ref('')

  const version = ref(1)
  const discoveredPlugins = ref<string[]>([])
  const schemaMap = ref<Record<string, Record<string, PluginSchemaField>>>({})
  const schemaErrors = ref<Record<string, string>>({})
  const pluginServices = ref<Record<string, PluginServiceInfo>>({})
  const pluginRoutes = ref<Record<string, PluginRouteInfo[]>>({})
  const pluginActions = ref<Record<string, PluginActionInfo[]>>({})
  const pluginPackages = ref<Record<string, PluginPackageInfo>>({})
  const instances = ref<PluginInstance[]>([])
  const runtimeStates = ref<Record<string, PluginRuntimeState>>({})

  // ---- WS 命令管理 ----
  let wsResponseSubscriptionId = ''
  let wsCommandCounter = 0
  const wsCommandPending = new Map<
    string,
    {
      resolve: (value: unknown) => void
      reject: (reason?: unknown) => void
      timer: ReturnType<typeof setTimeout>
    }
  >()

  const handleWsCommandResponse = (message: WebSocketBaseMessage) => {
    const payload = message.data as WsCommandResponse | undefined
    const requestId = payload?.request_id
    if (typeof requestId !== 'string') return

    const pending = wsCommandPending.get(requestId)
    if (!pending) return

    clearTimeout(pending.timer)
    wsCommandPending.delete(requestId)

    if (payload?.success) {
      pending.resolve(payload.data)
      return
    }

    pending.reject(
      new PluginWebSocketCommandError(
        payload?.message || `WebSocket command failed: ${requestId}`,
        true
      )
    )
  }

  const ensureWsResponseSubscription = () => {
    if (wsResponseSubscriptionId) return
    wsResponseSubscriptionId = subscribe(
      { type: 'response', id: 'Client' },
      handleWsCommandResponse
    )
  }

  const cleanupPendingWsCommands = () => {
    wsCommandPending.forEach(pending => {
      clearTimeout(pending.timer)
      pending.reject(
        new PluginWebSocketCommandError(
          'Plugin websocket command cancelled after dispatch; result unknown',
          true
        )
      )
    })
    wsCommandPending.clear()
  }

  const sendPluginCommand = async <T = unknown>(
    endpoint: string,
    params: Record<string, unknown> = {}
  ): Promise<T> => {
    try {
      ensureWsResponseSubscription()
    } catch (error) {
      throw new PluginWebSocketCommandError(
        `WebSocket response subscription failed before dispatch: ${String(error)}`,
        false
      )
    }

    return new Promise<T>((resolve, reject) => {
      const requestId = `plugin_${Date.now()}_${(wsCommandCounter += 1)}`
      const timer = setTimeout(() => {
        wsCommandPending.delete(requestId)
        reject(
          new PluginWebSocketCommandError(
            `WebSocket command timeout after dispatch; result unknown: ${endpoint}`,
            true
          )
        )
      }, 10000)

      wsCommandPending.set(requestId, {
        resolve: value => resolve(value as T),
        reject,
        timer,
      })

      const sent = sendRaw('command', { endpoint, params }, requestId)
      if (!sent) {
        clearTimeout(timer)
        wsCommandPending.delete(requestId)
        reject(
          new PluginWebSocketCommandError(
            `WebSocket unavailable before command dispatch: ${endpoint}`,
            false
          )
        )
      }
    })
  }

  const apiPost = async <T = unknown>(url: string, payload: Record<string, unknown> = {}) => {
    const requestUrl = `${OpenAPI.BASE}${url}`
    const { data } = await axios.post<T>(requestUrl, payload)
    return data
  }

  const requestPluginAction = async <T = unknown>(
    endpoint: string,
    url: string,
    payload: Record<string, unknown> = {}
  ): Promise<T> => {
    return requestPluginActionWithFallback<T>({
      endpoint,
      sendOverWebSocket: () => sendPluginCommand<T>(endpoint, payload),
      sendOverHttp: () => apiPost<T>(url, payload),
      onHttpFallback: error => {
        logger.warn(`WebSocket command fallback to HTTP: ${endpoint}, error=${String(error)}`)
      },
      onHttpReplaySuppressed: error => {
        logger.warn(
          `WebSocket command was dispatched; suppressing unsafe HTTP replay: ${endpoint}, error=${String(error)}`
        )
      },
    })
  }

  // ---- 快照管理 ----

  const applySnapshot = (
    data: PluginsGetResponse,
    syncLayoutFn: (instances: PluginInstance[]) => void,
    preferredInstanceId: string
  ): string => {
    const nextInstances = Array.isArray(data.instances) ? data.instances : []

    version.value = data.version
    discoveredPlugins.value = data.discovered_plugins || []
    schemaMap.value = data.schemas || {}
    schemaErrors.value = data.schema_errors || {}
    pluginServices.value = data.plugin_services || {}
    pluginRoutes.value = data.plugin_routes || {}
    pluginActions.value = data.plugin_actions || {}
    pluginPackages.value = data.plugin_packages || {}
    instances.value = nextInstances
    syncLayoutFn(nextInstances)
    runtimeStates.value = data.runtime_states || {}

    if (nextInstances.length === 0) return ''

    const targetId = nextInstances.some(item => item.id === preferredInstanceId)
      ? preferredInstanceId
      : nextInstances[0].id

    return targetId
  }

  const applyRuntimeStateUpdate = (record: PluginRuntimeState) => {
    if (!record?.instance_id) return
    runtimeStates.value = {
      ...runtimeStates.value,
      [record.instance_id]: record,
    }
  }

  // ---- 数据获取 ----

  const fetchDataByHttp = async (applySnapshotFn: (data: PluginsGetResponse) => string) => {
    const data = await apiPost<PluginsGetResponse>('/api/plugins/get', {})
    if (data.code !== 200 || data.status !== 'success') {
      throw new Error(data.message || '获取插件配置失败')
    }
    return applySnapshotFn(data)
  }

  const fetchData = async (applySnapshotFn: (data: PluginsGetResponse) => string) => {
    loading.value = true
    try {
      const data = await requestPluginAction<PluginsGetResponse>(
        'plugins.get',
        '/api/plugins/get',
        {}
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '获取插件配置失败')
      }
      return applySnapshotFn(data)
    } catch (error) {
      logger.warn(`Plugin fetch by websocket failed: ${String(error)}`)
      try {
        return await fetchDataByHttp(applySnapshotFn)
      } catch (httpError) {
        message.error(`获取失败: ${String(httpError)}`)
        logger.error(`获取插件配置失败: ${String(httpError)}`)
      }
    } finally {
      loading.value = false
    }
    return ''
  }

  // ---- 插件操作 ----

  const submitEdit = async (
    payload: Record<string, unknown>,
    sanitizeError?: (message: string) => string
  ) => {
    submitting.value = true
    try {
      const data = await requestPluginAction<{ code: number; status: string; message?: string }>(
        'plugins.update',
        '/api/plugins/update',
        payload
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '更新失败')
      }
      message.success('更新成功')
      return true
    } catch (error) {
      const rawError = String(error)
      const safeError = sanitizeError ? sanitizeError(rawError) : rawError
      logger.error(`更新插件实例失败: ${safeError}`)
      message.error(`更新失败: ${safeError}`)
      return false
    } finally {
      submitting.value = false
    }
  }

  const submitAdd = async (payload: { plugin: string; name?: string; enabled: boolean }) => {
    submitting.value = true
    try {
      const data = await requestPluginAction<{
        code: number
        status: string
        message?: string
        instance?: { id: string }
      }>('plugins.add', '/api/plugins/add', {
        plugin: payload.plugin,
        name: payload.name || undefined,
        enabled: payload.enabled,
        config: {},
      })
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '新增失败')
      }
      message.success('新增成功')
      return data.instance?.id || ''
    } catch (error) {
      message.error(`新增失败: ${String(error)}`)
      return ''
    } finally {
      submitting.value = false
    }
  }

  const deleteInstance = async (instanceId: string) => {
    try {
      const data = await requestPluginAction<{ code: number; status: string; message?: string }>(
        'plugins.delete',
        '/api/plugins/delete',
        { instanceId }
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '删除失败')
      }
      message.success('删除成功')
      return true
    } catch (error) {
      message.error(`删除失败: ${String(error)}`)
      return false
    }
  }

  const reloadAll = async () => {
    reloadingAll.value = true
    try {
      const data = await requestPluginAction<{ code: number; status: string; message?: string }>(
        'plugins.reload',
        '/api/plugins/reload',
        {}
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '重载失败')
      }
      message.success('重载全部成功')
    } catch (error) {
      message.error(`重载失败: ${String(error)}`)
    } finally {
      reloadingAll.value = false
    }
  }

  const reloadInstance = async (instanceId: string) => {
    try {
      const data = await requestPluginAction<{ code: number; status: string; message?: string }>(
        'plugins.reload_instance',
        '/api/plugins/reload_instance',
        { instanceId }
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '重载实例失败')
      }
      message.success(`实例重载成功: ${instanceId}`)
    } catch (error) {
      message.error(`实例重载失败: ${String(error)}`)
    }
  }

  const reloadPlugin = async (plugin: string) => {
    try {
      const data = await requestPluginAction<{ code: number; status: string; message?: string }>(
        'plugins.reload_plugin',
        '/api/plugins/reload_plugin',
        { plugin }
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '重载插件失败')
      }
      message.success(`插件重载成功: ${plugin}`)
    } catch (error) {
      message.error(`插件重载失败: ${String(error)}`)
    }
  }

  const uninstallPluginPackage = async (plugin: string, packageName: string) => {
    uninstallingPlugin.value = plugin
    try {
      const data = await requestPluginAction<{ code: number; status: string; message?: string }>(
        'plugins.uninstall_package',
        '/api/plugins/uninstall_package',
        { package: packageName }
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '卸载插件失败')
      }
      message.success(`插件包已卸载: ${packageName}`)
      return true
    } catch (error) {
      message.error(`卸载插件失败: ${String(error)}`)
      return false
    } finally {
      uninstallingPlugin.value = ''
    }
  }

  const toggleInstanceEnabled = async (instance: PluginInstance, enabled: boolean) => {
    if (instance.locked) {
      message.info('系统插件不可禁用')
      return false
    }
    togglingInstanceId.value = instance.id
    try {
      const data = await requestPluginAction<{ code: number; status: string; message?: string }>(
        'plugins.update',
        '/api/plugins/update',
        { instanceId: instance.id, enabled }
      )
      if (data.code !== 200 || data.status !== 'success') {
        throw new Error(data.message || '更新启用状态失败')
      }
      return true
    } catch (error) {
      message.error(`更新启用状态失败: ${String(error)}`)
      return false
    } finally {
      togglingInstanceId.value = ''
    }
  }

  // ---- 声明式插件动作 ----

  const requestDeclaredPluginAction = async <T = unknown>(action: PluginActionInfo) => {
    const method = (action.method || 'POST').toUpperCase()
    const path = action.path.startsWith('/') ? action.path : `/${action.path}`
    const requestUrl = `${OpenAPI.BASE}/plugin${path}`
    const payload = action.payload ?? {}
    const { data } = await axios.request<T>({
      method,
      url: requestUrl,
      params: method === 'GET' ? payload : undefined,
      data: method === 'GET' ? undefined : payload,
    })
    return data
  }

  const runDeclaredPluginAction = async (
    action: PluginActionInfo,
    sourceLabel = '插件动作',
    onSuccess?: () => void
  ) => {
    pluginActionLoadingId.value = action.id
    try {
      const data = await requestDeclaredPluginAction<{ code?: number; message?: string }>(action)
      if (data && typeof data === 'object' && 'code' in data && Number(data.code) !== 200) {
        throw new Error(String(data.message || '插件动作执行失败'))
      }
      message.success(`${action.label} 已执行`)
      if (action.refresh && onSuccess) {
        onSuccess()
      }
    } catch (error) {
      message.error(`${sourceLabel}失败: ${String(error)}`)
      logger.error(`${sourceLabel}失败: action=${action.id}, error=${String(error)}`)
    } finally {
      pluginActionLoadingId.value = ''
    }
  }

  // ---- WS 消息处理 ----

  const handlePluginSystemMessage = (
    wsMessage: WebSocketBaseMessage,
    applySnapshotFn: (data: PluginsGetResponse, preferredId: string) => string,
    currentSelectedId: string
  ): string | undefined => {
    const payload = wsMessage.data as
      | PluginSystemRuntimeMessage
      | PluginSystemSnapshotMessage
      | PluginSystemHmrMessage
      | undefined
    if (!payload || typeof payload !== 'object') return undefined

    if (payload.kind === 'snapshot') {
      return applySnapshotFn(payload, currentSelectedId)
    }

    if (payload.kind === 'runtime_state') {
      applyRuntimeStateUpdate(payload.record)
      return undefined
    }

    if (payload.kind === 'hmr') {
      logger.info(
        `Plugin HMR: plugin=${payload.plugin || '-'}, action=${payload.action}, status=${payload.status}`
      )
      if (payload.status === 'error') {
        message.warning(`插件 HMR 失败: ${payload.message || payload.plugin || 'unknown'}`)
      }
      return undefined
    }

    return undefined
  }

  const cleanup = () => {
    if (wsResponseSubscriptionId) {
      unsubscribe(wsResponseSubscriptionId)
      wsResponseSubscriptionId = ''
    }
    cleanupPendingWsCommands()
  }

  return {
    // 状态
    loading,
    submitting,
    reloadingAll,
    togglingInstanceId,
    pluginActionLoadingId,
    uninstallingPlugin,
    version,
    discoveredPlugins,
    schemaMap,
    schemaErrors,
    pluginServices,
    pluginRoutes,
    pluginActions,
    pluginPackages,
    instances,
    runtimeStates,
    // 数据操作
    applySnapshot,
    applyRuntimeStateUpdate,
    fetchData,
    // 插件操作
    submitEdit,
    submitAdd,
    deleteInstance,
    reloadAll,
    reloadInstance,
    reloadPlugin,
    uninstallPluginPackage,
    toggleInstanceEnabled,
    // 动作
    runDeclaredPluginAction,
    // WS
    subscribe,
    unsubscribe,
    handlePluginSystemMessage,
    cleanup,
  }
}
