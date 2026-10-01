import { onScopeDispose } from 'vue'
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
 */
export function useMaaFWProgressChannel(scriptId: string) {
  let envSubscriptionId: string | null = null
  let importListener: MaaFWProgressListener | null = null
  let envListener: MaaFWProgressListener | null = null

  // 准备过程可能几分钟，全程订阅后端推来的阶段与日志
  const ensureEnvSubscription = () => {
    if (envSubscriptionId) return
    envSubscriptionId = subscribe(
      { id: scriptId, type: WS_MAAFW_ENV_PREPARE_PROGRESS },
      wsMessage => {
        const data = wsMessage.data
        // 导入副本的进度也走这条通道（同一个脚本、同一个订阅），和环境准备不会同时发生
        if (data.stage === 'importing' || data.stage === 'imported') {
          importListener?.(data)
          return
        }
        envListener?.(data)
      }
    )
  }

  onScopeDispose(() => {
    if (envSubscriptionId) {
      unsubscribe(envSubscriptionId)
      envSubscriptionId = null
    }
  })

  return {
    ensureEnvSubscription,
    onImportProgress: (listener: MaaFWProgressListener) => {
      importListener = listener
    },
    onEnvProgress: (listener: MaaFWProgressListener) => {
      envListener = listener
    },
  }
}

export type MaaFWProgressChannel = ReturnType<typeof useMaaFWProgressChannel>
