import {
  bootstrapUpdateDownloadSubscriptions,
  disposeUpdateDownloadSubscriptions,
} from '@/composables/useUpdateDownload'
import {
  bootstrapResidentResources,
  registerResidentResource,
} from '@/services/websocket/residentResources'
import {
  bootstrapTaskRuntimeState,
  disposeTaskRuntimeState,
} from '@/composables/useTaskRuntimeState'
import { bootstrapSystemNotices, disposeSystemNotices } from '@/services/systemNotices'
import { bootstrapBackendI18n, disposeBackendI18n } from '@/stores/backendI18n'
import {
  bootstrapVirtualDisplayPrompt,
  disposeVirtualDisplayPrompt,
} from '@/services/virtualDisplayPrompt'

let registered = false

/**
 * 在首个主 WebSocket 连接前注册并启动所有应用级常驻业务订阅。
 *
 * 这是组合根：业务模块间不互相依赖，应用生命周期只依赖通用资源注册表。
 */
export function bootstrapRealtimeResidents(): void {
  if (!registered) {
    registerResidentResource('backend-i18n', {
      bootstrap: bootstrapBackendI18n,
      dispose: disposeBackendI18n,
    })
    registerResidentResource('task-runtime', {
      bootstrap: bootstrapTaskRuntimeState,
      dispose: disposeTaskRuntimeState,
    })
    registerResidentResource('update-download', {
      bootstrap: bootstrapUpdateDownloadSubscriptions,
      dispose: disposeUpdateDownloadSubscriptions,
    })
    registerResidentResource('system-notices', {
      bootstrap: bootstrapSystemNotices,
      dispose: disposeSystemNotices,
    })
    registerResidentResource('virtual-display-prompt', {
      bootstrap: bootstrapVirtualDisplayPrompt,
      dispose: disposeVirtualDisplayPrompt,
    })
    registered = true
  }
  bootstrapResidentResources()
}
