// OK-NTE 原生设置会话（原生 GUI 直控 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

export function useOknteGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'OK-NTE配置会话',
    keys: {
      stopFailed: 'edit.oknteSessionStopFailed',
      startFailed: 'edit.oknteSessionStartFailed',
      setupFailed: 'edit.oknteSessionFailed',
      opened: 'edit.oknteSessionOpened',
      viewOpened: 'edit.oknteViewOpened',
      timeoutWarn: 'edit.oknteSessionTimeoutWarn',
      saved: 'edit.okNteConfigurationThis',
    },
  })
  return {
    state: session.state,
    oknteConfigLoading: session.configLoading,
    oknteWebsocketId: session.taskId,
    showOknteConfigMask: session.showConfigMask,
    showOknteViewMask: session.showViewMask,
    stoppingOknteConfig: session.stopping,
    startSession: session.startSession,
    saveSession: session.saveSession,
    stopSession: session.stopSession,
    querySession: session.querySession,
  }
}
