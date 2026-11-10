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
import { bootstrapSchedulerTabs, disposeSchedulerTabs } from '@/stores/scheduler'
import { bootstrapTaskFeedback, disposeTaskFeedback } from '@/composables/useTaskFeedback'
import { bootstrapSystemNotices, disposeSystemNotices } from '@/services/systemNotices'
import { bootstrapTaskAnalytics, disposeTaskAnalytics } from '@/services/taskAnalytics'
import { useBackendI18nStore } from '@/stores/backendI18n'
import { bootstrapMcpStatus, disposeMcpStatus } from '@/composables/useMcpApi'
import { bootstrapEmulatorAnalytics, disposeEmulatorAnalytics } from '@/composables/useEmulatorApi'
import {
  bootstrapVirtualDisplayPrompt,
  disposeVirtualDisplayPrompt,
} from '@/services/virtualDisplayPrompt'
import {
  bootstrapSrcInstallRecovery,
  disposeSrcInstallRecovery,
} from '@/services/srcInstallRecovery'

let registered = false

/**
 * 在首个主 WebSocket 连接前注册并启动所有应用级常驻业务订阅。
 *
 * 这是组合根：业务模块间不互相依赖，应用生命周期只依赖通用资源注册表。
 */
export function bootstrapRealtimeResidents(): void {
  if (!registered) {
    registerResidentResource('mcp-status', {
      bootstrap: bootstrapMcpStatus,
      dispose: disposeMcpStatus,
    })
    registerResidentResource('backend-i18n', {
      bootstrap: () => useBackendI18nStore().bootstrap(),
      dispose: () => useBackendI18nStore().dispose(),
    })
    registerResidentResource('emulator-analytics', {
      bootstrap: bootstrapEmulatorAnalytics,
      dispose: disposeEmulatorAnalytics,
    })
    registerResidentResource('task-analytics', {
      bootstrap: bootstrapTaskAnalytics,
      dispose: disposeTaskAnalytics,
    })
    registerResidentResource('task-runtime', {
      bootstrap: bootstrapTaskRuntimeState,
      dispose: disposeTaskRuntimeState,
    })
    registerResidentResource('task-feedback', {
      bootstrap: bootstrapTaskFeedback,
      dispose: disposeTaskFeedback,
    })
    registerResidentResource('scheduler', {
      bootstrap: bootstrapSchedulerTabs,
      dispose: disposeSchedulerTabs,
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
    registerResidentResource('src-install-recovery', {
      bootstrap: bootstrapSrcInstallRecovery,
      dispose: disposeSrcInstallRecovery,
    })
    registered = true
  }
  bootstrapResidentResources()
}
