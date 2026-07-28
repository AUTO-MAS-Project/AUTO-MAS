import {
  bootstrapUpdateDownloadSubscriptions,
  disposeUpdateDownloadSubscriptions,
} from '@/composables/useUpdateDownload'
import {
  bootstrapResidentResources,
  registerResidentResource,
} from '@/services/websocket/residentResources'
import {
  bootstrapSchedulerSubscriptions,
  disposeSchedulerSubscriptions,
} from '@/views/scheduler/useSchedulerLogic'

let registered = false

/**
 * 在首个主 WebSocket 连接前注册并启动所有应用级常驻业务订阅。
 *
 * 这是组合根：业务模块间不互相依赖，应用生命周期只依赖通用资源注册表。
 */
export function bootstrapRealtimeResidents(): void {
  if (!registered) {
    registerResidentResource('scheduler', {
      bootstrap: bootstrapSchedulerSubscriptions,
      dispose: disposeSchedulerSubscriptions,
    })
    registerResidentResource('update-download', {
      bootstrap: bootstrapUpdateDownloadSubscriptions,
      dispose: disposeUpdateDownloadSubscriptions,
    })
    registered = true
  }
  bootstrapResidentResources()
}
