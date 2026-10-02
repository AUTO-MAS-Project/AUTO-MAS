import { getCurrentScope, onScopeDispose } from 'vue'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import { WS_MAAFW_ENV_PREPARE_PROGRESS, type WSDataForType } from '@/services/websocket/types'

export type MaaFWEnvProgressData = WSDataForType<typeof WS_MAAFW_ENV_PREPARE_PROGRESS>
type MaaFWProgressListener = (data: MaaFWEnvProgressData) => void

/**
 * 运行环境准备与导入副本共用的进度订阅（同一个脚本、同一条通道）。
 *
 * 订阅在第一次 `ensureEnvSubscription()` 时才挂上；调用方要在发请求之前调它，
 * 否则后端最先推的几条会漏。`importing` / `imported` 阶段交给导入的监听，
 * 其余交给环境准备的监听，两者不会同时发生。作用域销毁时退订。
 *
 * 两类监听都可以挂多个（页面自己的 + 特调分节的），按挂上的顺序调用。
 * `onImportProgress` / `onEnvProgress` 返回取消函数；在组件 setup 等作用域里挂的，
 * 作用域销毁时自动摘掉。
 */
export function useMaaFWProgressChannel(scriptId: string) {
  let envSubscriptionId: string | null = null
  const importListeners = new Set<MaaFWProgressListener>()
  const envListeners = new Set<MaaFWProgressListener>()

  // 准备过程可能几分钟，全程订阅后端推来的阶段与日志
  const ensureEnvSubscription = () => {
    if (envSubscriptionId) return
    envSubscriptionId = subscribe(
      { id: scriptId, type: WS_MAAFW_ENV_PREPARE_PROGRESS },
      wsMessage => {
        const data = wsMessage.data
        // 导入副本的进度也走这条通道（同一个脚本、同一个订阅），和环境准备不会同时发生
        const listeners =
          data.stage === 'importing' || data.stage === 'imported' ? importListeners : envListeners
        for (const listener of [...listeners]) listener(data)
      }
    )
  }

  const addListener = (
    listeners: Set<MaaFWProgressListener>,
    listener: MaaFWProgressListener
  ): (() => void) => {
    // 同一个函数挂两次也各算一个，取消时只摘自己这一个
    const entry: MaaFWProgressListener = data => listener(data)
    listeners.add(entry)
    const remove = () => {
      listeners.delete(entry)
    }
    if (getCurrentScope()) onScopeDispose(remove)
    return remove
  }

  onScopeDispose(() => {
    if (envSubscriptionId) {
      unsubscribe(envSubscriptionId)
      envSubscriptionId = null
    }
  })

  return {
    ensureEnvSubscription,
    onImportProgress: (listener: MaaFWProgressListener) => addListener(importListeners, listener),
    onEnvProgress: (listener: MaaFWProgressListener) => addListener(envListeners, listener),
  }
}

export type MaaFWProgressChannel = ReturnType<typeof useMaaFWProgressChannel>
